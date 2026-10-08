import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

import main


class FakeWebSocket:
    def __init__(self, origin: str | None):
        self.headers = {} if origin is None else {"origin": origin}
        self.accepted = False
        self.closed = None

    async def accept(self):
        self.accepted = True

    async def close(self, code, reason):
        self.closed = (code, reason)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = main.DB_PATH
        self.old_max_ideas = main.MAX_IDEAS
        self.old_max_results = main.MAX_RESULTS
        main.DB_PATH = Path(self.temp_dir.name) / "test.db"
        main.MAX_IDEAS = 100
        main.MAX_RESULTS = 500
        main.init_db()

    def tearDown(self):
        main.DB_PATH = self.old_db_path
        main.MAX_IDEAS = self.old_max_ideas
        main.MAX_RESULTS = self.old_max_results
        self.temp_dir.cleanup()

    def test_request_validation_bounds_mutation_and_content(self):
        with self.assertRaises(ValidationError):
            main.IdeaRequest(content="idea", mutation="arbitrary")
        with self.assertRaises(ValidationError):
            main.IdeaRequest(content="x" * 2_001)
        with self.assertRaises(ValidationError):
            main.IdeaRequest(content="   ")
        with self.assertRaises(ValidationError):
            main.IdeaRequest(mutation=main.Mutation.EXPAND)

    def test_base_idea_is_persisted_without_subprocess(self):
        with patch.object(main, "run_mutation") as mutation:
            result = asyncio.run(main.create_idea(main.IdeaRequest(content=" bounded idea ")))
        mutation.assert_not_called()
        self.assertEqual(result["content"], "bounded idea")
        self.assertEqual(asyncio.run(main.get_ideas()), [result])

    def test_unknown_parent_fails_before_subprocess(self):
        request = main.IdeaRequest(parent_id=999, mutation=main.Mutation.EXPAND)
        with patch.object(main, "run_mutation") as mutation:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.create_idea(request))
        mutation.assert_not_called()
        self.assertEqual(raised.exception.status_code, 404)

    def test_capacity_is_enforced(self):
        for index in range(100):
            asyncio.run(main.create_idea(main.IdeaRequest(content=f"idea-{index}")))
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.create_idea(main.IdeaRequest(content="one too many")))
        self.assertEqual(raised.exception.status_code, 507)

    def test_results_are_bounded_to_newest_rows(self):
        for index in range(12):
            asyncio.run(main.create_idea(main.IdeaRequest(content=f"idea-{index}")))
        main.MAX_RESULTS = 10
        results = asyncio.run(main.get_ideas())
        self.assertEqual(len(results), 10)
        self.assertEqual(results[0]["content"], "idea-2")
        self.assertEqual(results[-1]["content"], "idea-11")

    def test_cross_origin_websocket_is_rejected(self):
        websocket = FakeWebSocket("https://attacker.example")
        asyncio.run(main.websocket_endpoint(websocket))
        self.assertFalse(websocket.accepted)
        self.assertEqual(websocket.closed[0], 1008)

    def test_production_api_docs_are_disabled(self):
        self.assertIsNone(main.app.docs_url)
        self.assertIsNone(main.app.openapi_url)


if __name__ == "__main__":
    unittest.main()
