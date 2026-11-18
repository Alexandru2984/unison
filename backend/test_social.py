"""Reactions, live counters and discovery; temporary databases only."""
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import test_main
from test_main import main
from moderation import apply_rule
from social import WaterLedger, activity, discover_ids


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_main.ApiTests(methodName='runTest')
        self.fixture.setUp()
        self.client = self.fixture.client
        main.water_ledger = WaterLedger()

    def tearDown(self):
        self.fixture.tearDown()

    def create(self, *args, **kwargs):
        return self.fixture.create(*args, **kwargs)

    def hide(self, idea_id):
        with closing(main.connect_db()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            apply_rule(conn, idea_id, 'hide', 'spam', 'operator')
            conn.commit()

    def water(self, idea_id, **kwargs):
        return self.client.post(f'/api/idea/{idea_id}/water', json={}, **kwargs)

    def test_water_counts_once_per_connection_and_day(self):
        idea = self.create()
        with patch.object(main, 'broadcast_idea', new_callable=AsyncMock) as broadcast:
            first, again = self.water(idea['id']), self.water(idea['id'])
        self.assertEqual(first.json(), {'idea_id': idea['id'], 'water': 1, 'counted': True})
        self.assertEqual(again.json(), {'idea_id': idea['id'], 'water': 1, 'counted': False})
        broadcast.assert_awaited_once_with({'event': 'water', 'id': idea['id'], 'water': 1})
        self.assertEqual(self.client.get(f"/api/idea/{idea['id']}").json()['water'], 1)
        self.assertEqual(self.client.get('/api/stats').json()['water'], 1)
        # Another subscriber (a different ledger key) adds to the same total.
        with patch.object(main, 'client_key', return_value='198.51.100.7'):
            self.assertEqual(self.water(idea['id']).json()['water'], 2)

    def test_water_is_private_bounded_and_respects_moderation(self):
        idea = self.create()
        self.water(idea['id'])
        with closing(main.connect_db()) as conn:
            columns = [row['name'] for row in conn.execute('PRAGMA table_info(idea_water)')]
        self.assertEqual(columns, ['idea_id', 'day', 'count'])
        self.assertEqual(self.water(999).status_code, 404)
        self.hide(idea['id'])
        self.assertEqual(self.water(idea['id']).status_code, 404)
        self.assertEqual(self.client.get('/api/stats').json()['water'], 0)
        ledger = WaterLedger(max_entries=2)
        for idea_id in range(5):
            ledger.first_today('client', idea_id, '2026-11-18')
        self.assertEqual(len(ledger.seen), 2)
        self.assertNotIn(b'client', b''.join(ledger.seen))

    def test_water_uses_its_own_bucket_and_origin_rules(self):
        idea = self.create()
        self.assertEqual(self.water(idea['id'], headers={'Origin': 'https://evil.example'}).status_code, 403)
        with patch.object(main.limiters['water'], 'capacity', 0):
            self.assertEqual(self.water(idea['id']).status_code, 429)
            self.create('Writing is unaffected')

    def test_rows_carry_visible_branch_and_water_counts(self):
        root = self.create('Root')
        child = self.create('Child', parent_id=root['id'])
        hidden = self.create('Hidden child', parent_id=root['id'])
        self.assertEqual((root['children'], root['water']), (0, 0))
        self.hide(hidden['id'])
        self.water(root['id'])
        rows = {row['id']: row for row in self.client.get('/api/idea').json()}
        self.assertEqual((rows[root['id']]['children'], rows[root['id']]['water']), (1, 1))
        self.assertEqual(rows[child['id']]['children'], 0)
        self.assertEqual(self.client.get('/api/idea?leaves_only=true').json(), [rows[child['id']]])

    def test_discover_sections_exclude_hidden_ideas(self):
        old_seed = self.create('Old seed')
        branched = self.create('Branched seed')
        for text in ['one', 'two', 'three']:
            self.create(text, parent_id=branched['id'])
        deep = self.create('Deep', parent_id=old_seed['id'])
        deeper = self.create('Deeper', parent_id=deep['id'])
        self.water(deeper['id'])
        sections = self.client.get('/api/discover')
        self.assertEqual(sections.status_code, 200)
        self.assertIn('x-board-revision', sections.headers)
        data = {name: [row['id'] for row in rows] for name, rows in sections.json().items()}
        self.assertEqual(data['trending'], [deeper['id']])
        self.assertEqual(data['branching'][0], branched['id'])
        self.assertEqual(data['fresh'], [branched['id'], old_seed['id']])
        self.assertEqual(data['deepest'][0], deeper['id'])
        self.assertIn(deeper['id'], data['unexplored'])
        self.assertNotIn(branched['id'], data['unexplored'])
        self.hide(old_seed['id'])
        data = {name: [row['id'] for row in rows] for name, rows in self.client.get('/api/discover').json().items()}
        for ids in data.values():
            self.assertFalse({old_seed['id'], deep['id'], deeper['id']} & set(ids))

    def test_trending_uses_the_recent_window(self):
        idea = self.create()
        with closing(main.connect_db()) as conn:
            conn.execute("INSERT INTO idea_water(idea_id, day, count) VALUES(?, '2000-01-01', 50)", (idea['id'],))
            conn.commit()
            self.assertEqual(discover_ids(conn, main.MAX_DEPTH)['trending'], [])
            later = datetime(2000, 1, 3, tzinfo=timezone.utc)
            self.assertEqual(discover_ids(conn, main.MAX_DEPTH, later)['trending'], [idea['id']])

    def test_random_and_activity(self):
        self.assertEqual(self.client.get('/api/random').status_code, 404)
        idea = self.create()
        self.assertEqual(self.client.get('/api/random').json()['id'], idea['id'])
        self.hide(idea['id'])
        self.assertEqual(self.client.get('/api/random').status_code, 404)
        self.create('Visible')
        series = self.client.get('/api/stats').json()['activity']
        self.assertEqual(len(series), 30)
        self.assertEqual(series[-1], {'day': datetime.now(timezone.utc).date().isoformat(), 'ideas': 1})
        with closing(main.connect_db()) as conn:
            tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
            self.assertEqual(activity(conn, tomorrow)[-2]['ideas'], 1)


if __name__ == '__main__':
    unittest.main()
