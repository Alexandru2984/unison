"""Server-rendered public idea pages, sitemap and Atom feed.

Crawlers and link previews get real HTML without JavaScript. New ideas and
anything under an open report stay out of search engines: a page is indexable
only 48 hours after creation and while neither it nor an ancestor has an open
report. Hidden ideas do not exist here at all.
"""
import html
import json
import re
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Annotated
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Path
from fastapi.responses import HTMLResponse, Response

INDEX_AFTER = timedelta(hours=48)
SITEMAP_LIMIT = 5000
FEED_LIMIT = 30
CHILD_LIMIT = 24
MAX_SQLITE_ID = 9_223_372_036_854_775_807
# Ideas from before timestamps were recorded have no creation time.
LEGACY_UPDATED = '2026-11-17T00:00:00+00:00'
RULE_NAMES = {'base': 'Seed idea', 'expand': 'Expand', 'rephrase': 'Rephrase', 'mutate_keywords': 'Amplify',
              'synthesize': 'Synthesize', 'question': 'Question', 'twist': 'Twist', 'headline': 'Headline', 'flip': 'Flip'}
# Ideas under an open report, and every branch grown from them.
FLAGGED = '''WITH RECURSIVE flagged(id) AS (
    SELECT idea_id FROM idea_reports WHERE status = 'open'
    UNION SELECT i.id FROM ideas i JOIN flagged f ON i.parent_id = f.id)'''
XML_INVALID = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')
PAGE_STYLE = '''
:root{color-scheme:light dark;--bg:#f8f9f6;--surface:#fff;--soft:#f3f5f0;--text:#24372c;--muted:#5f6d63;--border:#e0e6dc;--accent:#2c543c;--on-accent:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#121a15;--surface:#1a251f;--soft:#223027;--text:#e3eadf;--muted:#a9b8ab;--border:#33433a;--accent:#c8e6ae;--on-accent:#14201a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
a{color:inherit}main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
.brand{display:inline-flex;gap:10px;align-items:center;font-weight:760;font-size:19px;text-decoration:none}
.mark{width:34px;height:34px;border-radius:10px;background:#dceacb;color:#30513b;display:grid;place-items:center;font-size:15px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:22px;margin:22px 0}
.meta{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;color:var(--muted);font-size:14px}
.tag{background:var(--soft);border-radius:8px;padding:2px 9px;font-weight:650;color:var(--text)}
.idea{font-size:clamp(21px,4.6vw,28px);line-height:1.4;font-weight:620;letter-spacing:-.3px;white-space:pre-wrap;overflow-wrap:anywhere;margin:14px 0}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
.button{display:inline-flex;align-items:center;min-height:46px;padding:10px 18px;border-radius:12px;border:1px solid var(--border);font-weight:650;text-decoration:none;background:var(--soft)}
.button.primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
h2{font-size:13px;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);margin:28px 0 10px}
ol,ul{list-style:none;padding:0;margin:0;display:grid;gap:8px}
li a{display:block;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:11px 14px;text-decoration:none;overflow-wrap:anywhere}
li small{display:block;color:var(--muted);font-size:13px}
footer{color:var(--muted);font-size:13px;margin-top:32px}
'''


def cutoff(now=None):
    return ((now or datetime.now(timezone.utc)) - INDEX_AFTER).isoformat(timespec='milliseconds')


def plain(text, limit):
    """Single-line excerpt for titles and descriptions."""
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def count(number, one, many):
    return f'{number} {one if number == 1 else many}'


def xml_text(text):
    return xml_escape(XML_INVALID.sub('', text))


def json_ld(data):
    # Keep the data block inert inside HTML: no "</script>" or markup can appear.
    return (json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e')
            .replace('&', '\\u0026'))


def rule_name(mutation, parent_id):
    return 'Seed idea' if parent_id is None else RULE_NAMES.get(mutation, mutation)


def page(*, title, description, canonical, robots, body, structured=None):
    e = html.escape
    head = [
        '<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{e(title)}</title>', f'<meta name="description" content="{e(description)}">',
        f'<meta name="robots" content="{robots}">', '<meta name="theme-color" content="#2c543c">',
        '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
        '<link rel="alternate" type="application/atom+xml" title="Idea Evolution" href="/feed.xml">',
    ]
    if canonical:
        image = f'{canonical.split("/i/")[0]}/social-card.png'
        head += [f'<link rel="canonical" href="{e(canonical)}">', '<meta property="og:type" content="article">',
                 '<meta property="og:site_name" content="Idea Evolution">', f'<meta property="og:title" content="{e(title)}">',
                 f'<meta property="og:description" content="{e(description)}">', f'<meta property="og:url" content="{e(canonical)}">',
                 f'<meta property="og:image" content="{e(image)}">', '<meta name="twitter:card" content="summary_large_image">',
                 f'<meta name="twitter:title" content="{e(title)}">', f'<meta name="twitter:description" content="{e(description)}">',
                 f'<meta name="twitter:image" content="{e(image)}">']
    if structured:
        head.append(f'<script type="application/ld+json">{json_ld(structured)}</script>')
    head += [f'<style>{PAGE_STYLE}</style>', '</head>']
    brand = '<a class="brand" href="/"><span class="mark" aria-hidden="true">◇</span>idea evolution</a>'
    return '\n'.join(head) + f'\n<body><main>{brand}{body}</main></body>\n</html>\n'


def create_share_router(connect_db, public_origin):
    router = APIRouter()
    IdeaPath = Annotated[int, Path(gt=0, le=MAX_SQLITE_ID)]

    def not_found():
        body = ('<section class="card"><h1>This idea is not available.</h1>'
                '<p>It may have been removed, or the link is incomplete.</p>'
                '<div class="actions"><a class="button primary" href="/">Explore the idea garden</a></div></section>')
        content = page(title='Idea not found — Idea Evolution', description='This idea is not available.', canonical=None,
                       robots='noindex, nofollow', body=body)
        return HTMLResponse(content, status_code=404, headers={'Cache-Control': 'no-cache', 'X-Robots-Tag': 'noindex, nofollow'})

    @router.api_route('/i/{idea_id}', methods=['GET', 'HEAD'], response_class=HTMLResponse)
    def idea_page(idea_id: IdeaPath):
        e = html.escape
        with closing(connect_db()) as conn:
            row = conn.execute('SELECT id, parent_id, content, mutation, created_at, depth FROM ideas WHERE id = ? AND hidden = 0',
                               (idea_id,)).fetchone()
            if row is None:
                return not_found()
            lineage, parent_id = [], row['parent_id']
            while parent_id is not None and len(lineage) < 40:
                ancestor = conn.execute('SELECT id, parent_id, content, mutation FROM ideas WHERE id = ? AND hidden = 0',
                                        (parent_id,)).fetchone()
                if ancestor is None:
                    break
                lineage.insert(0, ancestor)
                parent_id = ancestor['parent_id']
            children = conn.execute('SELECT id, parent_id, content, mutation FROM ideas WHERE parent_id = ? AND hidden = 0 '
                                    'ORDER BY id LIMIT ?', (idea_id, CHILD_LIMIT)).fetchall()
            branch_total = conn.execute('SELECT COUNT(*) FROM ideas WHERE parent_id = ? AND hidden = 0', (idea_id,)).fetchone()[0]
            water = conn.execute('SELECT COALESCE(SUM(count), 0) FROM idea_water WHERE idea_id = ?', (idea_id,)).fetchone()[0]
            ids = [idea_id, *(a['id'] for a in lineage)]
            reported = conn.execute(f"SELECT 1 FROM idea_reports WHERE status = 'open' AND idea_id IN ({','.join('?' * len(ids))}) "
                                    'LIMIT 1', ids).fetchone() is not None
        fresh = row['created_at'] is not None and row['created_at'] > cutoff()
        indexable = not fresh and not reported
        robots = 'index, follow' if indexable else 'noindex, nofollow'
        canonical = f'{public_origin}/i/{idea_id}'
        label = rule_name(row['mutation'], row['parent_id'])
        title = f'{plain(row["content"], 60)} — Idea Evolution'
        description = plain(row['content'], 160)

        def item(idea):
            return (f'<li><a href="/i/{idea["id"]}"><small>#{idea["id"]} · {e(rule_name(idea["mutation"], idea["parent_id"]))}</small>'
                    f'<span dir="auto">{e(plain(idea["content"], 180))}</span></a></li>')

        created = (f' · <time datetime="{e(row["created_at"])}">{e(row["created_at"][:10])}</time>'
                   if row['created_at'] else '')
        body = [f'<article class="card"><div class="meta"><span class="tag">{e(label)}</span><span>#{idea_id}</span>'
                f'<span>depth {row["depth"]}</span><span>{count(branch_total, "branch", "branches")}</span>'
                f'<span>{count(water, "watering", "waterings")}</span>{created}</div>',
                f'<p class="idea" dir="auto">{e(row["content"])}</p>',
                '<div class="actions">'
                f'<a class="button primary" href="/#idea-{idea_id}">Open in the garden</a>'
                '<a class="button" href="/?action=plant">Plant your own idea</a></div></article>']
        if lineage:
            body.append('<h2>The path here</h2><ol>' + ''.join(item(a) for a in lineage) + '</ol>')
        if children:
            body.append('<h2>Branches</h2><ul>' + ''.join(item(c) for c in children) + '</ul>')
        body.append('<footer>Idea Evolution is a public idea garden. Ideas are written by visitors and transformed by '
                    'pure, deterministic Unison functions.</footer>')
        structured = {'@context': 'https://schema.org', '@type': 'CreativeWork', 'name': plain(row['content'], 110),
                      'text': row['content'], 'url': canonical, 'inLanguage': 'und',
                      'isPartOf': {'@type': 'WebSite', 'name': 'Idea Evolution', 'url': f'{public_origin}/'}}
        if row['created_at']:
            structured['dateCreated'] = row['created_at']
        if lineage:
            structured['isBasedOn'] = f'{public_origin}/i/{lineage[-1]["id"]}'
        headers = {'Cache-Control': 'public, max-age=60'}
        if not indexable:
            headers['X-Robots-Tag'] = 'noindex, nofollow'
        return HTMLResponse(page(title=title, description=description, canonical=canonical, robots=robots,
                                 body=''.join(body), structured=structured), headers=headers)

    def eligible(conn, extra='', limit=SITEMAP_LIMIT):
        return conn.execute(f'''{FLAGGED}
            SELECT id, parent_id, content, created_at FROM ideas
            WHERE hidden = 0 AND (created_at IS NULL OR created_at <= ?) AND id NOT IN (SELECT id FROM flagged){extra}
            ORDER BY id DESC LIMIT ?''', (cutoff(), limit)).fetchall()

    @router.api_route('/sitemap.xml', methods=['GET', 'HEAD'])
    def sitemap():
        with closing(connect_db()) as conn:
            rows = eligible(conn)
        urls = [f'<url><loc>{xml_text(public_origin)}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>']
        for row in rows:
            lastmod = f'<lastmod>{row["created_at"][:10]}</lastmod>' if row['created_at'] else ''
            urls.append(f'<url><loc>{xml_text(public_origin)}/i/{row["id"]}</loc>{lastmod}</url>')
        body = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + '\n'.join(urls) + '\n</urlset>\n')
        return Response(body, media_type='application/xml', headers={'Cache-Control': 'public, max-age=900'})

    @router.api_route('/feed.xml', methods=['GET', 'HEAD'])
    def feed():
        with closing(connect_db()) as conn:
            rows = eligible(conn, ' AND parent_id IS NULL', FEED_LIMIT)
        origin = xml_text(public_origin)
        entries = []
        for row in rows:
            updated = row['created_at'] or LEGACY_UPDATED
            entries.append(f'<entry><id>{origin}/i/{row["id"]}</id><title>{xml_text(plain(row["content"], 90))}</title>'
                           f'<link rel="alternate" href="{origin}/i/{row["id"]}"/><updated>{xml_text(updated)}</updated>'
                           f'<content type="text">{xml_text(row["content"])}</content></entry>')
        latest = max((row['created_at'] or LEGACY_UPDATED for row in rows), default=LEGACY_UPDATED)
        body = ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">\n'
                f'<title>Idea Evolution — new seed ideas</title><id>{origin}/feed.xml</id>'
                f'<link rel="self" href="{origin}/feed.xml"/><link rel="alternate" href="{origin}/"/>'
                f'<updated>{xml_text(latest)}</updated><author><name>Idea Evolution community</name></author>\n'
                + '\n'.join(entries) + '\n</feed>\n')
        return Response(body, media_type='application/atom+xml', headers={'Cache-Control': 'public, max-age=900'})

    return router
