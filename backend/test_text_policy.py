"""Unicode, link and duplicate-identity policy for public text."""
import unittest

from text_policy import PolicyError, clean_engine_text, clean_user_text, contains_link, content_key, normalize


class TextPolicyTests(unittest.TestCase):
    def rejected(self, text):
        with self.assertRaises(PolicyError):
            clean_user_text(text)

    def test_normalization_is_canonical_and_bounded(self):
        self.assertEqual(normalize('  a \r\nb\rc  \n\n\n\n\nd\u2028e  '), 'a\nb\nc\n\nd\ne')
        self.assertEqual(normalize('Gra\u0306dina\u0306'), 'Gr\u0103din\u0103')

    def test_direction_overrides_and_invisible_text_are_rejected(self):
        for text in ['safe \u202egnp.exe', 'a\u2066b\u2069', 'x\u202ay', '\u200b\u200b\u200b', 'hi\u2060there',
                     '\ufeffhello', 'soft\u00adhyphen', 'tag\U000e0041\U000e0042', '\u3164', '\u2800\u2800',
                     'ok\u115f', 'private \ue000 use', 'unassigned \U000effff']:
            with self.subTest(text=ascii(text)):
                self.rejected(text)

    def test_legitimate_scripts_and_emoji_are_accepted(self):
        for text in ['Gr\u0103din\u0103 \U0001f331 \u65e5\u672c\u8a9e', '\u05e9\u05dc\u05d5\u05dd \u200f!',
                     '\U0001f468\u200d\U0001f469\u200d\U0001f467 family', '\u2764\ufe0f love', '1\ufe0f\u20e3 first',
                     '\u0928\u092e\u0938\u094d\u0924\u0947', '\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645',
                     'e.g. Node.js, 3.14, C:\\notes\\tree, ș.a.m.d.']:
            with self.subTest(text=ascii(text)):
                self.assertTrue(clean_user_text(text))

    def test_stacked_combining_marks_are_bounded(self):
        self.assertTrue(clean_user_text('a\u0301\u0302\u0303'))
        self.rejected('x' + '\u0301' * 4)  # no precomposed x-acute, so NFC keeps all four
        self.rejected('Z' + '\u0301' * 500)

    def test_links_and_addresses_are_rejected(self):
        for text in ['buy https://spam.example now', 'see HTTP://x.y', 'www.example.org', 'visit example.com today',
                     'shop.example.ro/offer', 'mail me@example.com', 'mailto:a', 'bit.ly/abc', 't.me/channel',
                     'full width \uff57\uff57\uff57\uff0eexample', 'dotted example\u2024com', 'ftp://files']:
            with self.subTest(text=ascii(text)):
                self.assertTrue(contains_link(text))
                self.rejected(text)
        for text in ['Node.js and Deno', 'e.g. this', 'version 2.0', 'U.S. history', 'C:\\notes', 'end. Me too',
                     'co-op living', 'pi is 3.14']:
            with self.subTest(text=text):
                self.assertFalse(contains_link(text))

    def test_engine_output_is_checked_without_link_rules(self):
        self.assertEqual(clean_engine_text('From a view: a\r\nb'), 'From a view: a\nb')
        with self.assertRaises(PolicyError):
            clean_engine_text('x\u202ey')

    def test_content_key_ignores_case_width_and_spacing(self):
        self.assertEqual(content_key('A  Garden\n'), content_key('a garden'))
        self.assertEqual(content_key('\uff21 garden'), content_key('a garden'))
        self.assertNotEqual(content_key('a garden'), content_key('a gardens'))


if __name__ == '__main__':
    unittest.main()
