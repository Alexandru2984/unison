"""Opt-in checks against the actual compiled Unison program (no database access)."""
import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARY = Path(os.getenv('UNISON_BIN', ROOT / 'ucm-bin/ucm-bin'))
PROGRAM = Path(os.getenv('UNISON_PROGRAM', ROOT / 'unison/evolution.uc'))


@unittest.skipUnless(os.getenv('RUN_ENGINE_TESTS') == '1', 'Set RUN_ENGINE_TESTS=1 after compiling Unison')
class EngineIntegrationTests(unittest.TestCase):
    def run_engine(self, mutation, text):
        result = subprocess.run([str(BINARY), 'run.compiled', str(PROGRAM), mutation, text],
                                capture_output=True, check=True, timeout=5)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['mutation'], mutation)
        return payload['result']

    def test_golden_transformations(self):
        self.assertEqual(self.run_engine('expand', 'A curious garden'),
                         'A curious (an important factor) garden (an important factor) -> Ultimately, this expands the core premise significantly.')
        self.assertEqual(self.run_engine('rephrase', 'one two three'), 'From a retrospective view: three two one.')
        self.assertEqual(self.run_engine('mutate_keywords', 'a garden grows'), 'MUTATION APPLIED: a GARDEN!! GROWS!!')
        self.assertEqual(self.run_engine('synthesize', 'one two three four'), 'Synthesis: one three')

    def test_json_characters_survive_all_transformations(self):
        for text in ['C:\\notes\\tree', '"quoted"', 'one\ttwo\rthree\nfour', 'Grădină 🌱 日本語', '\\"\\n literal']:
            for mutation in ['expand', 'rephrase', 'mutate_keywords', 'synthesize']:
                with self.subTest(text=text, mutation=mutation):
                    first = self.run_engine(mutation, text)
                    self.assertIsInstance(first, str)
                    self.assertEqual(first, self.run_engine(mutation, text))


if __name__ == '__main__':
    unittest.main()
