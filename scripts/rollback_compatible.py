#!/usr/bin/env python3
"""Fail closed when an older API release could misrepresent the current database.

A release declares what it understands in `capabilities.json`. Releases without
that file predate it and understand the original five mutation values only.
"""
import json
import os
import pwd
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

LEGACY_MUTATIONS = frozenset({'base', 'expand', 'rephrase', 'mutate_keywords', 'synthesize'})


def declared_mutations(release):
    path = Path(release) / 'capabilities.json'
    if not path.is_file():
        return LEGACY_MUTATIONS
    mutations = json.loads(path.read_text())['mutations']
    if not isinstance(mutations, list) or not all(isinstance(item, str) for item in mutations):
        raise ValueError('Invalid capabilities file')
    return frozenset(mutations)


def compatible(release, database):
    release = Path(release)
    mutations = declared_mutations(release)
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(ideas)')}
        # A pre-moderation release would ignore the visibility flag and republish hidden text.
        if not (release / 'moderation.py').is_file() and 'hidden' in columns and \
                conn.execute('SELECT 1 FROM ideas WHERE hidden=1 LIMIT 1').fetchone() is not None:
            return False
        # Older browsers reject records whose transformation they do not know.
        if 'mutation' in columns:
            stored = {row[0] for row in conn.execute('SELECT DISTINCT mutation FROM ideas')}
            if not stored <= mutations:
                return False
    return True


if __name__ == '__main__':
    try:
        if os.geteuid() == 0:
            service = pwd.getpwnam('unisonapp')
            os.setgroups([])
            os.setgid(service.pw_gid)
            os.setuid(service.pw_uid)
        raise SystemExit(0 if compatible(sys.argv[1], sys.argv[2]) else 1)
    except (OSError, sqlite3.Error, IndexError, KeyError, ValueError):
        raise SystemExit(1)
