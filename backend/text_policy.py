"""Public text policy: normalization, abusive Unicode and link rejection.

Ideas are anonymous and public. These rules keep text visible, honest about its
direction and free of advertising links. Messages never echo submitted text.
"""
import hashlib
import re
import unicodedata

# Zero-width (non-)joiners build emoji/Indic/Persian text; LRM/RLM mark direction
# without overriding it. Every other format character (bidi embeddings, overrides
# and isolates, zero-width spaces, word joiners, BOM, soft hyphens and Unicode tag
# characters) is either invisible or can disguise the order of displayed text.
ALLOWED_FORMAT = frozenset('\u200c\u200d\u200e\u200f')
# Letters and symbols that render as blank space and enable "invisible" posts.
BLANK_LOOKALIKES = frozenset('\u115f\u1160\u3164\uffa0\u2800')
MAX_COMBINING_RUN = 3
LINE_SEPARATORS = str.maketrans({'\u2028': '\n', '\u2029': '\n', '\x85': '\n', '\v': '\n', '\f': '\n'})
LINK_TLDS = ('com|net|org|ro|io|ru|xyz|info|biz|top|me|co|app|dev|link|shop|site|online|click|ly|gg|tk|eu|uk|'
             'de|fr|es|nl|pl|us|ca|au|cn|br|tv|cc|ai|store|live|club|vip|pro|win|bet|casino|porn|sex|money|'
             'loan|cam|ml|ga|cf|gq|su|ws|icu|cyou|sbs|lol|buzz|fun|space|website|tech|page|blog|news|today')
LINK = re.compile(
    r'[a-z][a-z0-9+.\-]{1,20}://'
    r'|(?<![\w.])www\d{0,3}\.'
    r'|(?<![\w.])mailto:'
    rf'|(?<![\w.-])(?:[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?\.)+(?:{LINK_TLDS})(?![\w-])',
    re.IGNORECASE)


class PolicyError(ValueError):
    """A user-facing reason that never contains the submitted text."""


def normalize(text: str) -> str:
    """Canonical storage form: NFC, LF line endings, no trailing spaces, at most one blank line."""
    text = text.replace('\r\n', '\n').replace('\r', '\n').translate(LINE_SEPARATORS)
    text = unicodedata.normalize('NFC', text)
    text = '\n'.join(line.rstrip() for line in text.split('\n')).strip()
    return re.sub(r'\n{3,}', '\n\n', text)


def check_characters(text: str) -> None:
    combining, visible = 0, False
    for character in text:
        category = unicodedata.category(character)
        if category == 'Cc' and character not in '\n\t':
            raise PolicyError('Unsupported control character in content')
        if category in ('Cs', 'Co', 'Cn'):
            raise PolicyError('Content contains unsupported or private-use characters')
        if (category == 'Cf' and character not in ALLOWED_FORMAT) or character in BLANK_LOOKALIKES:
            raise PolicyError('Invisible or direction-changing characters are not allowed')
        if category in ('Mn', 'Me'):
            combining += 1
            if combining > MAX_COMBINING_RUN:
                raise PolicyError('Too many stacked accent marks')
        else:
            combining = 0
        if category[0] in 'LNSP':
            visible = True
    if not visible:
        raise PolicyError('Write at least one visible character')


def contains_link(text: str) -> bool:
    # NFKC folds full-width letters and look-alike dots (U+FF57, U+2024 ONE DOT LEADER).
    folded = unicodedata.normalize('NFKC', text)
    return LINK.search(folded) is not None


def clean_user_text(text: str) -> str:
    """Normalize and validate text written by a person."""
    text = normalize(text)
    check_characters(text)
    if contains_link(text):
        raise PolicyError('Links and web addresses are not allowed in public ideas')
    return text


def clean_engine_text(text: str) -> str:
    """Validate deterministic engine output; only legacy CR line endings are folded."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    check_characters(text)
    return text


def content_key(text: str) -> str:
    """Duplicate identity: compatibility-folded, case-insensitive, whitespace-collapsed."""
    folded = ' '.join(unicodedata.normalize('NFKC', text).casefold().split())
    return hashlib.sha256(folded.encode('utf-8')).hexdigest()
