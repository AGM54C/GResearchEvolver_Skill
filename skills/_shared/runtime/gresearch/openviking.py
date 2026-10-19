"""OpenViking HTTP adapter; no dependency on or copy of the server implementation.

Contract inspected at volcengine/OpenViking e855796c83f9eb575d9b0f3082926660730f6a63.
An immutable revision is published last via a verified commit manifest. Partial
uploads remain unreachable from a committed revision and are reconciled on retry.
"""
import ipaddress
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .core import ResearchError, canonical, digest, finite, fingerprint


class VikingError(ResearchError):
    def __init__(self, code, status=None):
        self.code, self.status = code, status
        super().__init__('OpenViking request failed: ' + str(code))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise VikingError('redirect_refused')


def projection(snapshot, namespace):
    root = namespace + '/' + snapshot['project'] + '/' + snapshot['snapshot']
    files = {root + '/graph.json': canonical(snapshot)}
    uri = lambda identity: root + '/nodes/' + fingerprint(identity) + '.json'
    for node in snapshot['graph']['nodes']:
        files[uri(node['id'])] = canonical({'kind': 'research_node', 'snapshot': snapshot['snapshot'], 'record': node})
    for edge in snapshot['graph']['edges']:
        files[root + '/edges/' + fingerprint(edge['id']) + '.json'] = canonical({
            'kind': 'research_edge', 'snapshot': snapshot['snapshot'], 'record': edge,
            'from_uri': uri(edge['from']), 'to_uri': uri(edge['to'])})
    return root, files


class Client:
    def __init__(self, config):
        allowed = {'endpoint', 'namespace', 'api_key_env', 'account', 'user', 'timeout', 'max_response_bytes', 'processing_mode'}
        if not isinstance(config, dict) or set(config) - allowed:
            raise ResearchError('Unknown OpenViking configuration; credentials must use api_key_env')
        self.endpoint = config['endpoint'].rstrip('/')
        endpoint = urllib.parse.urlsplit(self.endpoint)
        if endpoint.scheme not in {'http', 'https'} or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ResearchError('Use an HTTP(S) endpoint without embedded credentials or query parameters')
        if endpoint.scheme == 'http':
            try: local = ipaddress.ip_address(endpoint.hostname).is_loopback
            except ValueError: local = endpoint.hostname == 'localhost'
            if not local: raise ResearchError('Non-loopback OpenViking requires HTTPS')
        self.namespace = config.get('namespace', 'viking://resources/gresearch').rstrip('/')
        if not re.fullmatch(r'viking://resources/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', self.namespace):
            raise ResearchError('Use a dedicated namespace below viking://resources/')
        self.timeout = finite(config.get('timeout', 60), 'timeout', .1)
        self.deadline = time.monotonic() + self.timeout
        self.maximum = config.get('max_response_bytes', 16_000_000)
        if type(self.maximum) is not int or not 1024 <= self.maximum <= 100_000_000:
            raise ResearchError('max_response_bytes must be 1024..100000000')
        self.mode = config.get('processing_mode', 'vectors_only')
        if self.mode not in {'vectors_only', 'semantic_and_vectors'}:
            raise ResearchError('processing_mode must be vectors_only or semantic_and_vectors')
        self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        if config.get('api_key_env'):
            key = os.environ.get(config['api_key_env'])
            if not key: raise ResearchError('OpenViking API key environment variable is unset')
            self.headers['X-API-Key'] = key
        for field, header in (('account', 'X-OpenViking-Account'), ('user', 'X-OpenViking-User')):
            if config.get(field): self.headers[header] = config[field]
        if any('\n' in value or '\r' in value for value in self.headers.values()):
            raise ResearchError('Invalid OpenViking header')
        self.identity = fingerprint({k: config.get(k) for k in ('endpoint', 'namespace', 'account', 'user')})
        self.opener = urllib.request.build_opener(NoRedirect())
        self.receipts = []

    def request(self, method, path, payload=None, query=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise VikingError('deadline')
        url = self.endpoint + path + ('?' + urllib.parse.urlencode(query) if query else '')
        data = canonical(payload).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        started = time.monotonic()
        try:
            try: response = self.opener.open(req, timeout=remaining)
            except urllib.error.HTTPError as exc: response = exc
            with response:
                status = response.status
                chunks, size = [], 0
                while True:
                    remaining = self.deadline - time.monotonic()
                    if remaining <= 0: raise VikingError('deadline')
                    sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                    if sock is not None: sock.settimeout(remaining)
                    chunk = response.read1(min(65536, self.maximum + 1 - size))
                    if not chunk: break
                    size += len(chunk)
                    if size > self.maximum: raise VikingError('response_too_large')
                    chunks.append(chunk)
                raw = b''.join(chunks)
            result = json.loads(raw)
            if not isinstance(result, dict): raise VikingError('invalid_envelope', status)
            if status < 200 or status >= 300 or result.get('status') != 'ok':
                error = result.get('error', {})
                raise VikingError(error.get('code', 'http_error') if isinstance(error, dict) else 'http_error', status)
            if 'result' not in result: raise VikingError('missing_result', status)
            self.receipts.append({'method': method, 'path': path, 'http_status': status, 'response_sha256': digest(raw),
                                  'seconds': time.monotonic() - started})
            return result['result']
        except json.JSONDecodeError as exc:
            raise VikingError('invalid_json') from exc

    def read(self, uri):
        result = self.request('GET', '/api/v1/content/read', query={'uri': uri, 'raw': 'true'})
        if not isinstance(result, str): raise VikingError('invalid_content')
        return result

    def verify_text(self, uri, text):
        if self.read(uri) != text:
            raise VikingError('content_mismatch')

    def ensure_file(self, uri, text):
        try:
            current = self.read(uri)
        except VikingError as exc:
            if exc.status != 404 and exc.code != 'NOT_FOUND': raise
        else:
            if current != text: raise VikingError('immutable_uri_conflict')
            return
        try:
            self.request('POST', '/api/v1/content/write', {'uri': uri, 'content': text, 'mode': 'create',
                                                         'wait': True, 'processing_mode': self.mode})
        except VikingError as exc:
            if exc.status in {400, 401, 403, 422}:
                raise
            self.verify_text(uri, text)
            return
        except OSError:
            # Lost acknowledgement is reconciled by reading the immutable URI.
            # It is never retried as an append or an unconditional replacement.
            self.verify_text(uri, text)
            return
        self.verify_text(uri, text)

    def ensure_directory(self, uri):
        try: self.request('POST', '/api/v1/fs/mkdir', {'uri': uri})
        except VikingError as exc:
            if exc.code != 'ALREADY_EXISTS' and exc.status != 409: raise
            result = self.request('GET', '/api/v1/fs/stat', query={'uri': uri})
            if not isinstance(result, dict) or not result.get('isDir', result.get('is_dir', False)):
                raise VikingError('directory_conflict')

    def commit_content(self, files, snapshot):
        return canonical({'version': 1, 'snapshot': snapshot['snapshot'], 'revision': snapshot['revision'],
                          'files': {uri: digest(value.encode('utf-8')) for uri, value in sorted(files.items())}})

    def verify_commit(self, root, files, snapshot):
        self.verify_text(root + '/commit.json', self.commit_content(files, snapshot))
        self.verify_text(root + '/graph.json', files[root + '/graph.json'])

    def publish(self, snapshot):
        root, files = projection(snapshot, self.namespace)
        segments = root[len('viking://resources/'):].split('/')
        current = 'viking://resources'
        for segment in segments:
            current += '/' + segment
            self.ensure_directory(current)
        for kind in ('nodes', 'edges'): self.ensure_directory(root + '/' + kind)
        for uri, content in sorted(files.items()): self.ensure_file(uri, content)
        self.ensure_file(root + '/commit.json', self.commit_content(files, snapshot))
        self.verify_commit(root, files, snapshot)
        return {'root_uri': root, 'snapshot': snapshot['snapshot'], 'verified_files': len(files),
                'processing_mode': self.mode, 'requests': self.receipts,
                'scientific_verification': False}

    def load(self, project, snapshot_hash):
        from .core import valid_id
        valid_id(project)
        if not re.fullmatch(r'[a-f0-9]{64}', snapshot_hash): raise ResearchError('Expected snapshot SHA-256')
        root = self.namespace + '/' + project + '/' + snapshot_hash
        snapshot = json.loads(self.read(root + '/graph.json'))
        if snapshot.get('snapshot') != snapshot_hash or snapshot.get('project') != project or fingerprint({k: v for k, v in snapshot.items() if k != 'snapshot'}) != snapshot_hash:
            raise VikingError('snapshot_mismatch')
        from .memory import validate
        validate(snapshot['graph'])
        _, files = projection(snapshot, self.namespace)
        self.verify_commit(root, files, snapshot)
        for uri, text in files.items(): self.verify_text(uri, text)
        return snapshot

    def find(self, query, root, limit):
        result = self.request('POST', '/api/v1/search/find', {'query': query, 'target_uri': root, 'limit': limit})
        if not isinstance(result, dict) or not isinstance(result.get('resources'), list):
            raise VikingError('invalid_search_result')
        return result['resources'][:limit]
