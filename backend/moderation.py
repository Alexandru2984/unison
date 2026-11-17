"""Private moderation storage and reversible subtree policy. No public admin API."""
from datetime import datetime, timezone
from enum import StrEnum


class ReportReason(StrEnum):
    SPAM = 'spam'
    HARASSMENT = 'harassment'
    PRIVACY = 'privacy'
    UNSAFE = 'unsafe'
    OTHER = 'other'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def init_moderation(conn):
    if 'hidden' not in {row['name'] for row in conn.execute('PRAGMA table_info(ideas)')}:
        conn.execute('ALTER TABLE ideas ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0')
    conn.executescript('''
        CREATE INDEX IF NOT EXISTS ideas_visible ON ideas(hidden, id);
        CREATE TABLE IF NOT EXISTS board_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO board_state(singleton, revision) VALUES(1, 0);
        CREATE TABLE IF NOT EXISTS idea_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id INTEGER NOT NULL REFERENCES ideas(id),
            reason TEXT NOT NULL CHECK(reason IN ('spam','harassment','privacy','unsafe','other')),
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved','dismissed')),
            created_at TEXT NOT NULL, closed_at TEXT, closed_by TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS reports_open_reason ON idea_reports(idea_id, reason) WHERE status='open';
        CREATE INDEX IF NOT EXISTS reports_status ON idea_reports(status, id);
        CREATE TABLE IF NOT EXISTS moderation_rules (
            idea_id INTEGER PRIMARY KEY REFERENCES ideas(id),
            reason TEXT NOT NULL, actor TEXT NOT NULL, changed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS moderation_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
            idea_id INTEGER, report_id INTEGER, reason TEXT NOT NULL,
            actor TEXT NOT NULL, affected INTEGER NOT NULL, created_at TEXT NOT NULL
        );
    ''')


def board_revision(conn):
    return conn.execute('SELECT revision FROM board_state WHERE singleton=1').fetchone()[0]


def apply_rule(conn, idea_id, action, reason, actor):
    """Caller owns BEGIN IMMEDIATE / commit, so visibility and revision agree."""
    row = conn.execute('SELECT id FROM ideas WHERE id=?', (idea_id,)).fetchone()
    if row is None:
        raise ValueError('Idea not found')
    existing = conn.execute('SELECT 1 FROM moderation_rules WHERE idea_id=?', (idea_id,)).fetchone()
    if (action == 'hide' and existing) or (action == 'restore' and not existing):
        return {'changed': False, 'affected': 0, 'revision': board_revision(conn)}
    timestamp = now()
    if action == 'hide':
        conn.execute('INSERT INTO moderation_rules(idea_id, reason, actor, changed_at) VALUES(?,?,?,?)',
                     (idea_id, reason, actor, timestamp))
    elif action == 'restore':
        conn.execute('DELETE FROM moderation_rules WHERE idea_id=?', (idea_id,))
    else:
        raise ValueError('Unsupported moderation action')
    before = conn.execute('SELECT COUNT(*) FROM ideas WHERE hidden=1').fetchone()[0]
    # UNION deduplicates IDs, terminating even for malformed legacy cycles.
    # Recompute from all active roots so restoring a parent cannot undo a
    # separate child moderation rule.
    conn.execute('''WITH RECURSIVE hidden_ids(id) AS (
        SELECT idea_id FROM moderation_rules UNION
        SELECT i.id FROM ideas i JOIN hidden_ids h ON i.parent_id=h.id)
        UPDATE ideas SET hidden=EXISTS(SELECT 1 FROM hidden_ids h WHERE h.id=ideas.id)''')
    after = conn.execute('SELECT COUNT(*) FROM ideas WHERE hidden=1').fetchone()[0]
    affected = abs(after - before)
    if action == 'hide':
        conn.execute("""UPDATE idea_reports SET status='resolved', closed_at=?, closed_by=?
            WHERE status='open' AND idea_id IN (SELECT id FROM ideas WHERE hidden=1)""", (timestamp, actor))
    conn.execute('UPDATE board_state SET revision=revision+1 WHERE singleton=1')
    conn.execute('''INSERT INTO moderation_audit(action,idea_id,reason,actor,affected,created_at)
        VALUES(?,?,?,?,?,?)''', (action, idea_id, reason, actor, affected, timestamp))
    return {'changed': True, 'affected': affected, 'revision': board_revision(conn)}


def close_report(conn, report_id, status, actor):
    if status not in ('resolved', 'dismissed'):
        raise ValueError('Unsupported report status')
    row = conn.execute('SELECT idea_id,reason,status FROM idea_reports WHERE id=?', (report_id,)).fetchone()
    if row is None:
        raise ValueError('Report not found')
    if row['status'] != 'open':
        return {'changed': False}
    timestamp = now()
    conn.execute('UPDATE idea_reports SET status=?,closed_at=?,closed_by=? WHERE id=?', (status, timestamp, actor, report_id))
    conn.execute('''INSERT INTO moderation_audit(action,idea_id,report_id,reason,actor,affected,created_at)
        VALUES(?,?,?,?,?,?,?)''', (status, row['idea_id'], report_id, row['reason'], actor, 1, timestamp))
    return {'changed': True}
