"""Exercise ownership, source pins and drift rejection with real local Git objects."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bundle_sync', ROOT / 'tools/bundle_sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class BundleSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gresearch-bundle-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        self.source.mkdir(); self.target.mkdir()
        self.git('init')
        self.git('config', 'user.name', 'Bundle fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.write(self.source, 'skills/example/SKILL.md', b'original\n')
        self.write(self.source, 'skills/_shared/runtime/research.py', b'engine-owned\n')
        self.write(self.source, 'README.md', b'product-owned\n')
        self.first = self.commit()
        self.write(self.target, 'product.json', b'{"product":"agent","dependency":"skills"}')

    def git(self, *args):
        result = subprocess.run(['git', '-c', 'safe.directory=' + self.source.as_posix(), '-C', str(self.source), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.decode().strip()

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def write(self, root, name, raw):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def initialize(self):
        return sync.synchronize(self.target, self.source, self.first, initialize=True)

    def test_snapshot_uses_commit_not_dirty_worktree_and_preserves_ownership(self):
        self.write(self.source, 'skills/example/SKILL.md', b'UNCOMMITTED\n')
        self.initialize()
        self.assertEqual((self.target / 'skills/example/SKILL.md').read_bytes(), b'original\n')
        self.assertFalse((self.target / 'skills/_shared/runtime/research.py').exists())
        self.assertFalse((self.target / 'README.md').exists())
        self.assertTrue(sync.verify(self.target, self.source)['source_verified'])

    def test_modified_or_added_generated_file_is_rejected_before_update(self):
        self.initialize()
        path = self.target / 'skills/example/SKILL.md'
        path.write_bytes(b'local scientific edits\n')
        with self.assertRaisesRegex(ValueError, 'drift'):
            sync.synchronize(self.target, self.source, self.first)
        self.assertEqual(path.read_bytes(), b'local scientific edits\n')
        path.write_bytes(b'original\n')
        self.write(self.target, 'skills/example/injected.py', b'pass\n')
        with self.assertRaisesRegex(ValueError, 'drift'):
            sync.verify(self.target)
        with self.assertRaisesRegex(ValueError, 'first migration'):
            sync.synchronize(self.target, self.source, self.first, initialize=True)

    def test_updated_and_removed_files_follow_new_commit_and_keep_local_product(self):
        self.initialize()
        self.write(self.target, 'README.md', b'local product\n')
        (self.source / 'skills/example/SKILL.md').unlink()
        self.write(self.source, 'skills/replacement/SKILL.md', b'new\n')
        revision = self.commit()
        sync.synchronize(self.target, self.source, revision)
        self.assertFalse((self.target / 'skills/example/SKILL.md').exists())
        self.assertEqual((self.target / 'README.md').read_bytes(), b'local product\n')
        self.assertEqual(sync.verify(self.target, self.source)['commit'], revision)

    def test_recomputed_local_lock_cannot_impersonate_pinned_source(self):
        self.initialize()
        self.write(self.target, 'skills/example/SKILL.md', b'forged\n')
        path = sync.lock_path(self.target, 'skills')
        lock = json.loads(path.read_text())
        lock['files'] = sync.inventory(sync.local_files(self.target, 'skills'))
        path.write_text(json.dumps(lock), encoding='utf-8')
        self.assertTrue(sync.verify(self.target)['valid'])
        with self.assertRaisesRegex(ValueError, 'pinned Git commit'):
            sync.verify(self.target, self.source)

    def test_runtime_export_excludes_skills_and_unsafe_pins_paths(self):
        self.write(self.target, 'product.json', b'{"product":"skill","dependency":"runtime"}')
        sync.synchronize(self.target, self.source, self.first, initialize=True)
        self.assertTrue((self.target / 'skills/_shared/runtime/research.py').is_file())
        self.assertFalse((self.target / 'skills/example/SKILL.md').exists())
        with self.assertRaisesRegex(ValueError, 'full 40'):
            sync.snapshot(self.source, 'HEAD', 'runtime')
        for path in ('../outside', '/absolute', 'C:/escape', 'skills\\..\\secret'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                sync.checked(self.target, path)


if __name__ == '__main__':
    unittest.main()
