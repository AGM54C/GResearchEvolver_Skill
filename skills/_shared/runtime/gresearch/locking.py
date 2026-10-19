"""Cooperative, process-lifetime locks for a single-host local store.

Lock files are never removed: unlinking one while another process has it open
would create two independent locks. Network filesystems are not supported.
"""
from contextlib import contextmanager
import os

from .core import ResearchError, valid_id


class LockBusy(ResearchError):
    pass


@contextmanager
def file_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockBusy('Resource has an active owner: ' + path.name) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def resource_lock(store, kind, identity):
    return file_lock(store.root / 'locks' / (valid_id(kind) + '-' + valid_id(identity) + '.lock'))
