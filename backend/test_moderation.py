import asyncio
import json
import os
import pwd
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_main
from test_main import main
from moderation import apply_rule, board_revision


class ModerationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_main.ApiTests(methodName='runTest')
        self.fixture.setUp()
        self.client = self.fixture.client

    def tearDown(self):
        self.fixture.tearDown()

    def create(self, *args, **kwargs):
        return self.fixture.create(*args, **kwargs)

    def rule(self, idea_id, action='hide'):
        with closing(main.connect_db()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            result = apply_rule(conn, idea_id, action, 'spam' if action == 'hide' else 'reviewed', 'operator')
            conn.commit()
        return result

    def cli(self, *args, success=True):
        command = [sys.executable, str(Path(__file__).resolve().parent.parent / 'scripts/moderate.py'), '--db', str(main.DB_PATH), *args]
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, env={**os.environ, 'SUDO_USER': 'untrusted-override'})
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result

    def test_reports_are_private_deduplicated_and_do_not_hide_content(self):
        idea = self.create()
        with patch.object(main, 'broadcast_idea', new_callable=AsyncMock) as broadcast:
            for _ in range(2):
                response = self.client.post(f"/api/idea/{idea['id']}/report", json={'reason': 'privacy'})
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json(), {'status': 'received'})
            broadcast.assert_not_called()
        with closing(main.connect_db()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM idea_reports').fetchone()[0], 1)
        self.assertEqual(self.client.get('/api/idea').json(), [idea])
        self.assertEqual(self.client.get('/api/stats').json()['total'], 1)
        for route in ['/api/reports', '/api/moderation', '/api/admin']:
            self.assertEqual(self.client.get(route).status_code, 404)

    def test_report_validation_limits_and_unknown_ideas(self):
        idea = self.create()
        for payload in [{'reason': 'arbitrary'}, {'reason': 'spam', 'details': 'private text'}, {}]:
            self.assertEqual(self.client.post(f"/api/idea/{idea['id']}/report", json=payload).status_code, 422)
        self.assertEqual(self.client.post('/api/idea/999/report', json={'reason': 'spam'}).status_code, 404)
        with patch.object(main, 'MAX_REPORTS', 0):
            self.assertEqual(self.client.post(f"/api/idea/{idea['id']}/report", json={'reason': 'spam'}).status_code, 503)
        self.assertEqual(self.client.post(f"/api/idea/{idea['id']}/report", json={'reason': 'spam'}, headers={'Origin': 'https://evil.example'}).status_code, 403)

    def test_hidden_subtree_is_absent_from_every_public_read(self):
        root = self.create('sensitive ancestor')
        child = self.create('sensitive descendant', parent_id=root['id'])
        other = self.create('visible seed')
        self.assertEqual(self.rule(root['id'])['affected'], 2)
        for query in ['', '?q=sensitive', f"?root_id={root['id']}", f"?ids={root['id']},{child['id']}", '?after=0', '?before=999', '?mutation=base', '?roots_only=true']:
            response = self.client.get('/api/idea'+query)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('sensitive', response.text)
            self.assertEqual(response.headers['x-board-revision'], '1')
        for idea in [root, child]:
            for suffix in ['', '/lineage']:
                self.assertEqual(self.client.get(f"/api/idea/{idea['id']}{suffix}").status_code, 404)
            self.assertEqual(self.client.post(f"/api/idea/{idea['id']}/report", json={'reason': 'spam'}).status_code, 404)
        summary = self.client.get('/api/stats').json()
        self.assertEqual((summary['total'], summary['seeds'], summary['board_revision']), (1, 1, 1))
        self.assertEqual(self.client.get('/api/idea').json(), [other])

    def test_hidden_parents_and_hidden_idempotent_replays_are_rejected(self):
        headers = {'Idempotency-Key': 'private-replay-key-123'}
        root = self.client.post('/api/idea', json={'content': 'hidden original'}, headers=headers).json()
        self.rule(root['id'])
        self.assertEqual(self.client.post('/api/idea', json={'content': 'hidden original'}, headers=headers).status_code, 404)
        with patch.object(main, 'run_mutation', new_callable=AsyncMock) as mutation:
            self.assertEqual(self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'expand'}).status_code, 404)
            mutation.assert_not_called()
        self.assertEqual(self.client.post('/api/idea', json={'content': 'new', 'parent_id': root['id']}).status_code, 404)

    def test_parent_hidden_while_engine_runs_cannot_gain_visible_child(self):
        root = self.create()
        async def racing_mutation(*_):
            self.rule(root['id'])
            return 'must not persist'
        with patch.object(main, 'run_mutation', side_effect=racing_mutation):
            response = self.client.post('/api/idea', json={'parent_id': root['id'], 'mutation': 'expand'})
        self.assertEqual(response.status_code, 404)
        with closing(main.connect_db()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM ideas').fetchone()[0], 1)

    def test_restoring_parent_preserves_independently_hidden_child(self):
        root = self.create()
        child = self.create('child', parent_id=root['id'])
        grandchild = self.create('grandchild', parent_id=child['id'])
        self.rule(child['id'])
        self.rule(root['id'])
        result = self.rule(root['id'], 'restore')
        self.assertEqual(result['affected'], 1)
        self.assertEqual(self.client.get('/api/idea').json(), [root])
        self.assertFalse(self.rule(root['id'], 'restore')['changed'])
        self.rule(child['id'], 'restore')
        self.assertEqual(self.client.get('/api/idea').json(), [root, child, grandchild])
        with closing(main.connect_db()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM moderation_audit').fetchone()[0], 4)

    def test_cli_review_hiding_and_history_use_os_identity(self):
        root = self.create()
        self.client.post(f"/api/idea/{root['id']}/report", json={'reason': 'spam'})
        queue = self.cli('queue')
        self.assertEqual(len(queue), 1)
        self.assertTrue(self.cli('review', str(queue[0]['report_id']), '--status', 'dismissed')['changed'])
        self.assertEqual(self.cli('queue'), [])
        self.assertTrue(self.cli('hide', str(root['id']), '--reason', 'spam')['changed'])
        self.assertEqual(self.cli('show', str(root['id']))['hidden'], 1)
        history = self.cli('history')
        self.assertEqual(history[0]['actor'], pwd.getpwuid(os.getuid()).pw_name)
        self.assertTrue(self.cli('restore', str(root['id']))['changed'])
        self.cli('hide', '999', '--reason', 'spam', success=False)

    def test_oversized_sqlite_ids_are_rejected_without_server_errors(self):
        huge = 2**63
        self.assertEqual(self.client.post('/api/idea', json={'content': 'x', 'parent_id': huge}).status_code, 422)
        for path in [f'/api/idea/{huge}', f'/api/idea/{huge}/lineage']:
            self.assertEqual(self.client.get(path).status_code, 422)
        self.assertEqual(self.client.post(f'/api/idea/{huge}/report', json={'reason': 'spam'}).status_code, 422)
        for parameter in ['before', 'after', 'root_id']:
            self.assertEqual(self.client.get('/api/idea', params={parameter: huge}).status_code, 422)
        self.cli('show', str(huge), success=False)

    def test_socket_notification_has_no_moderated_text(self):
        root = self.create('never broadcast this hidden text')
        with self.client.websocket_connect('/ws', headers={'Origin': main.PUBLIC_ORIGIN}) as socket:
            self.rule(root['id'])
            with patch.object(main, 'MODERATION_POLL_SECONDS', 0.01):
                event = socket.receive_json()
            self.assertEqual(event, {'event': 'board_changed', 'revision': 1})
            self.assertNotIn(root['content'], json.dumps(event))


if __name__ == '__main__':
    unittest.main()
