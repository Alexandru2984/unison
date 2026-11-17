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


if __name__ == '__main__':
    unittest.main()
