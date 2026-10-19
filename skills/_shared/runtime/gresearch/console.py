"""Local-only human control UI. Observe, intervene, fork and compare real artifacts."""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import urllib.parse

from .core import ResearchError, Store, canonical, compare_runs, safe_path
from .execution import run_workflow


PAGE = '''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>GResearch · 研究控制台</title><style>
body{font:16px system-ui;max-width:1180px;margin:2rem auto;padding:0 1rem;color:#183044;background:#f5f7fa}
button,input,select,textarea{font:inherit;padding:.5rem;margin:.2rem;border:1px solid #aab8c6;border-radius:5px}
button{cursor:pointer;background:white}button:hover{background:#dfeaf4}pre{background:white;padding:1rem;overflow:auto;max-height:32rem;white-space:pre-wrap}
section{margin:1rem 0}textarea{width:95%;height:5rem}small{color:#465b6e}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}@media(max-width:700px){.grid{display:block}}
</style><h1>GResearch · 研究控制台</h1>
<p>查看运行、科学阶段与原始记录。暂停在阶段边界生效；取消终止本地进程。远程外部状态需要另行核实。</p>
<section><label>运行 <select id="run"></select></label><button id="refresh">刷新</button><label>阶段 <select id="stage"></select></label></section>
<section id="controls"><button data-action="run">执行</button><button data-action="pause">暂停</button><button data-action="resume">继续</button><button data-action="step">单步</button><button data-action="breakpoint">设断点</button><button data-action="retry">重试失败阶段</button><button data-action="cancel">取消</button><button data-action="archive">归档</button></section>
<p id="message" role="status"></p><div class="grid"><section><h2>科学阶段与状态</h2><pre id="state"></pre></section><section><h2>事件与输入输出依据</h2><pre id="events"></pre></section></div>
<section><h2>人工批注</h2><label>对象（阶段、论断或产物）<input id="target"></label><label>判断与理由 <input id="note" size="55"></label><button id="annotate">保存批注</button></section>
<section><h2>从选中阶段建立分支</h2><p>原运行保留。恢复工作区文件检查点；数据库、服务、远程进程等外部状态不自动回滚。</p><label>阶段配置修改 JSON（键为阶段 ID；空对象表示不改配置）<textarea id="patch">{}</textarea></label><button id="fork">建立分支</button></section>
<section><h2>对比运行</h2><label>另一个运行 <input id="other"></label><button id="compare">对比阶段与产物</button><pre id="comparison"></pre></section>
<section><h2>产物与原始日志</h2><select id="artifact"></select><button id="read">查看文本</button><pre id="raw"></pre></section>
<script>
const token=__TOKEN__, el=id=>document.getElementById(id);let current=null;
async function api(path,body){let response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Research-Token':token},body:JSON.stringify(body)}:{});let data=await response.json();if(!response.ok)throw Error(data.error||response.statusText);return data}
function options(id,values){let selected=el(id).value;el(id).replaceChildren(...values.map(v=>{let o=document.createElement('option');o.textContent=v;o.value=v;return o}));if(values.includes(selected))el(id).value=selected}
function show(id,value){el(id).textContent=typeof value==='string'?value:JSON.stringify(value,null,2)}
async function refresh(){let runs=await api('/api/runs');options('run',runs.map(x=>x.run));if(!el('run').value)return;current=await api('/api/run?run='+encodeURIComponent(el('run').value));options('stage',current.manifest.stages.map(x=>x.id));show('state',{objective:current.manifest.objective,status:current.state.status,stages:current.manifest.stages.map(s=>({id:s.id,milestone:s.milestone||s.instructions||s.skill,status:current.state.stages[s.id]})),annotations:current.state.annotations});show('events',current.events.slice(-30));options('artifact',current.files)}
async function action(name,extra={}){let result=await api('/api/action',{action:name,run:el('run').value,stage:el('stage').value,...extra});show('message',result);await refresh();return result}
function guarded(fn){return async()=>{try{await fn()}catch(e){show('message',e.message)}}}
el('refresh').onclick=guarded(refresh);el('run').onchange=guarded(refresh);
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=guarded(()=>action(b.dataset.action)));
el('annotate').onclick=guarded(()=>action('annotate',{target:el('target').value,text:el('note').value}));
el('fork').onclick=guarded(async()=>{let r=await action('fork',{changes:JSON.parse(el('patch').value)});el('other').value=r.child});
el('compare').onclick=guarded(async()=>show('comparison',await action('compare',{other:el('other').value})));
el('read').onclick=guarded(async()=>show('raw',await api('/api/artifact?run='+encodeURIComponent(el('run').value)+'&path='+encodeURIComponent(el('artifact').value))));
guarded(refresh)();setInterval(guarded(refresh),4000);
</script></html>'''


def make_server(root, port=0):
    root, token = str(Path(root).resolve()), secrets.token_urlsafe(32)
    workers, lock = set(), threading.Lock()

    def start_worker(run):
        with lock:
            if run in workers: return
            workers.add(run)
        def work():
            store = Store(root)
            try:
                run_workflow(store, run)
            except Exception as exc:
                with store.tx(): store.event(run, 'console_worker_error', {'error': str(exc)})
            finally:
                store.close()
                with lock: workers.discard(run)
        threading.Thread(target=work, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def respond(self, value, code=200, html=False):
            raw = value.encode('utf-8') if html else canonical(value).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ('text/html' if html else 'application/json') + '; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}' and self.client_address[0] == '127.0.0.1'

        def do_GET(self):
            if not self.valid_host(): return self.respond({'error': 'invalid host'}, 403)
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == '/': return self.respond(PAGE.replace('__TOKEN__', json.dumps(token)), html=True)
            store = Store(root)
            try:
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path == '/api/runs':
                    result = [{'run': r[0]} for r in store.db.execute('SELECT id FROM runs ORDER BY rowid')]
                else:
                    run = query['run'][0]
                    m, s = store.get(run)
                    if parsed.path == '/api/run':
                        result = {'manifest': m, 'state': s, 'events': store.events(run),
                                  'files': [p.relative_to(store.work(run)).as_posix() for p in store.work(run).rglob('*') if p.is_file()]}
                    elif parsed.path == '/api/artifact':
                        p = safe_path(store.work(run), query['path'][0])
                        with p.open('rb') as file: raw = file.read(1_000_001)
                        result = {'path': query['path'][0], 'text': raw[:1_000_000].decode('utf-8', errors='replace'), 'truncated': len(raw) > 1_000_000}
                    else: return self.respond({'error': 'not found'}, 404)
                self.respond(result)
            except (ResearchError, KeyError, OSError) as exc: self.respond({'error': str(exc)}, 400)
            finally: store.close()

        def do_POST(self):
            expected_origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin') != expected_origin or not hmac.compare_digest(self.headers.get('X-Research-Token', ''), token):
                return self.respond({'error': 'origin/token validation failed'}, 403)
            if self.path != '/api/action': return self.respond({'error': 'not found'}, 404)
            store = Store(root)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 100_000: raise ResearchError('invalid request length')
                body = json.loads(self.rfile.read(size))
                run, action = body['run'], body['action']
                store.get(run)
                if action == 'run': start_worker(run); result = {'worker': 'requested'}
                elif action in {'pause', 'resume', 'step', 'cancel', 'breakpoint', 'retry'}:
                    result = store.control(run, action, body.get('reason', 'human console intervention'), body.get('stage'))
                    if action in {'resume', 'step', 'retry'}: start_worker(run)
                elif action == 'annotate': result = store.annotate(run, body['target'], body['text'])
                elif action == 'fork': result = {'child': store.fork(run, body['stage'], body.get('changes', {}))}
                elif action == 'compare': result = compare_runs(store, run, body['other'])
                elif action == 'archive': result = store.archive(run)
                else: raise ResearchError('unknown action')
                self.respond(result)
            except (ResearchError, KeyError, OSError, ValueError, TypeError) as exc: self.respond({'error': str(exc)}, 400)
            finally: store.close()

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.research_token = token  # local automated integration testing; never returned by JSON API
    return server


def serve(root, port):
    server = make_server(root, port)
    print(f'Research console: http://127.0.0.1:{server.server_port}', flush=True)
    try: server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()
