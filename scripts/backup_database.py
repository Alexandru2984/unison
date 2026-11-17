#!/usr/bin/env python3
"""Make and verify a private, consistent SQLite online backup."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
source = args.source.resolve(strict=True)
args.destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd = os.open(args.destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
try:
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(args.destination)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup failed integrity check')
    print(f'Verified SQLite backup: {args.destination}')
except BaseException:
    args.destination.unlink(missing_ok=True)
    raise
