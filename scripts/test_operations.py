"""Safety checks for the online backup command; no production state is read."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

SCRIPT = Path(__file__).resolve().with_name('backup_database.py')


class BackupTests(unittest.TestCase):
    def test_live_wal_backup_is_consistent_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, backup = root / 'live.db', root / 'private/snapshot.db'
            with closing(sqlite3.connect(database)) as source:
                source.execute('PRAGMA journal_mode=WAL')
                source.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, content TEXT)')
                source.execute('INSERT INTO records(content) VALUES (?)', ('committed',))
                source.commit()
                source.execute('INSERT INTO records(content) VALUES (?)', ('not yet committed',))
                result = subprocess.run([sys.executable, str(SCRIPT), str(database), str(backup)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                with closing(sqlite3.connect(backup)) as snapshot:
                    self.assertEqual(snapshot.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
                    self.assertEqual(snapshot.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(os.stat(backup).st_mode & 0o777, 0o600)

    def test_existing_backup_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, backup = root / 'source.db', root / 'backup.db'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE records(id INTEGER)')
            backup.write_bytes(b'preserve this backup')
            result = subprocess.run([sys.executable, str(SCRIPT), str(database), str(backup)], capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(backup.read_bytes(), b'preserve this backup')

class RollbackPolicyTests(unittest.TestCase):
    def test_old_release_cannot_expose_hidden_content(self):
        from rollback_compatible import compatible
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / 'release'
            release.mkdir()
            database = root / 'state.db'
            with closing(sqlite3.connect(database)) as conn:
                conn.execute('CREATE TABLE ideas(id INTEGER PRIMARY KEY, hidden INTEGER DEFAULT 0)')
                conn.execute('INSERT INTO ideas(id) VALUES(1)')
                conn.commit()
                self.assertTrue(compatible(release, database))
                conn.execute('UPDATE ideas SET hidden=1')
                conn.commit()
                self.assertFalse(compatible(release, database))
                (release / 'moderation.py').touch()
                self.assertTrue(compatible(release, database))

    def test_old_release_cannot_serve_unknown_transformations(self):
        from rollback_compatible import compatible
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, current = root / 'legacy', root / 'current'
            legacy.mkdir()
            current.mkdir()
            for release in (legacy, current):
                (release / 'moderation.py').touch()
            (current / 'capabilities.json').write_text('{"mutations": ["base", "expand", "twist"]}')
            database = root / 'state.db'
            with closing(sqlite3.connect(database)) as conn:
                conn.execute('CREATE TABLE ideas(id INTEGER PRIMARY KEY, mutation TEXT, hidden INTEGER DEFAULT 0)')
                conn.execute("INSERT INTO ideas(mutation) VALUES('expand')")
                conn.commit()
                self.assertTrue(compatible(legacy, database))
                conn.execute("INSERT INTO ideas(mutation) VALUES('twist')")
                conn.commit()
                self.assertFalse(compatible(legacy, database))
                self.assertTrue(compatible(current, database))
            (current / 'capabilities.json').write_text('{"mutations": "twist"}')
            with self.assertRaises(ValueError):
                compatible(current, database)

    def test_repository_capabilities_match_the_api(self):
        import json
        capabilities = json.loads((SCRIPT.parent.parent / 'backend/capabilities.json').read_text())
        source = (SCRIPT.parent.parent / 'backend/main.py').read_text()
        for mutation in capabilities['mutations']:
            self.assertIn(f"= '{mutation}'", source)



ROOT = Path(__file__).resolve().parents[1]


class PruneTests(unittest.TestCase):
    def layout(self, root: Path):
        api, site, runtime, backups = root / 'api', root / 'site', root / 'runtime', root / 'backups'
        for base in (api / 'releases', site / 'releases', runtime, backups):
            base.mkdir(parents=True)
        for index in range(12):
            for base in (api, site):
                release = base / 'releases' / f'rev{index:02d}-2026111{index % 10}T000000Z'
                release.mkdir()
                os.utime(release, (1_000_000 + index, 1_000_000 + index))
            (backups / f'202611{index + 1:02d}T000000Z').mkdir()
        for name in ('venv-aaaaaaaaaaaa', 'venv-bbbbbbbbbbbb', 'ucm-cccccccccccc', 'ucm-dddddddddddd'):
            (runtime / name).mkdir()
        (backups / 'not-a-backup').mkdir()
        newest = sorted((api / 'releases').iterdir())[-1]
        (newest / 'venv').symlink_to(runtime / 'venv-aaaaaaaaaaaa')
        (newest / 'runtime.env').write_text(f'APP_REVISION=x\nUNISON_BIN={runtime}/ucm-cccccccccccc/ucm-bin\n')
        oldest = sorted((api / 'releases').iterdir())[0]
        (api / 'current').symlink_to(oldest)
        return api, site, runtime, backups

    def run_prune(self, root, *extra):
        api, site, runtime, backups = (root / name for name in ('api', 'site', 'runtime', 'backups'))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/prune_releases.py'), '--api-root', str(api),
                                 '--site-root', str(site), '--runtime-root', str(runtime), '--backups', str(backups),
                                 '--keep-releases', '3', '--keep-backups', '4', *extra],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        import json
        return json.loads(result.stdout)

    def test_dry_run_plans_without_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api, *_ = self.layout(root)
            report = self.run_prune(root)
            self.assertFalse(report['applied'])
            # 12 releases: newest 3 plus the current (oldest) one are kept.
            self.assertEqual(len(report['api_releases']), 8)
            self.assertNotIn('rev00-20261110T000000Z', report['api_releases'])
            self.assertEqual(sorted(report['runtimes']), ['ucm-dddddddddddd', 'venv-bbbbbbbbbbbb'])
            self.assertEqual(len(report['backups']), 8)
            self.assertEqual(len(list((api / 'releases').iterdir())), 12)

    def test_apply_keeps_current_protected_and_referenced_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api, site, runtime, backups = self.layout(root)
            protected = sorted((site / 'releases').iterdir())[4]
            report = self.run_prune(root, '--apply', '--protect', str(protected), '--protect', str(backups / '20261101T000000Z'))
            self.assertTrue(report['applied'])
            self.assertEqual(len(list((api / 'releases').iterdir())), 4)
            self.assertTrue((api / 'current').resolve().is_dir())
            self.assertTrue(protected.is_dir())
            self.assertEqual(len(list((site / 'releases').iterdir())), 4)
            self.assertEqual(sorted(p.name for p in runtime.iterdir()), ['ucm-cccccccccccc', 'venv-aaaaaaaaaaaa'])
            self.assertTrue((backups / '20261101T000000Z').is_dir())
            self.assertTrue((backups / 'not-a-backup').is_dir())
            self.assertEqual(len([p for p in backups.iterdir() if p.name[0] == '2']), 5)

    def test_refuses_unsafe_retention(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/prune_releases.py'), '--keep-releases', '1'],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)


class DailyBackupTests(unittest.TestCase):
    def test_snapshots_are_verified_private_and_rotated(self):
        sys.path.insert(0, str(ROOT / 'backend'))
        try:
            import backup
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, target = root / 'live.db', root / 'daily'
            with closing(sqlite3.connect(database)) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE ideas(id INTEGER PRIMARY KEY)')
                conn.commit()
            target.mkdir(mode=0o700)
            for day in range(1, 5):
                (target / f'evolution-202611{day:02d}T031700Z.db').write_bytes(b'old')
            (target / 'keep-me.txt').write_text('unrelated')
            (target / '.evolution-20261105T000000Z.db.partial').write_bytes(b'interrupted')
            backup.main(['--db', str(database), '--dir', str(target), '--keep', '3'])
            names = sorted(p.name for p in target.iterdir())
            snapshots = [n for n in names if n.startswith('evolution-')]
            self.assertEqual(len(snapshots), 3)
            self.assertNotIn('evolution-20261101T031700Z.db', names)
            self.assertIn('keep-me.txt', names)
            newest = target / snapshots[-1]
            self.assertEqual(os.stat(newest).st_mode & 0o777, 0o640)
            with closing(sqlite3.connect(newest)) as copy:
                self.assertEqual(copy.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


class ReleaseRuntimeTests(unittest.TestCase):
    def test_lock_pins_every_requirement_with_hashes(self):
        import re
        pins = lambda text: {m.group(1).lower().replace('_', '-'): m.group(2)
                             for m in re.finditer(r'^([A-Za-z0-9_.-]+)==(\S+)', text, re.M)}
        lock = (ROOT / 'backend/requirements.lock').read_text()
        self.assertEqual(pins(lock), pins((ROOT / 'backend/requirements.txt').read_text()))
        for block in re.split(r'\n(?=[A-Za-z0-9])', lock.split('\n', 6)[-1]):
            if re.match(r'^[A-Za-z0-9]', block):
                self.assertIn('--hash=sha256:', block, block.split()[0])

    def test_service_runs_only_from_release_paths(self):
        unit = (ROOT / 'unison-backend.service').read_text()
        self.assertNotIn('/home/', unit)
        self.assertIn('ExecStart=/opt/unison-backend/current/venv/bin/uvicorn ', unit)
        self.assertIn('ProtectHome=yes', unit)
        backup_unit = (ROOT / 'infra/systemd/unison-backup.service').read_text()
        for setting in ('User=unisonapp', 'PrivateNetwork=yes', 'ProtectSystem=strict', 'NoNewPrivileges=yes'):
            self.assertIn(setting, backup_unit)


if __name__ == '__main__':
    unittest.main()
