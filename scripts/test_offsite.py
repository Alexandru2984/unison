"""Off-host backup checks against a real rclone crypt remote on local disk; no network or production state."""
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
try:
    import offsite
finally:
    sys.path.pop(0)
RCLONE = shutil.which('rclone')


def stamp(moment: datetime) -> str:
    return f'{moment:%Y%m%dT%H%M%SZ}'


class RetentionTests(unittest.TestCase):
    def test_keeps_newest_copy_per_day_and_month(self):
        day = datetime(2026, 11, 18, 3, 17, tzinfo=timezone.utc)
        stamps = [stamp(day - timedelta(days=n)) for n in range(120)] + ['20261118T120000Z']
        doomed = offsite.plan_retention(stamps, keep_daily=30, keep_monthly=4)
        kept = sorted(set(stamps) - set(doomed))
        # The second copy of the newest day wins that day; the morning copy is replaced.
        self.assertIn('20261118T120000Z', kept)
        self.assertIn('20261118T031700Z', doomed)
        self.assertEqual(len({s[:8] for s in kept if s >= '20261020'}), 30)
        # Before the daily window only the newest snapshot of each month survives.
        self.assertEqual([s for s in kept if s < '20261020'], ['20260831T031700Z', '20260930T031700Z'])
        self.assertNotIn('20260721T031700Z', kept)

    def test_short_histories_and_protected_stamps_are_never_deleted(self):
        stamps = ['20261101T000000Z', '20261102T000000Z', '20261103T000000Z']
        self.assertEqual(offsite.plan_retention(stamps, keep_daily=7, keep_monthly=1), [])
        self.assertEqual(offsite.plan_retention(stamps, keep_daily=1, keep_monthly=1, protect={'20261101T000000Z'}),
                         ['20261102T000000Z'])

    def test_remote_must_be_a_dedicated_folder(self):
        self.assertEqual(offsite.remote_folder('vault:apps/unison.micutu.com/'), 'vault:apps/unison.micutu.com')
        for value in ('vault:', 'vault:/', 'vault:/abs', 'vault:apps/../other', 'vault:./x', ':apps', 'vault:a b', 'vault'):
            with self.subTest(value=value), self.assertRaises(Exception):
                offsite.remote_folder(value)


@unittest.skipUnless(RCLONE, 'rclone is not installed')
class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.source, self.work, self.state, self.store = (self.root / name for name in ('daily', 'work', 'state', 'store'))
        for directory in (self.source, self.work, self.state, self.store):
            directory.mkdir(mode=0o700)
        password = subprocess.run([RCLONE, 'obscure', 'test passphrase only'], capture_output=True, text=True, check=True).stdout.strip()
        self.config = self.root / 'rclone.conf'
        self.config.write_text(f'[store]\ntype = local\n\n[vault]\ntype = crypt\nremote = store:{self.store}\n'
                               f'password = {password}\nfilename_encryption = standard\ndirectory_name_encryption = true\n')
        self.remote = 'vault:apps/test.example'

    def snapshot(self, moment: datetime, rows: int = 3) -> Path:
        path = self.source / f'evolution-{stamp(moment)}.db'
        with closing(sqlite3.connect(path)) as database:
            database.execute('CREATE TABLE ideas(id INTEGER PRIMARY KEY, content TEXT)')
            database.executemany('INSERT INTO ideas(content) VALUES (?)', [(f'idea {n}',) for n in range(rows)])
            database.commit()
        return path

    def run_offsite(self, *args: str) -> dict:
        output = StringIO()
        with redirect_stdout(output):
            offsite.main([*args, '--remote', self.remote, '--config', str(self.config), '--rclone', RCLONE])
        return json.loads(output.getvalue())

    def upload(self, *extra: str) -> dict:
        return self.run_offsite('upload', '--source', str(self.source), '--work', str(self.work), '--state', str(self.state), *extra)

    def rclone(self, *args: str) -> str:
        return subprocess.run([RCLONE, '--config', str(self.config), *args], capture_output=True, text=True, check=True).stdout

    def test_upload_is_encrypted_verified_idempotent_and_restorable(self):
        snapshot = self.snapshot(datetime.now(timezone.utc) - timedelta(minutes=1))
        leftover = self.work / 'offsite-killed-run'
        leftover.mkdir()
        (leftover / snapshot.name).write_bytes(b'plaintext from an interrupted run')
        first = self.upload()
        self.assertEqual(first['archive'], snapshot.name + '.gz')
        self.assertEqual(first['remote_archives'], 1)
        self.assertEqual(json.loads((self.state / 'status.json').read_text())['sha256'], first['sha256'])
        stored = [p for p in self.store.rglob('*') if p.is_file()]
        self.assertEqual(len(stored), 2)
        for path in stored:
            self.assertNotIn('evolution', str(path.relative_to(self.store)))
            self.assertNotIn(b'SQLite format 3', path.read_bytes())
            self.assertNotIn(b'idea 1', path.read_bytes())
        self.assertEqual(list(self.work.iterdir()), [], 'scratch space must be removed')
        # A rerun keeps the existing archive and verifies it again.
        self.assertEqual(self.upload()['sha256'], first['sha256'])
        listing = self.run_offsite('list')['archives']
        self.assertEqual(listing, [{'name': first['archive'], 'bytes': first['bytes'], 'manifest': True}])
        restored = self.root / 'restore/evolution.db'
        restored.parent.mkdir()
        fetched = self.run_offsite('fetch', '--output', str(restored))
        self.assertEqual(fetched['archive'], first['archive'])
        self.assertEqual(restored.read_bytes(), snapshot.read_bytes())
        self.assertEqual(os.stat(restored).st_mode & 0o777, 0o600)
        with self.assertRaises(SystemExit):
            self.run_offsite('fetch', '--output', str(restored))

    def test_changed_remote_archive_fails_verification(self):
        snapshot = self.snapshot(datetime.now(timezone.utc) - timedelta(minutes=1))
        name = self.upload()['archive']
        forged = self.root / 'forged.db'
        shutil.copy(snapshot, forged)
        with closing(sqlite3.connect(forged)) as database:
            database.execute("UPDATE ideas SET content = 'tampered'")
            database.commit()
        packed = self.root / name
        packed.write_bytes(gzip.compress(forged.read_bytes(), mtime=0))
        self.rclone('copyto', str(packed), f'{self.remote}/{name}')
        with self.assertRaisesRegex(SystemExit, 'does not match its manifest'):
            self.upload()
        with self.assertRaisesRegex(SystemExit, 'does not match its manifest'):
            self.run_offsite('fetch', '--output', str(self.root / 'never.db'))
        self.assertFalse((self.root / 'never.db').exists())

    def test_truncated_archive_is_rejected(self):
        self.snapshot(datetime.now(timezone.utc) - timedelta(minutes=1), rows=2000)
        name = self.upload()['archive']
        local = self.root / 'copy.gz'
        self.rclone('copyto', f'{self.remote}/{name}', str(local))
        local.write_bytes(local.read_bytes()[:-64])
        self.rclone('copyto', str(local), f'{self.remote}/{name}')
        self.rclone('copyto', f'{self.remote}/{name}.sha256', str(self.root / 'manifest'))
        digest = offsite.sha256(local)
        manifest = (self.root / 'manifest').read_text().splitlines()
        (self.root / 'manifest').write_text(f'{digest}  {name}\n{manifest[1]}\n')
        self.rclone('copyto', str(self.root / 'manifest'), f'{self.remote}/{name}.sha256')
        with self.assertRaisesRegex(SystemExit, 'not a complete gzip archive'):
            self.run_offsite('fetch', '--output', str(self.root / 'never.db'))

    def test_stale_or_invalid_snapshots_are_not_uploaded(self):
        self.snapshot(datetime.now(timezone.utc) - timedelta(days=3))
        with self.assertRaisesRegex(SystemExit, 'older than'):
            self.upload()
        (self.source / f'evolution-{stamp(datetime.now(timezone.utc))}.db').write_bytes(b'not a database')
        with self.assertRaises(SystemExit):
            self.upload()
        self.assertEqual([p for p in self.store.rglob('*') if p.is_file()], [])

    def test_retention_only_removes_old_archives_of_this_program(self):
        now = datetime.now(timezone.utc)
        seeded = self.root / 'seeded'
        seeded.mkdir()
        for days in range(1, 13):
            name = f'evolution-{stamp(now - timedelta(days=days))}.db.gz'
            (seeded / name).write_bytes(b'old archive')
            (seeded / f'{name}.sha256').write_text('old manifest')
        (seeded / 'notes.txt').write_text('unrelated')
        (seeded / 'evolution-latest.db.gz').write_text('unrelated')
        self.rclone('copy', str(seeded), self.remote)
        self.snapshot(now - timedelta(minutes=1))
        result = self.upload('--keep-daily', '7', '--keep-monthly', '1')
        remaining = sorted(self.rclone('lsf', '--files-only', self.remote).split())
        archives = [n for n in remaining if offsite.ARCHIVE.match(n)]
        self.assertEqual(len(archives), result['remote_archives'])
        self.assertEqual(archives[-1], result['archive'])
        self.assertEqual(len(archives), 7)
        self.assertIn('notes.txt', remaining)
        self.assertIn('evolution-latest.db.gz', remaining)
        self.assertEqual(len(result['deleted']), 2 * 6)
        for name in archives:
            self.assertIn(f'{name}.sha256', remaining)


class UnitTests(unittest.TestCase):
    def test_offsite_unit_is_sandboxed_and_chained_after_snapshots(self):
        unit = (ROOT / 'infra/systemd/unison-offsite.service').read_text()
        for setting in ('DynamicUser=yes', 'SupplementaryGroups=unisonapp', 'ProtectSystem=strict', 'NoNewPrivileges=yes',
                        'LoadCredential=rclone.conf:/etc/unison-backend/offsite-rclone.conf', 'CapabilityBoundingSet=\n',
                        'ConditionPathExists=/etc/unison-backend/offsite-rclone.conf', 'InaccessiblePaths=/var/lib/unison-backend '):
            self.assertIn(setting, unit)
        self.assertNotRegex(unit, r'(?m)^(User|Group)=')
        self.assertIn('--remote gdrive-vps-crypt:apps/unison.micutu.com', unit)
        backup_unit = (ROOT / 'infra/systemd/unison-backup.service').read_text()
        self.assertIn('OnSuccess=unison-offsite.service', backup_unit)
        self.assertIn('UMask=0027', backup_unit)
        self.assertIn('StateDirectoryMode=0750', backup_unit)


if __name__ == '__main__':
    unittest.main()
