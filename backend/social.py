"""Anonymous reactions and discovery queries. No addresses or identifiers are stored."""
import hashlib
import hmac
import secrets
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

DISCOVER_LIMIT = 8
TRENDING_DAYS = 7
ACTIVITY_DAYS = 30


def utc_day(now=None):
    return (now or datetime.now(timezone.utc)).date().isoformat()


def init_social(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS idea_water (
            idea_id INTEGER NOT NULL REFERENCES ideas(id),
            day TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0 CHECK(count >= 0),
            PRIMARY KEY (idea_id, day)
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS water_day ON idea_water(day, idea_id);
    ''')


class WaterLedger:
    """Remembers who already watered an idea today, as keyed one-way digests in memory.

    A per-process secret means digests cannot be reversed or linked across
    restarts; a restart only forgets today's duplicates. Memory is bounded.
    """

    def __init__(self, max_entries=100_000):
        self.secret = secrets.token_bytes(32)
        self.max_entries = max_entries
        self.seen = OrderedDict()

    def first_today(self, client, idea_id, day):
        digest = hmac.new(self.secret, f'{day}|{client}|{idea_id}'.encode(), hashlib.blake2s).digest()[:12]
        if digest in self.seen:
            self.seen.move_to_end(digest)
            return False
        self.seen[digest] = None
        while len(self.seen) > self.max_entries:
            self.seen.popitem(last=False)
        return True


def water_total(conn, idea_id):
    return conn.execute('SELECT COALESCE(SUM(count), 0) FROM idea_water WHERE idea_id = ?', (idea_id,)).fetchone()[0]


def add_water(conn, idea_id, day):
    conn.execute('''INSERT INTO idea_water(idea_id, day, count) VALUES(?, ?, 1)
        ON CONFLICT(idea_id, day) DO UPDATE SET count = count + 1''', (idea_id, day))


def discover_ids(conn, max_depth, today=None):
    """Ordered idea IDs for each discovery section; every query excludes hidden ideas."""
    today = today or datetime.now(timezone.utc)
    since = (today - timedelta(days=TRENDING_DAYS - 1)).date().isoformat()
    limit = DISCOVER_LIMIT
    queries = {
        'trending': ('''SELECT i.id FROM ideas i JOIN (SELECT idea_id, SUM(count) AS recent FROM idea_water
                        WHERE day >= ? GROUP BY idea_id) w ON w.idea_id = i.id WHERE i.hidden = 0
                        ORDER BY w.recent DESC, i.id DESC LIMIT ?''', (since, limit)),
        'branching': ('''SELECT p.id FROM ideas p JOIN (SELECT parent_id, COUNT(*) AS branches FROM ideas
                         WHERE hidden = 0 AND parent_id IS NOT NULL GROUP BY parent_id) c ON c.parent_id = p.id
                         WHERE p.hidden = 0 ORDER BY c.branches DESC, p.id DESC LIMIT ?''', (limit,)),
        'unexplored': ('''SELECT i.id FROM ideas i WHERE i.hidden = 0 AND i.depth < ? AND NOT EXISTS
                          (SELECT 1 FROM ideas c WHERE c.parent_id = i.id AND c.hidden = 0)
                          ORDER BY i.id DESC LIMIT ?''', (max_depth, limit)),
        'fresh': ('SELECT id FROM ideas WHERE hidden = 0 AND parent_id IS NULL ORDER BY id DESC LIMIT ?', (limit,)),
        'deepest': ('''SELECT id FROM (SELECT id, depth, ROW_NUMBER() OVER (PARTITION BY root_id ORDER BY depth DESC, id DESC) AS rank
                       FROM ideas WHERE hidden = 0 AND depth > 0) WHERE rank = 1 ORDER BY depth DESC, id DESC LIMIT ?''', (limit,)),
    }
    return {name: [row[0] for row in conn.execute(sql, values)] for name, (sql, values) in queries.items()}


def activity(conn, today=None):
    """Visible ideas created per UTC day for the last ACTIVITY_DAYS days, oldest first."""
    today = (today or datetime.now(timezone.utc)).date()
    first = today - timedelta(days=ACTIVITY_DAYS - 1)
    counts = {row[0]: row[1] for row in conn.execute(
        '''SELECT substr(created_at, 1, 10) AS day, COUNT(*) FROM ideas
           WHERE hidden = 0 AND created_at >= ? GROUP BY day''', (first.isoformat(),))}
    return [{'day': (first + timedelta(days=offset)).isoformat(),
             'ideas': counts.get((first + timedelta(days=offset)).isoformat(), 0)} for offset in range(ACTIVITY_DAYS)]
