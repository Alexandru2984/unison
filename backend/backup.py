#!/usr/bin/env python3
"""Daily private SQLite backups with integrity checks and bounded retention.

Runs from the systemd timer as the service user. A snapshot is written under a
temporary name and only renamed into place after SQLite's integrity check, so
an interrupted run never counts toward retention.
"""
import argparse
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

NAME = re.compile(r'^evolution-\d{8}T\d{6}Z\.db$')


def snapshot(source: Path, destination: Path) -> None:
    partial = destination.with_name(f'.{destination.name}.partial')
    partial.unlink(missing_ok=True)
    # Group-readable so the off-host copy job (a member of this group only while it
    # runs) can read it; the directory is closed to everyone else.
    os.close(os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640))
    try:
        with closing(sqlite3.connect(source.resolve(strict=True).as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(partial)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup failed integrity check')
        os.replace(partial, destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def rotate(directory: Path, keep: int) -> list[str]:
    """Delete the oldest verified snapshots beyond `keep`; other files are never touched."""
    backups = sorted(p for p in directory.iterdir() if NAME.match(p.name) and p.is_file() and not p.is_symlink())
    removed = backups[:max(0, len(backups) - keep)]
    for path in removed:
        path.unlink()
    return [path.name for path in removed]


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--dir', type=Path, required=True)
    parser.add_argument('--keep', type=int, default=14)
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error('--keep must be at least 1')
    args.dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    destination = args.dir / f'evolution-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db'
    if destination.exists():
        raise SystemExit(f'Refusing to overwrite {destination.name}')
    snapshot(args.db, destination)
    removed = rotate(args.dir, args.keep)
    print(json.dumps({'backup': destination.name, 'bytes': destination.stat().st_size, 'removed': removed}))


if __name__ == '__main__':
    main()
