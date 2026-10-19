"""Explicit model calls with bounded responses, usage receipts and no persisted credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from .core import ResearchError, digest, fingerprint, write_json


def resolve(config):
    config = dict(config)
    allowed={'provider','model','base_url','config_dir','key_env','max_output_tokens','timeout','max_input_chars',
             'stream','reasoning_effort','context_tokens','seed','temperature','json_schema'}
    if set(config)-allowed:raise ResearchError('Unknown model configuration fields; credentials belong in key_env or the existing Codex configuration')
    key = None
    if config.get('provider') == 'codex-config':
        try: import tomllib
        except ImportError:
            try: import tomli as tomllib
            except ImportError as exc: raise ResearchError('codex-config on Python 3.10 needs optional tomli; Python 3.11+ includes tomllib') from exc
        home = Path(config.get('config_dir') or os.getenv('CODEX_HOME') or Path.home() / '.codex')
        settings = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8-sig'))
        provider = settings.get('model_providers', {}).get(settings.get('model_provider', 'openai'), {})
        if provider.get('wire_api', 'responses') != 'responses':
            raise ResearchError('Configured provider is not a Responses endpoint')
        config.setdefault('model', settings.get('model'))
        config.setdefault('base_url', provider.get('base_url', 'https://api.openai.com/v1'))
        config['provider'] = 'responses'
        if provider.get('env_key'):
            key = os.getenv(provider['env_key'])
        else:
            auth = json.loads((home / 'auth.json').read_text(encoding='utf-8-sig'))
            key = auth.get('OPENAI_API_KEY')
        if not key:
            raise ResearchError('Configured API-key authentication unavailable; use the authenticated CLI or an explicit provider')
    elif config.get('key_env'):
        key = os.getenv(config['key_env'])
        if not key: raise ResearchError('Missing model credential environment variable')
    if not config.get('model'): raise ResearchError('Pin a concrete model identifier')
    url = urllib.parse.urlsplit(config.get('base_url', ''))
    if url.username or url.password or url.query or url.fragment:
        raise ResearchError('Model base URL must not embed credentials, queries or fragments')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}):
        raise ResearchError('Use HTTPS, or HTTP on loopback only')
    return config, key


def _request(url, body, key, timeout):
    headers = {'Content-Type': 'application/json', 'User-Agent': 'GResearchEvolver/2.1'}
    if key: headers['Authorization'] = 'Bearer ' + key
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            chunks, size = [], 0
            while size <= 16_000_000:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0: raise ResearchError('Model wall-clock timeout')
                # urllib's HTTPResponse exposes the live socket on CPython. Bound
                # each read by the remaining total budget, not a fresh timeout.
                sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                if sock is not None: sock.settimeout(remaining)
                chunk = response.read1(min(65536, 16_000_001-size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
            raw = b''.join(chunks)
            content_type = response.headers.get('Content-Type', '')
    except urllib.error.HTTPError as exc:
        # Provider errors can echo headers or credentials. Persist only the status, not the body.
        raise ResearchError('Model endpoint HTTP ' + str(exc.code)) from None
    if len(raw) > 16_000_000: raise ResearchError('Model response exceeded 16 MB')
    if time.monotonic()-started > timeout: raise ResearchError('Model wall-clock timeout')
    return raw, content_type


def generate(config, messages, destination):
    cfg, key = resolve(config)
    limit = cfg.get('max_output_tokens', 1200)
    if not isinstance(limit, int) or not 1 <= limit <= 32768:
        raise ResearchError('max_output_tokens must be 1..32768')
    timeout = cfg.get('timeout', 120)
    if not 1 <= timeout <= 600: raise ResearchError('Model timeout must be 1..600 seconds')
    if not messages or any(m.get('role') not in {'system', 'user', 'assistant'} or not isinstance(m.get('content'), str) for m in messages):
        raise ResearchError('Messages need explicit text and roles')
    if sum(len(m['content']) for m in messages) > cfg.get('max_input_chars', 120000):
        raise ResearchError('Input exceeds declared character budget')
    dest = Path(destination)
    if dest.exists(): raise ResearchError('Use a fresh model-call directory; do not overwrite attempts')
    dest.mkdir(parents=True)
    provider = cfg.get('provider')
    body = {'model': cfg['model']}
    if provider == 'responses':
        endpoint = '/responses'
        body.update(input=messages, max_output_tokens=limit, store=False, stream=cfg.get('stream', True))
        if cfg.get('reasoning_effort'): body['reasoning'] = {'effort': cfg['reasoning_effort']}
        if cfg.get('json_schema'): body['text'] = {'format': {'type':'json_schema','name':'research_response','strict':True,'schema':cfg['json_schema']}}
    elif provider == 'chat-completions':
        endpoint = '/chat/completions'
        body.update(messages=messages, max_tokens=limit, stream=False)
        if cfg.get('json_schema'): body['response_format'] = {'type':'json_schema','json_schema':{'name':'research_response','strict':True,'schema':cfg['json_schema']}}
    elif provider == 'ollama':
        endpoint = '/api/chat'
        body.update(messages=messages, stream=False, options={'num_predict': limit, 'num_ctx': cfg.get('context_tokens', 8192), 'seed': cfg.get('seed', 0)})
        if cfg.get('json_schema'): body['format'] = cfg['json_schema']
    else:
        raise ResearchError('Model provider must be responses, chat-completions, ollama or codex-config')
    if 'temperature' in cfg and provider != 'ollama': body['temperature'] = cfg['temperature']
    public_cfg = {k: v for k, v in cfg.items() if k not in {'key_env', 'config_dir'}}
    write_json(dest / 'request.json', {'config': public_cfg, 'body': body, 'credential_values_recorded': False})
    started = time.monotonic()
    try:
        raw, content_type = _request(cfg['base_url'].rstrip('/') + endpoint, body, key, timeout)
        (dest / 'response.raw').write_bytes(raw)
        if 'text/event-stream' in content_type or raw.lstrip().startswith(b'data:'):
            events = []
            for line in raw.decode('utf-8').splitlines():
                if line.startswith('data:') and line[5:].strip() != '[DONE]':
                    events.append(json.loads(line[5:].strip()))
            completed = [e['response'] for e in events if e.get('type') == 'response.completed']
            if not completed: raise ResearchError('Stream ended without a completed response')
            result = completed[-1]
        else: result = json.loads(raw)
        if provider == 'responses':
            text = ''.join(c.get('text', '') for item in result.get('output', []) if item.get('type') == 'message' for c in item.get('content', []) if c.get('type') == 'output_text')
            usage = result.get('usage', {})
            incomplete = result.get('status') not in {None, 'completed'}
        elif provider == 'chat-completions':
            text = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            incomplete = result['choices'][0].get('finish_reason') != 'stop'
        else:
            text = result['message']['content']
            usage = {'input_tokens': result.get('prompt_eval_count'), 'output_tokens': result.get('eval_count')}
            incomplete = result.get('done_reason') == 'length'
        if not isinstance(text, str) or not text.strip(): raise ResearchError('Model returned no answer text')
        receipt = {'requested_model': cfg['model'], 'returned_model': result.get('model'),
                   'provider': provider, 'usage': usage, 'seconds': time.monotonic() - started,
                   'request_hash': fingerprint(body), 'response_sha256': digest(raw), 'incomplete': incomplete,
                   'text': text, 'seed_reproducibility_guaranteed': False}
        write_json(dest / 'result.json', receipt)
        return receipt
    except Exception as exc:
        write_json(dest / 'failure.json', {'type': type(exc).__name__, 'seconds': time.monotonic() - started,
                                          'status': 'failed', 'counts_against_budget': True})
        raise


def embeddings(config, texts, destination):
    cfg, key = resolve(config)
    if not texts or any(not isinstance(t, str) or not t for t in texts) or sum(map(len, texts)) > 120000:
        raise ResearchError('Provide nonempty texts within the batch character budget')
    dest = Path(destination)
    if dest.exists(): raise ResearchError('Embedding receipt directory already exists')
    dest.mkdir(parents=True)
    endpoint = '/api/embed' if cfg.get('provider') == 'ollama' else '/embeddings'
    body = {'model': cfg['model'], 'input': texts}
    raw, _ = _request(cfg['base_url'].rstrip('/') + endpoint, body, key, cfg.get('timeout', 120))
    (dest / 'response.raw').write_bytes(raw)
    response = json.loads(raw)
    if endpoint != '/api/embed' and sorted(x['index'] for x in response.get('data',[])) != list(range(len(texts))):
        raise ResearchError('Embedding response indices are missing, duplicated or out of range')
    vectors = response['embeddings'] if endpoint == '/api/embed' else [x['embedding'] for x in sorted(response['data'], key=lambda x: x['index'])]
    if len(vectors) != len(texts): raise ResearchError('Embedding response count differs from inputs')
    from .core import finite
    if not vectors or not vectors[0] or len({len(v) for v in vectors}) != 1: raise ResearchError('Invalid embedding dimensions')
    for vector in vectors:
        for value in vector: finite(value)
    result = {'model': cfg['model'], 'returned_model':response.get('model'), 'text_hashes': [digest(t.encode('utf-8')) for t in texts],
              'vectors': vectors, 'response_sha256': digest(raw), 'usage': response.get('usage'), 'generated': True}
    write_json(dest / 'result.json', result)
    return result
