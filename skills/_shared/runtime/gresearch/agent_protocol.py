"""Native function calling, with complete replies and stateless continuations.

Receipts retain provider output (including Responses reasoning items), never
authentication headers. Tool execution belongs to the durable controller.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time

from . import models
from .core import ResearchError, atomic_bytes, canonical, digest, fingerprint, write_json


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ResearchError('Duplicate JSON field')
            value[key] = item
        return value
    def nonfinite(value): raise ResearchError('Nonfinite JSON number')
    try: return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, TypeError, RecursionError) as exc: raise ResearchError('Invalid JSON') from exc


def arguments(value):
    if isinstance(value, str): value = strict_json(value)
    if not isinstance(value, dict) or len(canonical(value)) > 100_000:
        raise ResearchError('Tool arguments must be a bounded JSON object')
    return value


def parse_response(provider, result, call_prefix):
    calls, text, append = [], '', []
    if provider == 'responses':
        if result.get('status') != 'completed': raise ResearchError('Incomplete model response; no tools executed')
        output = result.get('output', [])
        for item in output:
            if item.get('type') == 'function_call':
                if item.get('status') not in {None, 'completed'}: raise ResearchError('Incomplete function call')
                calls.append({'id': item['call_id'], 'name': item['name'], 'arguments': arguments(item['arguments'])})
            elif item.get('type') == 'message':
                text += ''.join(c.get('text', '') for c in item.get('content', []) if c.get('type') == 'output_text')
            elif item.get('type') != 'reasoning':
                raise ResearchError('Unexpected provider-side tool; use the local gateway')
        append = output
        usage = result.get('usage') or {}
    elif provider == 'chat-completions':
        choices = result.get('choices', [])
        if len(choices) != 1 or choices[0].get('finish_reason') not in {'stop', 'tool_calls'}:
            raise ResearchError('Incomplete or ambiguous chat response; no tools executed')
        message = choices[0]['message']
        text = message.get('content') or ''
        tool_calls = message.get('tool_calls') or []
        for item in tool_calls:
            if item.get('type') != 'function': raise ResearchError('Unsupported tool call type')
            calls.append({'id': item['id'], 'name': item['function']['name'], 'arguments': arguments(item['function']['arguments'])})
        append = [{'role': 'assistant', 'content': text}]
        if tool_calls: append[0]['tool_calls'] = tool_calls
        usage = result.get('usage') or {}
    elif provider == 'ollama':
        if result.get('done') is not True or result.get('done_reason') == 'length':
            raise ResearchError('Incomplete Ollama response; no tools executed')
        message = result['message']
        text = message.get('content') or ''
        for i, item in enumerate(message.get('tool_calls') or []):
            calls.append({'id': call_prefix + '-' + str(i), 'name': item['function']['name'], 'arguments': arguments(item['function']['arguments'])})
        append = [message]
        usage = {'input_tokens': result.get('prompt_eval_count'), 'output_tokens': result.get('eval_count')}
    else: raise ResearchError('Unsupported native tool provider')
    if not isinstance(text, str) or (not text.strip() and not calls): raise ResearchError('Empty model turn')
    if len(calls) > 32: raise ResearchError('Too many tool calls in one turn')
    seen = set()
    for call in calls:
        if not isinstance(call['id'], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', call['id']) or call['id'] in seen:
            raise ResearchError('Missing, invalid or duplicate tool call ID')
        if not isinstance(call['name'], str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}', call['name']):
            raise ResearchError('Invalid tool name')
        seen.add(call['id'])
    return {'text': text, 'calls': calls, 'append': append, 'usage': usage}


def turn(config, history, tools, destination, call_prefix='call'):
    cfg, key = models.resolve(config)
    provider = cfg['provider']
    limit, timeout = cfg.get('max_output_tokens', 2000), cfg.get('timeout', 120)
    if type(limit) is not int or not 1 <= limit <= 32768: raise ResearchError('Invalid output token limit')
    if type(timeout) not in {int, float} or not 1 <= timeout <= 600: raise ResearchError('Invalid model timeout')
    if not history or len(canonical(history)) + len(canonical(tools)) > cfg.get('max_input_chars', 120000):
        raise ResearchError('Context budget exhausted; original history is retained')
    body = {'model': cfg['model']}
    if provider == 'responses':
        endpoint = '/responses'
        body.update(input=history, tools=[{'type': 'function', **tool, 'strict': True} for tool in tools],
                    store=False, stream=cfg.get('stream', True), max_output_tokens=limit,
                    include=['reasoning.encrypted_content'], parallel_tool_calls=False)
        if cfg.get('reasoning_effort'): body['reasoning'] = {'effort': cfg['reasoning_effort']}
    elif provider in {'chat-completions', 'ollama'}:
        endpoint = '/api/chat' if provider == 'ollama' else '/chat/completions'
        body.update(messages=history, tools=[{'type': 'function', 'function': tool} for tool in tools], stream=False)
        if provider == 'ollama': body['options'] = {'num_predict': limit, 'num_ctx': cfg.get('context_tokens', 8192), 'seed': cfg.get('seed', 0)}
        else: body.update(max_tokens=limit, parallel_tool_calls=False)
    else: raise ResearchError('Unsupported native tool provider')
    if 'temperature' in cfg:
        if provider == 'ollama': body['options']['temperature'] = cfg['temperature']
        else: body['temperature'] = cfg['temperature']
    dest = Path(destination)
    if dest.exists(): raise ResearchError('Model attempt directory already exists')
    dest.mkdir(parents=True)
    public = {k: v for k, v in cfg.items() if k not in {'key_env', 'config_dir'}}
    write_json(dest / 'request.json', {'config': public, 'body': body, 'credential_values_recorded': False})
    started = time.monotonic()
    try:
        raw, mime = models._request(cfg['base_url'].rstrip('/') + endpoint, body, key, timeout)
        atomic_bytes(dest / 'response.raw', raw)
        if 'text/event-stream' in mime or raw.lstrip().startswith(b'data:'):
            events = [strict_json(line[5:].strip()) for line in raw.decode('utf-8').splitlines()
                      if line.startswith('data:') and line[5:].strip() not in {'', '[DONE]'}]
            completed = [e['response'] for e in events if e.get('type') == 'response.completed']
            if len(completed) != 1 or any(e.get('type') in {'error', 'response.failed', 'response.incomplete'} for e in events):
                raise ResearchError('Stream lacks a single complete response; no tools executed')
            response = completed[0]
        else: response = strict_json(raw)
        result = parse_response(provider, response, call_prefix)
        result.update(provider=provider, requested_model=cfg['model'], returned_model=response.get('model'),
                      request_hash=fingerprint(body), response_sha256=digest(raw), seconds=time.monotonic() - started,
                      seed_reproducibility_guaranteed=False)
        write_json(dest / 'result.json', result)
        return result
    except Exception as exc:
        write_json(dest / 'failure.json', {'type': type(exc).__name__, 'category': getattr(exc, 'category', 'invalid_response'),
                    'retryable': getattr(exc, 'retryable', False), 'retry_after': getattr(exc, 'retry_after', 0),
                    'seconds': time.monotonic() - started, 'counts_against_budget': True})
        raise


def tool_output(provider, call, result):
    content = canonical(result)
    if provider == 'responses': return {'type': 'function_call_output', 'call_id': call['id'], 'output': content}
    if provider == 'ollama': return {'role': 'tool', 'tool_name': call['name'], 'content': content}
    return {'role': 'tool', 'tool_call_id': call['id'], 'content': content}
