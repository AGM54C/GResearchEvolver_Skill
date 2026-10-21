"""Local-only human control UI. Observe, intervene, fork and compare real artifacts."""
from __future__ import annotations

import hmac
import base64
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
<p><a href="/agent">进入完整能力 Agent 工作台 →</a></p>
<p>查看运行、科学阶段与原始记录。暂停在阶段边界生效；取消终止本地进程。远程外部状态需要另行核实。</p>
<section><label>运行 <select id="run"></select></label><button id="refresh">刷新</button><label>阶段 <select id="stage"></select></label></section>
<section id="controls"><button data-action="run">执行</button><button data-action="pause">暂停</button><button data-action="resume">继续</button><button data-action="step">单步</button><button data-action="breakpoint">设断点</button><button data-action="retry">重试失败阶段</button><button data-action="cancel">取消</button><button data-action="archive">归档</button></section>
<p id="message" role="status"></p>
<section><h2>阶段报告与科研讲解</h2><button id="load-report">读取最新报告</button><span id="report-version"></span><p id="report-update" role="status"></p>
<label>讲解深度 <select id="depth"><option value="intuition">直观解释</option><option value="technical">方法与技术细节</option><option value="evidence">前提、边界与论断来源</option></select></label><pre id="explanation"></pre>
<details><summary>完整阶段报告：理由、执行结果、证据与待决定问题</summary><pre id="report"></pre></details>
<label>研究者 <input id="reviewer" value="researcher"></label><label>意见 <select id="decision"><option value="comment">记录意见</option><option value="explain">请求进一步解释</option><option value="revise">要求修改并暂停</option><option value="approve">接受本报告并允许继续</option><option value="stop">停止研究运行</option></select></label>
<label>判断、理由或希望解决的问题 <textarea id="feedback-reason"></textarea></label><button id="feedback">提交当前报告的反馈</button>
<p>只针对上方显示的报告提交。接受不会替代科学验证；修改请使用下方分支功能保留原轨迹。</p></section>
<details><summary>运行状态与原始审计记录</summary><div class="grid"><section><h2>科学阶段与状态</h2><pre id="state"></pre></section><section><h2>事件与输入输出依据</h2><pre id="events"></pre></section></div></details>
<section><h2>人工批注</h2><label>对象（阶段、论断或产物）<input id="target"></label><label>判断与理由 <input id="note" size="55"></label><button id="annotate">保存批注</button></section>
<section><h2>从选中阶段建立分支</h2><p>原运行保留。恢复工作区文件检查点；数据库、服务、远程进程等外部状态不自动回滚。</p><label>阶段配置修改 JSON（键为阶段 ID；空对象表示不改配置）<textarea id="patch">{}</textarea></label><button id="fork">建立分支</button><button id="revise">落实最近的修改请求并建分支</button></section>
<section><h2>对比运行</h2><label>另一个运行 <input id="other"></label><button id="compare">对比阶段与产物</button><pre id="comparison"></pre></section>
<section><h2>产物与原始日志</h2><select id="artifact"></select><button id="read">查看文本</button><pre id="raw"></pre></section>
<script>
const token=__TOKEN__, el=id=>document.getElementById(id);let current=null,shownReport=null;
async function api(path,body){let response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Research-Token':token},body:JSON.stringify(body)}:{});let data=await response.json();if(!response.ok)throw Error(data.error||response.statusText);return data}
function options(id,values){let selected=el(id).value;el(id).replaceChildren(...values.map(v=>{let o=document.createElement('option');o.textContent=v;o.value=v;return o}));if(values.includes(selected))el(id).value=selected}
function show(id,value){el(id).textContent=typeof value==='string'?value:JSON.stringify(value,null,2)}
async function refresh(){let runs=await api('/api/runs');options('run',runs.map(x=>x.run));if(!el('run').value)return;current=await api('/api/run?run='+encodeURIComponent(el('run').value));options('stage',current.manifest.stages.map(x=>x.id));show('state',{objective:current.manifest.objective,status:current.state.status,stages:current.manifest.stages.map(s=>({id:s.id,milestone:s.milestone||s.instructions||s.skill,status:current.state.stages[s.id]})),annotations:current.state.annotations});show('events',current.events.slice(-30));options('artifact',current.files);if(!shownReport)await loadReport();else if(current.state.stages[el('stage').value].report?.id!==shownReport.receipt.id)show('report-update','报告有新版本；请先读取最新报告再提交意见。当前输入会保留。')}
function showExplanation(){let bundle=shownReport?.report.explanation?.bundle;if(!bundle){show('explanation','尚未提交科研讲解。可以选择“请求进一步解释”，说明需要直观例子、方法细节或原文依据。');return}let depth=el('depth').value;show('explanation',depth==='evidence'?{assumptions:bundle.assumptions,limitations:bundle.limitations,claims:bundle.claims,questions:bundle.questions}:bundle[depth])}
async function loadReport(){shownReport=await api('/api/report?run='+encodeURIComponent(el('run').value)+'&stage='+encodeURIComponent(el('stage').value));show('report',shownReport.markdown);show('report-version',shownReport.report.stage+' · '+shownReport.receipt.id);show('report-update','');showExplanation()}
async function action(name,extra={}){let result=await api('/api/action',{action:name,run:el('run').value,stage:el('stage').value,...extra});show('message',result);await refresh();return result}
function guarded(fn){return async()=>{try{await fn()}catch(e){show('message',e.message)}}}
el('refresh').onclick=guarded(refresh);el('run').onchange=guarded(async()=>{shownReport=null;await refresh()});el('stage').onchange=guarded(loadReport);el('load-report').onclick=guarded(loadReport);el('depth').onchange=showExplanation;
el('feedback').onclick=guarded(async()=>{if(!shownReport)throw Error('请先读取报告');await action('feedback',{report_id:shownReport.receipt.id,actor:el('reviewer').value,decision:el('decision').value,reason:el('feedback-reason').value});await loadReport()});
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=guarded(()=>action(b.dataset.action)));
el('annotate').onclick=guarded(()=>action('annotate',{target:el('target').value,text:el('note').value}));
el('fork').onclick=guarded(async()=>{let r=await action('fork',{changes:JSON.parse(el('patch').value)});el('other').value=r.child});
el('revise').onclick=guarded(async()=>{let items=current.state.stages[el('stage').value].feedback||[];let request=[...items].reverse().find(x=>x.decision==='revise');if(!request)throw Error('当前阶段没有修改请求');let r=await action('revise',{feedback_id:request.id,changes:JSON.parse(el('patch').value)});el('other').value=r.child});
el('compare').onclick=guarded(async()=>show('comparison',await action('compare',{other:el('other').value})));
el('read').onclick=guarded(async()=>show('raw',await api('/api/artifact?run='+encodeURIComponent(el('run').value)+'&path='+encodeURIComponent(el('artifact').value))));
guarded(refresh)();setInterval(guarded(refresh),4000);
</script></html>'''


def make_server(root, port=0):
    root, token = str(Path(root).resolve()), secrets.token_urlsafe(32)
    workers, lock = set(), threading.Lock()

    def start_worker(run, *, agent_session=False):
        worker_key = ('agent:' if agent_session else 'run:') + run
        with lock:
            if worker_key in workers: return
            workers.add(worker_key)
        def work():
            store = Store(root)
            try:
                if agent_session:
                    from . import agent, long_horizon as horizon
                    while True:
                        state = agent.get(store, run)
                        if state['status'] == 'ready': state = agent.run(store, run)
                        if state['status'] != 'waiting_external': break
                        # Durable receipt polling, not model polling. On console
                        # restart the researcher can restart observation explicitly.
                        horizon.watch(store, state['long_project'], seconds=1, interval=1)
                        if agent.get(store, run)['status'] == 'waiting_external':
                            threading.Event().wait(1)
                else: run_workflow(store, run)
            except Exception as exc:
                with store.tx(): store.event(worker_key, 'console_worker_error', {'type': type(exc).__name__})
            finally:
                store.close()
                with lock: workers.discard(worker_key)
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
            if parsed.path == '/agent':
                from .agent_ui import PAGE as AGENT_PAGE
                return self.respond(AGENT_PAGE.replace('__TOKEN__', json.dumps(token)), html=True)
            store = Store(root)
            try:
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path.startswith('/api/agent/'):
                    from . import agent, agent_tools
                    route = parsed.path.removeprefix('/api/agent/')
                    if route == 'sessions': result = agent.list_sessions(store)
                    elif route == 'catalog': result = agent_tools.catalog(agent.DEFAULT_POLICY)
                    else:
                        identity = query['session'][0]
                        state = agent.get(store, identity)
                        if route == 'session': result = agent.inspect(store, identity)
                        elif route == 'context':
                            from .long_horizon import read_context
                            result = read_context(store, identity, int(query['epoch'][0]), int(query.get('offset', ['0'])[0]), 20000)
                        elif route == 'artifact': result = agent_tools.read_text(agent.workdir(store, identity), query['path'][0], 0, 20000)
                        elif route == 'download':
                            path = agent_tools.checked_path(agent.workdir(store, identity), query['path'][0])
                            if path.stat().st_size > state['policy']['max_workspace_bytes']: raise ResearchError('Artifact exceeds quota')
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/octet-stream')
                            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(path.name))
                            self.send_header('Content-Length', str(path.stat().st_size))
                            self.send_header('Cache-Control', 'no-store')
                            self.send_header('X-Content-Type-Options', 'nosniff')
                            self.end_headers()
                            with path.open('rb') as source:
                                while True:
                                    chunk = source.read(65536)
                                    if not chunk: break
                                    self.wfile.write(chunk)
                            return
                        elif route == 'report':
                            report = next((r for r in state['reports'] if r['id'] == query['reference'][0]), None)
                            if not report: raise ResearchError('Unknown stage report')
                            result = {'report': report, 'markdown': store.blob(report['markdown_hash']).decode('utf-8')}
                        elif route == 'logs':
                            attempt = next((a for a in state['attempts'] if a['directory'] == query['attempt'][0]), None)
                            if not attempt: raise ResearchError('Unknown settled attempt')
                            path = agent.directory(store, identity) / 'attempts' / attempt['directory'] / 'supervisor'
                            result = {}
                            for name in ('stdout.txt', 'stderr.txt', 'result.json'):
                                if (path / name).is_file():
                                    with (path / name).open('rb') as source: result[name] = source.read(100000).decode('utf-8', errors='replace')
                        else: return self.respond({'error': 'not found'}, 404)
                elif parsed.path == '/api/runs':
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
                    elif parsed.path == '/api/report':
                        from .hci import read
                        result = read(store, run, query['stage'][0], query.get('report_id', [None])[0])
                    else: return self.respond({'error': 'not found'}, 404)
                self.respond(result)
            except (ResearchError, KeyError, OSError, ValueError, TypeError) as exc: self.respond({'error': str(exc)}, 400)
            finally: store.close()

        def do_POST(self):
            expected_origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin') != expected_origin or not hmac.compare_digest(self.headers.get('X-Research-Token', ''), token):
                return self.respond({'error': 'origin/token validation failed'}, 403)
            if self.path not in {'/api/action', '/api/agent/action'}: return self.respond({'error': 'not found'}, 404)
            store = Store(root)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= (22_000_000 if self.path == '/api/agent/action' else 100_000): raise ResearchError('invalid request length')
                body = json.loads(self.rfile.read(size))
                if self.path == '/api/agent/action':
                    from . import agent, long_horizon as horizon
                    action = body['action']
                    if action == 'project-create':
                        return self.respond(horizon.create(store, body['project'], body['objective'], constraints=body.get('constraints'),
                            budget=body.get('budget'), actor=body.get('actor', 'researcher')))
                    if action == 'create':
                        result = agent.create(store, body['objective'], body['config'], budget=body.get('budget'), policy=body.get('policy'), long_project=body.get('long_project') or None)
                        return self.respond({'id': result['id'], 'status': result['status']})
                    identity = body['session']
                    state = agent.get(store, identity)
                    if action.startswith('project-'):
                        if not state.get('long_project'): raise ResearchError('Session has no long-horizon project')
                        project = state['long_project']
                        if action == 'project-decide':
                            return self.respond(horizon.decide(store, project, body['text'], actor=body['actor'],
                                target=body.get('target') or None, expected_hash=body.get('expected_hash')))
                        if action == 'project-track':
                            result = horizon.track_job(store, project, body['run'], actor=body['actor'], cost=body.get('cost', 0))
                            start_worker(body['run'])
                            return self.respond(result)
                        if action == 'project-watch':
                            horizon.tick(store, project)
                            state = agent.get(store, identity)
                            if state['status'] in {'ready', 'waiting_external'}: start_worker(identity, agent_session=True)
                            return self.respond({'status': state['status']})
                        raise ResearchError('Unknown project action')
                    if action == 'fork':
                        result = agent.fork(store, identity, budget=body.get('budget'))
                        return self.respond({'id': result['id'], 'status': result['status']})
                    if action == 'run':
                        if agent.get(store, identity)['status'] != 'ready': raise ResearchError('Use Continue or resolve the pending request first')
                        start_worker(identity, agent_session=True); result = {'worker': 'requested'}
                    elif action in {'pause', 'cancel', 'resume'}:
                        result = agent.control(store, identity, action, actor=body.get('actor', 'researcher'), reason=body.get('reason', 'human console intervention'))
                        if action == 'resume': start_worker(identity, agent_session=True)
                    elif action == 'feedback':
                        result = agent.feedback(store, identity, **{k: body[k] for k in ('reference', 'actor', 'decision', 'reason')})
                        if result['status'] == 'ready': start_worker(identity, agent_session=True)
                    elif action == 'recover': result = agent.recover(store, identity, body.get('reconciliation'))
                    elif action == 'steer': result = agent.steer(store, identity, body['text'], actor=body.get('actor', 'researcher'))
                    elif action == 'import':
                        raw = base64.b64decode(body['base64'], validate=True)
                        if len(raw) > 16_000_000: raise ResearchError('Browser imports are limited to 16 MB per file')
                        result = agent.import_material(store, identity, body['path'], raw, actor=body.get('actor', 'researcher'))
                    else: raise ResearchError('Unknown Agent action')
                    return self.respond({'status': result.get('status'), 'result': result.get('requested', result.get('path', action))})
                run, action = body['run'], body['action']
                store.get(run)
                if action == 'run': start_worker(run); result = {'worker': 'requested'}
                elif action in {'pause', 'resume', 'step', 'cancel', 'breakpoint', 'retry'}:
                    result = store.control(run, action, body.get('reason', 'human console intervention'), body.get('stage'))
                    if action in {'resume', 'step', 'retry'}: start_worker(run)
                elif action == 'annotate': result = store.annotate(run, body['target'], body['text'])
                elif action == 'feedback':
                    from .hci import feedback
                    result = feedback(store, run, body['stage'], body['report_id'], body['actor'], body['decision'], body['reason'])
                elif action == 'revise':
                    from .hci import revise
                    result = revise(store, run, body['stage'], body['feedback_id'], body['changes'])
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
    print(f'Agent workbench: http://127.0.0.1:{server.server_port}/agent', flush=True)
    try: server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()
