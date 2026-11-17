"""Opt-in checks against the actual compiled Unison program (no database access)."""
import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARY = Path(os.getenv('UNISON_BIN', ROOT / 'ucm-bin/ucm-bin'))
PROGRAM = Path(os.getenv('UNISON_PROGRAM', ROOT / 'unison/evolution.uc'))
MUTATIONS = ['expand', 'rephrase', 'mutate_keywords', 'synthesize', 'question', 'twist', 'headline', 'flip']


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

    def test_v2_golden_transformations(self):
        seed = 'Turn empty city rooftops into shared neighborhood gardens.'
        self.assertEqual(self.run_engine('question', seed),
                         'What if we turn empty city rooftops into shared neighborhood gardens?')
        self.assertEqual(self.run_engine('question', 'A library where people borrow skills.'),
                         'What if there were a library where people borrow skills?')
        self.assertEqual(self.run_engine('question', 'What if AI helped every small town?'),
                         'What would happen next if AI helped every small town?')
        self.assertEqual(self.run_engine('question', 'I want a calmer internet!'), 'What if I want a calmer internet?')
        self.assertEqual(self.run_engine('twist', seed),
                         'Twist: Turn empty city rooftops into shared neighborhood gardens, but where the audience becomes the creator.')
        self.assertEqual(self.run_engine('twist', 'Twist: A museum of unfinished ideas, but on a tiny island.'),
                         'Twist: A museum of unfinished ideas, but on a tiny island, but without any technology.')
        self.assertEqual(self.run_engine('headline', seed), 'Turn Empty City Rooftops into Shared Neighborhood Gardens')
        self.assertEqual(self.run_engine('headline', ' '.join(['word'] * 14)), ' '.join(['Word'] * 12) + '…')
        self.assertEqual(self.run_engine('headline', '!!'), '!!')
        self.assertEqual(self.run_engine('flip', 'Make repairing everyday objects EASY and cheap, ALWAYS.'),
                         'Flip side: Break repairing everyday objects HARD and expensive, NEVER.')
        self.assertEqual(self.run_engine('flip', 'Gardens grow'), 'Flip side: imagine the exact opposite of this. Gardens grow')

    def test_all_mode_matches_individual_rules(self):
        text = 'Grădină 🌱 "quoted" C:\\notes\nline\ttab'
        result = subprocess.run([str(BINARY), 'run.compiled', str(PROGRAM), 'all', text], capture_output=True, check=True, timeout=5)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['mutation'], 'all')
        self.assertEqual(set(payload['results']), set(MUTATIONS))
        for mutation in MUTATIONS:
            self.assertEqual(payload['results'][mutation], self.run_engine(mutation, text))

    def test_json_characters_survive_all_transformations(self):
        for text in ['C:\\notes\\tree', '"quoted"', 'one\ttwo\rthree\nfour', 'Grădină 🌱 日本語', '\\"\\n literal']:
            for mutation in MUTATIONS:
                with self.subTest(text=text, mutation=mutation):
                    first = self.run_engine(mutation, text)
                    self.assertIsInstance(first, str)
                    self.assertEqual(first, self.run_engine(mutation, text))


if __name__ == '__main__':
    unittest.main()
