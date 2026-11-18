"""Public idea pages, sitemap and feed; temporary databases only."""
import re
import unittest
import xml.etree.ElementTree as ET
from contextlib import closing

import test_main
from test_main import main
from moderation import apply_rule

OLD = '2026-01-01T00:00:00.000+00:00'


class ShareTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_main.ApiTests(methodName='runTest')
        self.fixture.setUp()
        self.client = self.fixture.client

    def tearDown(self):
        self.fixture.tearDown()

    def create(self, *args, **kwargs):
        return self.fixture.create(*args, **kwargs)

    def age(self, idea_id, created_at=OLD):
        with closing(main.connect_db()) as conn:
            conn.execute('UPDATE ideas SET created_at = ? WHERE id = ?', (created_at, idea_id))
            conn.commit()

    def report(self, idea_id):
        response = self.client.post(f'/api/idea/{idea_id}/report', json={'reason': 'spam'})
        self.assertEqual(response.status_code, 202, response.text)

    def hide(self, idea_id):
        with closing(main.connect_db()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            apply_rule(conn, idea_id, 'hide', 'spam', 'operator')
            conn.commit()

    def test_page_escapes_text_and_describes_the_idea(self):
        hostile = '<script>alert("x")</script> & "quotes" \'single\' </title>'
        root = self.create('A calm library')
        idea = self.create(hostile, parent_id=root['id'])
        self.client.post(f"/api/idea/{idea['id']}/water", json={})
        response = self.client.get(f"/i/{idea['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['content-type'].startswith('text/html'))
        body = response.text
        self.assertNotIn('<script>alert', body)
        self.assertNotIn('</title> &', body)
        self.assertIn('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &quot;quotes&quot;', body)
        self.assertIn(f'<link rel="canonical" href="https://unison.micutu.com/i/{idea["id"]}">', body)
        self.assertIn(f'href="/#idea-{idea["id"]}"', body)
        self.assertIn(f'href="/i/{root["id"]}"', body)
        self.assertIn('1 watering<', body)
        self.assertIn('0 branches', body)
        # The JSON-LD block cannot be closed by user text.
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', body, re.S).group(1)
        self.assertNotIn('<', block)
        self.assertIn('\\u003c/script\\u003e', block)
        self.assertEqual(len(re.findall('<script', body)), 1)

    def test_new_and_reported_pages_are_not_indexed(self):
        idea = self.create('Fresh thought')
        fresh = self.client.get(f"/i/{idea['id']}")
        self.assertIn('noindex', fresh.headers['x-robots-tag'])
        self.assertIn('<meta name="robots" content="noindex, nofollow">', fresh.text)
        self.age(idea['id'])
        mature = self.client.get(f"/i/{idea['id']}")
        self.assertNotIn('x-robots-tag', mature.headers)
        self.assertIn('content="index, follow"', mature.text)
        child = self.create('A branch', parent_id=idea['id'])
        self.age(child['id'])
        self.report(idea['id'])
        for idea_id in (idea['id'], child['id']):
            self.assertIn('noindex', self.client.get(f'/i/{idea_id}').headers['x-robots-tag'])
        legacy = self.create('Legacy seed')
        self.age(legacy['id'], None)
        self.assertNotIn('x-robots-tag', self.client.get(f"/i/{legacy['id']}").headers)

    def test_hidden_and_missing_ideas_return_noindex_404(self):
        idea = self.create('Soon hidden')
        child = self.create('Its branch', parent_id=idea['id'])
        self.hide(idea['id'])
        for path in (f"/i/{idea['id']}", f"/i/{child['id']}", '/i/999'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
            self.assertIn('noindex', response.headers['x-robots-tag'])
            self.assertNotIn('Soon hidden', response.text)
        self.assertEqual(self.client.get('/i/0').status_code, 422)
        self.assertEqual(self.client.head(f"/i/{idea['id']}").status_code, 404)

    def test_sitemap_lists_only_mature_unreported_visible_ideas(self):
        mature, fresh, reported, hidden = (self.create(text) for text in ('Mature', 'Fresh', 'Reported', 'Hidden'))
        reported_child = self.create('Reported child', parent_id=reported['id'])
        for idea in (mature, reported, hidden, reported_child):
            self.age(idea['id'])
        self.report(reported['id'])
        self.hide(hidden['id'])
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.headers['content-type'], 'application/xml')
        tree = ET.fromstring(response.content)
        locs = [el.text for el in tree.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertEqual(locs, ['https://unison.micutu.com/', f"https://unison.micutu.com/i/{mature['id']}"])
        self.assertIn('<lastmod>2026-01-01</lastmod>', response.text)

    def test_feed_is_valid_atom_of_mature_seeds(self):
        seed = self.create('A seed with <markup> & ampersands')
        branch = self.create('A branch', parent_id=seed['id'])
        self.create('Too fresh')
        for idea in (seed, branch):
            self.age(idea['id'])
        response = self.client.get('/feed.xml')
        self.assertEqual(response.headers['content-type'], 'application/atom+xml')
        atom = '{http://www.w3.org/2005/Atom}'
        tree = ET.fromstring(response.content)
        entries = tree.findall(f'{atom}entry')
        self.assertEqual([e.find(f'{atom}id').text for e in entries], [f"https://unison.micutu.com/i/{seed['id']}"])
        self.assertEqual(entries[0].find(f'{atom}content').text, 'A seed with <markup> & ampersands')
        self.assertEqual(tree.find(f'{atom}updated').text, OLD)

    def test_feed_and_sitemap_strip_characters_invalid_in_xml(self):
        idea = self.create('Legacy text')
        with closing(main.connect_db()) as conn:
            conn.execute('UPDATE ideas SET content = ?, created_at = NULL WHERE id = ?', ('bad\x01text\ufffe', idea['id']))
            conn.commit()
        tree = ET.fromstring(self.client.get('/feed.xml').content)
        self.assertEqual(tree.find('{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}content').text, 'badtext')


if __name__ == '__main__':
    unittest.main()
