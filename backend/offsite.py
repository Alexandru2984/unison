#!/usr/bin/env python3
"""Verified, encrypted off-host copies of the daily SQLite snapshots.

`upload` runs after each successful daily snapshot as a transient, unprivileged
user. It copies the newest snapshot into private storage, checks it, compresses
it deterministically and sends it through an rclone remote (an encrypting crypt
remote in production). It then downloads the archive and its manifest again,
restores the database in scratch space and verifies it before it applies
retention. Remote archives are never overwritten, and retention deletes only
this program's archive names while always keeping the newest copies.

`list` shows the remote archives. `fetch` is the operator's restore path: it
downloads an archive (the newest by default), checks it against its manifest and
writes a verified database file that is ready for the documented restore steps.
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

SNAPSHOT = re.compile(r'^evolution-(\d{8}T\d{6}Z)\.db$')
ARCHIVE = re.compile(r'^evolution-(\d{8}T\d{6}Z)\.db\.gz$')
REMOTE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$')
DIGEST = re.compile(r'^([0-9a-f]{64})  (\S+)$')
MAX_BYTES = 512 * 1024 * 1024
CHUNK = 1024 * 1024
RCLONE_TIMEOUT = 600


def remote_folder(value: str) -> str:
    """An rclone remote with a dedicated folder; never a remote's root or a parent path."""
    folder = value.rstrip('/')
    if not REMOTE.match(folder) or any(part in ('.', '..') for part in folder.split(':', 1)[1].split('/')):
        raise argparse.ArgumentTypeError('use NAME:folder with a dedicated folder below the remote root')
    return folder


def parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def create_private(path: Path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600), 'wb')


def copy_bounded(source, destination, limit: int) -> int:
    total = 0
    while block := source.read(CHUNK):
        total += len(block)
        if total > limit:
            raise SystemExit(f'Input exceeds the {limit} byte limit')
        destination.write(block)
    return total


def verify_database(path: Path) -> None:
    uri = path.resolve(strict=True).as_uri() + '?mode=ro&immutable=1'
    try:
        with closing(sqlite3.connect(uri, uri=True)) as database:
            healthy = database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            ideas = database.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ideas'").fetchone()
    except sqlite3.DatabaseError as error:
        raise SystemExit(f'{path.name} is not a readable SQLite database: {error}') from None
    if not healthy:
        raise SystemExit(f'{path.name} failed the SQLite integrity check')
    if not ideas:
        raise SystemExit(f'{path.name} is not an Idea Evolution database')


def gunzip_bounded(archive: Path, output: Path) -> None:
    try:
        with gzip.open(archive, 'rb') as source, create_private(output) as destination:
            copy_bounded(source, destination, MAX_BYTES)
    except (OSError, EOFError) as error:
        raise SystemExit(f'{archive.name} is not a complete gzip archive: {error}') from None


def newest_snapshot(directory: Path, max_age: timedelta, now: datetime) -> tuple[Path, str]:
    try:
        names = os.listdir(directory)
    except OSError as error:
        raise SystemExit(f'Cannot read snapshots in {directory}: {error.strerror}') from None
    found = sorted((match.group(1), name) for name in names if (match := SNAPSHOT.match(name)))
    if not found:
        raise SystemExit(f'No daily snapshot found in {directory}')
    stamp, name = found[-1]
    if not now - max_age <= parse_stamp(stamp) <= now + timedelta(minutes=5):
        raise SystemExit(f'The newest snapshot {name} is older than {max_age}; check unison-backup.service')
    return directory / name, stamp


def stage(source: Path, scratch: Path, stamp: str) -> dict:
    """Freeze the snapshot privately, verify it and build its deterministic archive."""
    database = scratch / source.name
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise SystemExit(f'{source.name} is not a regular file')
        with create_private(database) as copy:
            copy_bounded(handle, copy, MAX_BYTES)
    verify_database(database)
    archive = scratch / f'evolution-{stamp}.db.gz'
    with open(database, 'rb') as plain, create_private(archive) as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=9, mtime=0) as packed:
            shutil.copyfileobj(plain, packed, CHUNK)
    manifest = scratch / f'{archive.name}.sha256'
    with create_private(manifest) as handle:
        handle.write(f'{sha256(archive)}  {archive.name}\n{sha256(database)}  {database.name}\n'.encode())
    return {'archive': archive, 'manifest': manifest, 'database': database}


def read_manifest(path: Path, archive_name: str) -> dict[str, str]:
    entries = {}
    for line in path.read_text().splitlines():
        match = DIGEST.match(line)
        if not match:
            raise SystemExit(f'Malformed manifest {path.name}')
        entries[match.group(2)] = match.group(1)
    if set(entries) != {archive_name, archive_name.removesuffix('.gz')}:
        raise SystemExit(f'Manifest {path.name} does not describe {archive_name}')
    return entries


class Rclone:
    """rclone with explicit flags only; RCLONE_* variables from the caller are ignored."""

    def __init__(self, binary: str, seed: Path, scratch: Path):
        # rclone saves refreshed OAuth tokens, so it gets a private copy of the credential.
        config = scratch / 'rclone.conf'
        with open(seed, 'rb') as source, create_private(config) as copy:
            copy_bounded(source, copy, 1024 * 1024)
        self.base = [binary, '--config', str(config), '--cache-dir', str(scratch / 'cache'),
                     '--retries', '2', '--low-level-retries', '3', '--contimeout', '10s', '--timeout', '30s',
                     '--log-level', 'ERROR', '--max-transfer', '1Gi', '--cutoff-mode', 'hard']
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('RCLONE_')}

    def __call__(self, *args: str, capture: bool = False) -> str:
        result = subprocess.run([*self.base, *args], stdin=subprocess.DEVNULL, env=self.env, timeout=RCLONE_TIMEOUT,
                                stdout=subprocess.PIPE if capture else None, text=True, check=False)
        if result.returncode != 0:
            raise SystemExit(f'rclone {args[0]} failed with exit status {result.returncode}')
        return result.stdout or ''

    def archives(self, remote: str) -> dict[str, int]:
        listing = json.loads(self('lsjson', '--files-only', '--no-mimetype', '--no-modtime', remote, capture=True))
        return {item['Name']: item['Size'] for item in listing
                if ARCHIVE.match(item['Name']) or ARCHIVE.match(item['Name'].removesuffix('.sha256'))}


def plan_retention(stamps, keep_daily: int, keep_monthly: int, protect=()) -> list[str]:
    """Stamps to delete: everything except the newest copy of each of the newest
    `keep_daily` days and `keep_monthly` months, and the protected stamps."""
    kept, days, months = set(protect), set(), set()
    for stamp in sorted(set(stamps), reverse=True):
        if stamp[:8] not in days and len(days) < keep_daily:
            days.add(stamp[:8])
            kept.add(stamp)
        if stamp[:6] not in months and len(months) < keep_monthly:
            months.add(stamp[:6])
            kept.add(stamp)
    return sorted(set(stamps) - kept)


def verify_remote(rclone: Rclone, remote: str, name: str, scratch: Path) -> tuple[Path, dict[str, str]]:
    """Download an archive and its manifest, then restore and check the database."""
    downloaded = scratch / 'download'
    downloaded.mkdir(mode=0o700)
    archive, manifest = downloaded / name, downloaded / f'{name}.sha256'
    rclone('copyto', f'{remote}/{name}', str(archive))
    rclone('copyto', f'{remote}/{manifest.name}', str(manifest))
    digests = read_manifest(manifest, name)
    if sha256(archive) != digests[name]:
        raise SystemExit(f'Remote {name} does not match its manifest')
    restored = downloaded / name.removesuffix('.gz')
    gunzip_bounded(archive, restored)
    if sha256(restored) != digests[restored.name]:
        raise SystemExit(f'Remote {name} does not restore the database its manifest describes')
    verify_database(restored)
    return restored, digests


def upload(args) -> dict:
    now = datetime.now(timezone.utc)
    source, stamp = newest_snapshot(args.source, timedelta(hours=args.max_age_hours), now)
    # systemd runs one instance at a time; scratch left by a killed run holds plaintext.
    for stale in args.work.glob('offsite-*'):
        if stale.is_dir() and not stale.is_symlink():
            shutil.rmtree(stale)
    with tempfile.TemporaryDirectory(prefix='offsite-', dir=args.work) as directory:
        scratch = Path(directory)
        rclone = Rclone(args.rclone, args.config, scratch)
        staged = stage(source, scratch, stamp)
        name = staged['archive'].name
        # Existing archives are kept as they are and must verify against this snapshot.
        rclone('copyto', '--ignore-existing', str(staged['archive']), f'{args.remote}/{name}')
        rclone('copyto', '--ignore-existing', str(staged['manifest']), f'{args.remote}/{staged["manifest"].name}')
        _, digests = verify_remote(rclone, args.remote, name, scratch)
        if digests[source.name] != sha256(staged['database']):
            raise SystemExit(f'Remote {name} holds a different database than {source.name}; inspect it before retrying')
        present = rclone.archives(args.remote)
        stamps = {ARCHIVE.match(item).group(1) for item in present if ARCHIVE.match(item)}
        expired = plan_retention(stamps, args.keep_daily, args.keep_monthly, protect={stamp})
        deleted = []
        for old in expired:
            for item in (f'evolution-{old}.db.gz', f'evolution-{old}.db.gz.sha256'):
                if item in present:
                    rclone('deletefile', f'{args.remote}/{item}')
                    deleted.append(item)
    status = {'status': 'ok', 'verified_at': now.isoformat(timespec='seconds'), 'archive': name,
              'sha256': digests[name], 'bytes': present.get(name), 'remote_archives': len(stamps) - len(expired),
              'deleted': deleted}
    if args.state:
        fd, partial = tempfile.mkstemp(prefix='.status-', dir=args.state)
        with os.fdopen(fd, 'w') as handle:
            json.dump(status, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, args.state / 'status.json')
    return status


def list_archives(args) -> dict:
    with tempfile.TemporaryDirectory(prefix='offsite-') as directory:
        present = Rclone(args.rclone, args.config, Path(directory)).archives(args.remote)
    return {'archives': [{'name': name, 'bytes': size, 'manifest': f'{name}.sha256' in present}
                         for name, size in sorted(present.items()) if ARCHIVE.match(name)]}


def fetch(args) -> dict:
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise SystemExit(f'Refusing to overwrite {output}')
    with tempfile.TemporaryDirectory(prefix='offsite-') as directory:
        scratch = Path(directory)
        rclone = Rclone(args.rclone, args.config, scratch)
        name = args.name
        if name is None:
            archives = sorted(item for item in rclone.archives(args.remote) if ARCHIVE.match(item))
            if not archives:
                raise SystemExit(f'No archives in {args.remote}')
            name = archives[-1]
        restored, digests = verify_remote(rclone, args.remote, name, scratch)
        partial = output.with_name(f'.{output.name}.partial')
        partial.unlink(missing_ok=True)
        try:
            with open(restored, 'rb') as source, create_private(partial) as copy:
                copy_bounded(source, copy, MAX_BYTES)
                copy.flush()
                os.fsync(copy.fileno())
            if os.path.lexists(output):
                raise SystemExit(f'Refusing to overwrite {output}')
            os.replace(partial, output)
        finally:
            partial.unlink(missing_ok=True)
    return {'archive': name, 'database': str(output), 'sha256': digests[name.removesuffix('.gz')]}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    credentials = os.environ.get('CREDENTIALS_DIRECTORY')
    for command in ('upload', 'list', 'fetch'):
        sub = commands.add_parser(command)
        sub.add_argument('--remote', type=remote_folder, required=True, help='rclone remote folder, e.g. vault:apps/site')
        sub.add_argument('--config', type=Path, required=credentials is None,
                         default=Path(credentials, 'rclone.conf') if credentials else None)
        sub.add_argument('--rclone', default='/usr/bin/rclone')
        if command == 'upload':
            sub.add_argument('--source', type=Path, required=True, help='directory of daily snapshots')
            sub.add_argument('--work', type=Path, required='CACHE_DIRECTORY' not in os.environ,
                             default=os.environ.get('CACHE_DIRECTORY'), help='private, disk-backed scratch directory')
            sub.add_argument('--state', type=Path, default=os.environ.get('STATE_DIRECTORY'))
            sub.add_argument('--max-age-hours', type=float, default=36)
            sub.add_argument('--keep-daily', type=int, default=30)
            sub.add_argument('--keep-monthly', type=int, default=12)
        if command == 'fetch':
            sub.add_argument('--name', help='archive name (default: the newest)')
            sub.add_argument('--output', type=Path, required=True, help='new database file to write')
    args = parser.parse_args(argv)
    if args.command == 'upload':
        if args.keep_daily < 7 or args.keep_monthly < 1:
            parser.error('keep at least 7 daily and 1 monthly archives')
        args.work, args.state = Path(args.work), Path(args.state) if args.state else None
    if args.command == 'fetch' and args.name is not None and not ARCHIVE.match(args.name):
        parser.error('--name must be an evolution-<UTC stamp>.db.gz archive')
    result = {'upload': upload, 'list': list_archives, 'fetch': fetch}[args.command](args)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
