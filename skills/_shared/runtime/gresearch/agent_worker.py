"""One supervised native-model/tool attempt. Not a public authority endpoint."""
from pathlib import Path
import sys
import traceback

if __package__ in {None, ''}:
    # A script's own directory must not shadow stdlib statistics with our
    # gresearch/statistics.py when the operation gateway imports calculators.
    sys.path = [entry for entry in sys.path if Path(entry or '.').resolve() != Path(__file__).resolve().parent]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gresearch.core import ResearchError, Store, read_json, write_json


def main(path):
    request = read_json(path)
    output = Path(request['output'])
    try:
        if request['kind'] == 'model':
            from gresearch.agent_protocol import turn
            value = turn(request['config'], request['history'], request['tools'], request['receipt_dir'], request['prefix'])
        else:
            from gresearch.agent_tools import execute
            store = Store(request['store'])
            try: value = execute(store, request['session'], request['call'], Path(request['work']), request['policy'], request['approved'])
            finally: store.close()
        write_json(output, {'ok': True, 'value': value, 'attempt_token': request['attempt_token']})
    except Exception as exc:
        # Network/provider/plugin exceptions can contain credentials. Detailed
        # messages are retained only for our own validated ResearchError type.
        write_json(output, {'ok': False, 'error': str(exc)[:1000] if isinstance(exc, ResearchError) else type(exc).__name__,
                   'category': getattr(exc, 'category', type(exc).__name__), 'retryable': getattr(exc, 'retryable', False),
                   'retry_after': getattr(exc, 'retry_after', 0), 'attempt_token': request['attempt_token'],
                   'frames': [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name} for f in traceback.extract_tb(exc.__traceback__)]})
    return 0


if __name__ == '__main__': raise SystemExit(main(sys.argv[1]))
