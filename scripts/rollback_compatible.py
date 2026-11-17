#!/usr/bin/env python3
"""Fail closed when an old API release would ignore existing hidden ideas."""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def compatible(release, database):
    if (Path(release) / 'moderation.py').is_file():
        return True
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(ideas)')}
        return 'hidden' not in columns or conn.execute('SELECT 1 FROM ideas WHERE hidden=1 LIMIT 1').fetchone() is None


if __name__ == '__main__':
    try:
        raise SystemExit(0 if compatible(sys.argv[1], sys.argv[2]) else 1)
    except (OSError, sqlite3.Error, IndexError):
        raise SystemExit(1)
