"""HTTP, persistence, resource-boundary and subprocess regression tests.

Always use temporary databases, including during module import.
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

_IMPORT_STATE = tempfile.TemporaryDirectory()
os.environ['DB_PATH'] = str(Path(_IMPORT_STATE.name) / 'import.db')
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost,127.0.0.1,unison.micutu.com'
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
from fastapi import HTTPException
from fastapi.testclient import TestClient
import main
from security import RateLimiter


def core(value):
    """Strip live counters (branches, reactions) that change after a snapshot."""
    if isinstance(value, list):
        return [core(item) for item in value]
    return {key: item for key, item in value.items() if key not in ('children', 'water')}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = patch.object(main, 'DB_PATH', Path(self.temp_dir.name) / 'test.db')
        self.database.start()
        main.init_db()
        for limiter in [*main.limiters.values(), main.socket_limiter]:
            limiter.entries.clear()
        main.write_budget.clients.clear()
        main.write_budget.recent.clear()
        main.clients.clear()
        main.idea_lock = asyncio.Lock()
        main.mutation_slots = asyncio.Semaphore(2)
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.database.stop()
        self.temp_dir.cleanup()

    def create(self, content='A thoughtful community garden', **kwargs):
        response = self.client.post('/api/idea', json={'content': content, **kwargs})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_base_idea_persistence_and_safe_headers(self):
        with patch.object(main, 'run_mutation', new_callable=AsyncMock) as mutation:
            idea = self.create('  A garden  ')
        mutation.assert_not_called()
        self.assertEqual(idea['content'], 'A garden')
        self.assertEqual(idea['root_id'], idea['id'])
        self.assertIsNotNone(idea['created_at'])
        response = self.client.get('/api/idea')
        self.assertEqual(response.json(), [idea])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')

    def test_invalid_requests_do_not_echo_submitted_text(self):
        for payload in [{'content': 'sensitive', 'mutation': 'arbitrary'}, {'content': 'x' * 2001},
                        {'content': '   '}, {'mutation': 'expand'}, {'content': 'x\x00y'},
                        {'content': 'x\ud800y'}, {'content': 'x', 'parent_id': True},
                        {'content': 'x', 'unexpected': 'sensitive'}]:
            response = self.client.post('/api/idea', content=json.dumps(payload), headers={'Content-Type': 'application/json'})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertNotIn('sensitive', response.text)
        self.assertEqual(self.client.get('/api/stats').json()['total'], 0)

    def test_valid_unicode_and_json_characters(self):
        content = 'Grădină 🌱 "quoted" C:\\notes\nnew\tline\rnext'
        self.assertEqual(self.create(content)['content'], content.replace('\r', '\n'))

    def test_parent_integrity_for_custom_branches_and_mutations(self):
        for payload in [{'content': 'orphan', 'parent_id': 999}, {'parent_id': 999, 'mutation': 'expand'}]:
            with patch.object(main, 'run_mutation', new_callable=AsyncMock) as mutation:
                response = self.client.post('/api/idea', json=payload)
            self.assertEqual(response.status_code, 404)
            mutation.assert_not_called()
        root = self.create()
        child = self.create('A hand-written variation', parent_id=root['id'])
        self.assertEqual((child['root_id'], child['depth']), (root['id'], 1))
        self.assertEqual(core(self.client.get(f"/api/idea/{child['id']}/lineage").json()), core([root, child]))

    def test_mutation_uses_stored_parent(self):
        root = self.create()
        with patch.object(main, 'run_mutation', new_callable=AsyncMock, return_value='Expanded result') as mutation:
            response = self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'expand'})
        self.assertEqual(response.status_code, 201)
        mutation.assert_awaited_once_with(main.Mutation.EXPAND, root['content'])
        self.assertEqual(response.json()['depth'], 1)

    def test_depth_and_capacity_are_checked_before_engine(self):
        root = self.create()
        with closing(main.connect_db()) as conn:
            conn.execute('UPDATE ideas SET depth = ? WHERE id = ?', (main.MAX_DEPTH, root['id']))
            conn.commit()
        with patch.object(main, 'run_mutation', new_callable=AsyncMock) as mutation:
            self.assertEqual(self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'expand'}).status_code, 422)
            with patch.object(main, 'MAX_IDEAS', 1):
                self.assertEqual(self.client.post('/api/idea', json={'content': 'full'}).status_code, 507)
        mutation.assert_not_called()

    def test_idempotency_and_conflicts(self):
        headers = {'Idempotency-Key': 'a-unique-request-12345'}
        first = self.client.post('/api/idea', json={'content': 'one'}, headers=headers)
        second = self.client.post('/api/idea', json={'content': 'one'}, headers=headers)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.client.post('/api/idea', json={'content': 'two'}, headers=headers).status_code, 409)
        self.assertEqual(self.client.post('/api/idea', json={'content': 'one'}, headers={'Idempotency-Key': 'short'}).status_code, 422)
        self.assertEqual(self.client.get('/api/stats').json()['total'], 1)
        self.assertNotIn('request_key', first.json())

    def test_cursor_pagination_and_filters(self):
        rows = [self.create(f'idea-{i} 100%') for i in range(6)]
        page = self.client.get('/api/idea?limit=2')
        self.assertEqual(page.json(), rows[-2:])
        self.assertEqual(page.headers['x-has-more'], 'true')
        older = self.client.get('/api/idea', params={'before': page.headers['x-next-cursor'], 'limit': 2})
        self.assertEqual(older.json(), rows[2:4])
        self.assertEqual(self.client.get('/api/idea?after=2&limit=2').json(), rows[2:4])
        self.assertEqual(self.client.get('/api/idea?q=idea-3').json(), [rows[3]])
        self.assertEqual(len(self.client.get('/api/idea', params={'q': '%'}).json()), 6)
        self.assertEqual(self.client.get('/api/idea', params={'q': "%' OR 1=1 --"}).json(), [])
        self.assertEqual(self.client.get('/api/idea', params={'root_id': rows[0]['id']}).json(), [rows[0]])
        self.assertEqual(self.client.get('/api/idea?mutation=expand').json(), [])
        self.assertEqual(self.client.get('/api/idea?before=2&after=1').status_code, 422)
        self.assertEqual(self.client.get('/api/idea?limit=100000').status_code, 422)

    def test_missing_detail_and_lineage(self):
        self.assertEqual(self.client.get('/api/idea/999').status_code, 404)
        self.assertEqual(self.client.get('/api/idea/999/lineage').status_code, 404)

    def test_saved_ids_and_seed_filters_are_bounded(self):
        seed = self.create('seed')
        child = self.create('custom branch', parent_id=seed['id'])
        self.assertEqual(core(self.client.get('/api/idea?roots_only=true').json()), core([seed]))
        self.assertEqual(self.client.get('/api/idea', params={'ids': str(child['id'])}).json(), [child])
        for ids in ['0', '1,2,not-a-number', ','.join(['1'] * 101), '1) OR 1=1 --']:
            self.assertEqual(self.client.get('/api/idea', params={'ids': ids}).status_code, 422)

    def test_socket_capacity_is_enforced_before_accepting(self):
        with patch.object(main, 'MAX_CLIENTS', 0):
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect('/ws', headers={'Origin': main.PUBLIC_ORIGIN}):
                    pass
        self.assertFalse(main.clients)

    def test_stats_and_catalogue(self):
        self.create()
        stats = self.client.get('/api/stats').json()
        self.assertEqual((stats['total'], stats['seeds'], stats['max_depth']), (1, 1, 0))
        catalogue = self.client.get('/api/mutations').json()
        self.assertEqual([m['id'] for m in catalogue], [m.value for m in main.TRANSFORMATIONS])

    def test_cross_origin_and_form_writes_rejected(self):
        for origin in ['https://attacker.example', 'null']:
            self.assertEqual(self.client.post('/api/idea', json={'content': 'x'}, headers={'Origin': origin}).status_code, 403)
        self.assertEqual(self.client.post('/api/idea', data={'content': 'x'}).status_code, 415)
        self.assertEqual(self.client.post('/api/idea', json={'content': 'x'}, headers={'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.post('/api/idea', json={'content': 'same origin'}, headers={'Origin': main.PUBLIC_ORIGIN}).status_code, 201)

    def test_body_limits_with_and_without_length(self):
        response = self.client.post('/api/idea', content=' ' * 16_385, headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        response = self.client.post('/api/idea', content=iter([b' ' * 9000, b' ' * 9000]), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)

    def test_rate_limit_and_untrusted_host(self):
        with patch.object(main.write_limiter, 'capacity', 1), patch.object(main.write_limiter, 'refill', 0):
            self.create()
            response = self.client.post('/api/idea', json={'content': 'flood'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers['retry-after'], '30')
        self.assertEqual(self.client.get('/api/health', headers={'Host': 'evil.example'}).status_code, 400)
        self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_websocket_origin_updates_and_cleanup(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/ws', headers={'Origin': 'https://attacker.example'}):
                pass
        with self.client.websocket_connect('/ws', headers={'Origin': main.PUBLIC_ORIGIN}) as ws:
            idea = self.create()
            self.assertEqual(ws.receive_json(), {'event': 'ideas_changed'})
            ws.send_text('unsolicited')
            self.assertEqual(ws.receive()['code'], 1008)
        self.assertFalse(main.clients)

    def test_policy_rejections_explain_without_echoing_text(self):
        for content, message in [('secret https://spam.example', 'Links and web addresses'),
                                 ('secret \u202egnp', 'Invisible or direction-changing'),
                                 ('\u200b\u200b', 'Invisible or direction-changing'),
                                 ('secret' + '\u0301' * 9, 'stacked accent')]:
            response = self.client.post('/api/idea', json={'content': content})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn(message, response.json()['detail'][0]['message'])
            self.assertFalse(response.json()['detail'][0]['message'].startswith('Value error'))
            self.assertNotIn('secret', response.text)
        self.assertEqual(self.client.get('/api/stats').json()['total'], 0)

    def test_duplicate_seeds_and_branches_reuse_the_existing_idea(self):
        seed = self.create('A shared  Garden')
        again = self.client.post('/api/idea', json={'content': 'a shared garden'})
        self.assertEqual((again.status_code, again.headers.get('x-idea-duplicate')), (200, 'true'))
        self.assertEqual(again.json(), seed)
        branch = self.create('Rooftop beds', parent_id=seed['id'])
        self.assertEqual(self.client.post('/api/idea', json={'content': 'Rooftop  beds', 'parent_id': seed['id']}).json(), branch)
        # The same text elsewhere is a different idea.
        self.assertNotEqual(self.create('Rooftop beds')['id'], branch['id'])
        self.assertEqual(self.client.get('/api/stats').json()['total'], 3)

    def test_repeated_deterministic_mutation_skips_the_engine(self):
        root = self.create()
        with patch.object(main, 'run_mutation', new_callable=AsyncMock, return_value='Expanded result') as mutation:
            first = self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'expand'})
            second = self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'expand'})
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(second.headers['x-idea-duplicate'], 'true')
        self.assertEqual(first.json(), second.json())
        mutation.assert_awaited_once()
        # A different rule that reproduces existing sibling text is reused too.
        with patch.object(main, 'run_mutation', new_callable=AsyncMock, return_value='expanded  RESULT'):
            third = self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'rephrase'})
        self.assertEqual((third.status_code, third.json()['id']), (200, first.json()['id']))

    def test_moderated_text_cannot_be_republished(self):
        from moderation import apply_rule
        seed = self.create('Moderated words')
        with patch.object(main, 'run_mutation', new_callable=AsyncMock, return_value='Expanded words'):
            child = self.client.post('/api/idea', json={'parent_id': seed['id'], 'mutation': 'expand'}).json()
        with closing(main.connect_db()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            apply_rule(conn, child['id'], 'hide', 'spam', 'operator')
            conn.commit()
        with patch.object(main, 'run_mutation', new_callable=AsyncMock) as mutation:
            response = self.client.post('/api/idea', json={'parent_id': seed['id'], 'mutation': 'expand'})
        self.assertEqual(response.status_code, 409)
        mutation.assert_not_called()
        with closing(main.connect_db()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            apply_rule(conn, seed['id'], 'hide', 'spam', 'operator')
            conn.commit()
        self.assertEqual(self.client.post('/api/idea', json={'content': 'moderated  WORDS'}).status_code, 409)

    def test_daily_and_global_budgets_bound_new_ideas(self):
        with patch.object(main.write_budget, 'per_client_day', 2):
            self.create('one')
            self.create('two')
            self.assertEqual(self.client.post('/api/idea', json={'content': 'one'}).status_code, 200)
            response = self.client.post('/api/idea', json={'content': 'three'})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers['retry-after']), 0)
        self.assertIn('Daily limit', response.json()['detail'])
        main.write_budget.clients.clear()
        with patch.object(main.write_budget, 'global_hour', 2):
            response = self.client.post('/api/idea', json={'content': 'four'})
        self.assertEqual(response.status_code, 429)
        self.assertIn('growing very fast', response.json()['detail'])
        self.assertEqual(self.client.get('/api/stats').json()['total'], 2)

    def test_ipv6_clients_share_a_slash_64_budget(self):
        from security import client_key
        self.assertEqual(client_key('2001:db8:1:2:aaaa::1'), client_key('2001:db8:1:2:ffff::9'))
        self.assertNotEqual(client_key('2001:db8:1:2::1'), client_key('2001:db8:1:3::1'))
        self.assertEqual(client_key('::ffff:203.0.113.9'), '203.0.113.9')
        self.assertEqual(client_key('203.0.113.9'), '203.0.113.9')
        self.assertEqual(client_key(None), 'unknown')
        limiter = RateLimiter(capacity=2, per_minute=0)
        allowed = sum(limiter.allow(client_key(f'2001:db8::{i:x}')) for i in range(50))
        self.assertEqual(allowed, 2)

    def test_unchanged_branches_are_rejected(self):
        root = self.create('Same text')
        self.assertEqual(self.client.post('/api/idea', json={'content': 'Same text ', 'parent_id': root['id']}).status_code, 422)
        with patch.object(main, 'run_mutation', new_callable=AsyncMock, return_value='Same text'):
            response = self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'headline'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('unchanged', response.json()['detail'])

    def test_idea_preview_is_cached_and_marks_existing_branches(self):
        root = self.create('Plant a garden')
        results = {m.value: f'{m.value} result' for m in main.TRANSFORMATIONS}
        results['headline'] = 'Plant a garden'
        results['flip'] = None
        main.preview_cache.clear()
        with patch.object(main, 'run_mutation', new_callable=AsyncMock, return_value='expand result'):
            child = self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'expand'}).json()
        with patch.object(main, 'run_all', new_callable=AsyncMock, return_value=results) as engine:
            first = self.client.get(f"/api/idea/{root['id']}/preview")
            second = self.client.get(f"/api/idea/{root['id']}/preview")
        self.assertEqual(first.status_code, 200)
        engine.assert_awaited_once_with('Plant a garden')
        self.assertEqual(first.json(), second.json())
        rows = {row['mutation']: row for row in first.json()['results']}
        self.assertEqual(list(rows), [m.value for m in main.TRANSFORMATIONS])
        self.assertEqual(rows['expand']['existing_id'], child['id'])
        self.assertTrue(rows['headline']['unchanged'])
        self.assertIsNone(rows['flip']['content'])
        self.assertEqual(self.client.get('/api/idea/999/preview').status_code, 404)
        self.assertEqual(self.client.get('/api/stats').json()['total'], 2)

    def test_draft_preview_applies_policy_and_stores_nothing(self):
        results = {m.value: 'x' for m in main.TRANSFORMATIONS}
        with patch.object(main, 'run_all', new_callable=AsyncMock, return_value=results) as engine:
            response = self.client.post('/api/preview', json={'content': '  A draft  '})
            rejected = self.client.post('/api/preview', json={'content': 'see www.spam.example'})
        self.assertEqual(response.status_code, 200)
        engine.assert_awaited_once_with('A draft')
        self.assertEqual(len(response.json()['results']), len(main.TRANSFORMATIONS))
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(self.client.get('/api/stats').json()['total'], 0)
        with patch.object(main.limiters['preview'], 'capacity', 0):
            self.assertEqual(self.client.post('/api/preview', json={'content': 'again'}).status_code, 429)

    def test_docs_disabled(self):
        self.assertEqual(self.client.get('/docs').status_code, 404)
        self.assertEqual(self.client.get('/openapi.json').status_code, 404)

    def test_migration_is_additive_and_repeatable(self):
        legacy_path = Path(self.temp_dir.name) / 'legacy.db'
        with sqlite3.connect(legacy_path) as conn:
            conn.executescript('''CREATE TABLE ideas (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER, content TEXT NOT NULL, mutation TEXT NOT NULL);
                INSERT INTO ideas VALUES(1, NULL, 'seed', 'base');
                INSERT INTO ideas VALUES(2, 1, 'child', 'expand');''')
        with patch.object(main, 'DB_PATH', legacy_path):
            main.init_db()
            main.init_db()
            with closing(main.connect_db()) as conn:
                child = conn.execute('SELECT * FROM ideas WHERE id=2').fetchone()
                self.assertEqual((child['root_id'], child['depth'], child['created_at']), (1, 1, None))
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


from starlette.websockets import WebSocketDisconnect


class AsyncBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.script = self.path / 'engine'
        self.program = self.path / 'program.uc'
        self.program.touch()
        self.patches = [patch.object(main, 'UNISON_BIN', self.script), patch.object(main, 'UNISON_PROGRAM', self.program)]
        for item in self.patches:
            item.start()
        main.mutation_slots = asyncio.Semaphore(2)
        main.clients.clear()

    async def asyncTearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()
        main.clients.clear()

    def engine(self, code):
        self.script.write_text(f'#!{sys.executable}\n{code}\n')
        self.script.chmod(0o700)

    async def test_engine_strict_json_contract(self):
        self.engine('import json; print(json.dumps({"mutation":"expand", "result":"Grădină 🌱"}))')
        self.assertEqual(await main.run_mutation(main.Mutation.EXPAND, 'x'), 'Grădină 🌱')
        for code in ['print("raw text")', 'print("[]")', 'print(\'{"result": "x"}\')',
                     'import sys; sys.exit(1)', 'print(\'{"mutation":"expand","result":""}\')']:
            self.engine(code)
            with self.assertRaises(HTTPException) as error:
                await main.run_mutation(main.Mutation.EXPAND, 'x')
            self.assertEqual(error.exception.status_code, 502)

    async def test_all_mode_contract_drops_only_unusable_results(self):
        self.engine('import json; r={"expand":"ok","rephrase":"x\\u202ey","question":""}; '
                    'print(json.dumps({"mutation":"all","results":r}))')
        results = await main.run_all('x')
        self.assertEqual(results['expand'], 'ok')
        self.assertIsNone(results['rephrase'])
        self.assertIsNone(results['question'])
        self.assertIsNone(results['flip'])
        self.engine('import json; print(json.dumps({"mutation":"all","results":[]}))')
        with self.assertRaises(HTTPException):
            await main.run_all('x')

    async def test_output_cap_and_timeout(self):
        self.engine('print("x" * 1000000)')
        with self.assertRaises(HTTPException) as error:
            await main.run_mutation(main.Mutation.EXPAND, 'x')
        self.assertEqual(error.exception.status_code, 502)
        self.engine('import time; time.sleep(10)')
        with patch.object(main, 'MUTATION_TIMEOUT_SECONDS', 0.05):
            start = time.monotonic()
            with self.assertRaises(HTTPException) as error:
                await main.run_mutation(main.Mutation.EXPAND, 'x')
        self.assertEqual(error.exception.status_code, 504)
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(main.mutation_slots._value, 2)

    async def test_cancellation_reaps_child_and_releases_slot(self):
        pid_path = self.path / 'pid'
        self.engine(f'import os, time; open({str(pid_path)!r}, "w").write(str(os.getpid())); time.sleep(10)')
        task = asyncio.create_task(main.run_mutation(main.Mutation.EXPAND, 'x'))
        for _ in range(100):
            if pid_path.exists():
                break
            await asyncio.sleep(0.005)
        self.assertTrue(pid_path.exists())
        pid = int(pid_path.read_text())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertEqual(main.mutation_slots._value, 2)

    async def test_busy_engine_fails_without_unbounded_queue(self):
        self.engine('print("unused")')
        await main.mutation_slots.acquire()
        await main.mutation_slots.acquire()
        with self.assertRaises(HTTPException) as error:
            await main.run_mutation(main.Mutation.EXPAND, 'x')
        self.assertEqual(error.exception.status_code, 503)

    async def test_slow_socket_does_not_block_other_clients(self):
        slow, fast = AsyncMock(), AsyncMock()
        async def stalled(_idea):
            await asyncio.sleep(10)
        slow.send_json.side_effect = stalled
        main.clients.update({slow: 'slow', fast: 'fast'})
        started = time.monotonic()
        await main.broadcast_idea({'id': 1})
        self.assertLess(time.monotonic() - started, 0.9)
        fast.send_json.assert_awaited_once_with({'id': 1})
        self.assertNotIn(slow, main.clients)

    async def test_rate_limiter_memory_is_bounded(self):
        limiter = RateLimiter(capacity=1, max_clients=2)
        self.assertTrue(limiter.allow('one'))
        self.assertFalse(limiter.allow('one'))
        self.assertTrue(limiter.allow('two'))
        self.assertFalse(limiter.allow('three'))
        self.assertEqual(len(limiter.entries), 2)


if __name__ == '__main__':
    unittest.main()
