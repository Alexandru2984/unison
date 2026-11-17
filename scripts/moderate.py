#!/usr/bin/env python3
"""Local operator interface, authorized by SSH/sudo and database permissions."""
import argparse
import json
import os
import pwd
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
from moderation import ReportReason, apply_rule, close_report


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('Use a positive ID')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path('/var/lib/unison-backend/evolution.db'))
    actions = parser.add_subparsers(dest='action', required=True)
    queue = actions.add_parser('queue', help='List up to 100 private reports')
    queue.add_argument('--status', choices=['open', 'resolved', 'dismissed'], default='open')
    show = actions.add_parser('show', help='Inspect an idea, its visibility and direct rule')
    show.add_argument('id', type=positive)
    for name in ['hide', 'restore']:
        action = actions.add_parser(name, help=f'{name.title()} a branch reversibly')
        action.add_argument('id', type=positive)
        if name == 'hide': action.add_argument('--reason', choices=list(ReportReason), required=True)
    resolve = actions.add_parser('review', help='Resolve or dismiss a report without changing visibility')
    resolve.add_argument('id', type=positive)
    resolve.add_argument('--status', choices=['resolved', 'dismissed'], required=True)
    actions.add_parser('history', help='Show the latest 100 operator audit events')
    args = parser.parse_args()
    actor = pwd.getpwuid(os.getuid()).pw_name
    if os.geteuid() == 0:
        actor = os.environ.get('SUDO_USER') or actor
        service = pwd.getpwnam('unisonapp')
        # Never create root-owned WAL/SHM files that would lock the service out.
        os.setgroups([])
        os.setgid(service.pw_gid)
        os.setuid(service.pw_uid)
    os.umask(0o077)
    database = args.db.resolve(strict=True)
    writable = args.action in ('hide', 'restore', 'review')
    with closing(sqlite3.connect(database.as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        if args.action == 'queue':
            rows = conn.execute('''SELECT r.id AS report_id,r.idea_id,r.reason,r.status,r.created_at,
                i.hidden,substr(i.content,1,120) AS preview FROM idea_reports r JOIN ideas i ON i.id=r.idea_id
                WHERE r.status=? ORDER BY r.id LIMIT 100''', (args.status,)).fetchall()
            result = [dict(row) for row in rows]
        elif args.action == 'history':
            result = [dict(row) for row in conn.execute('SELECT * FROM moderation_audit ORDER BY id DESC LIMIT 100')]
        elif args.action == 'show':
            row = conn.execute('SELECT id,parent_id,content,mutation,hidden FROM ideas WHERE id=?', (args.id,)).fetchone()
            if row is None: raise ValueError('Idea not found')
            result = dict(row)
            rule = conn.execute('SELECT reason,actor,changed_at FROM moderation_rules WHERE idea_id=?', (args.id,)).fetchone()
            result['direct_rule'] = dict(rule) if rule else None
        else:
            conn.execute('BEGIN IMMEDIATE')
            if args.action == 'review':
                result = close_report(conn, args.id, args.status, actor)
            else:
                result = apply_rule(conn, args.id, args.action, args.reason if args.action == 'hide' else 'reviewed', actor)
            conn.commit()
        print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f'Moderation failed: {error}. Use the service account or sudo for the production database.', file=sys.stderr)
        raise SystemExit(1)
