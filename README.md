# Idea Evolution

A public playground for exploring how ideas branch. React presents the workspace, FastAPI persists the graph in SQLite, and **Unison executes eight deterministic text transformations**. This is a single-server application with live updates, not a distributed worker cluster or an AI text generator.

Production: **https://unison.micutu.com/**

## Explore

- Plant a seed or write a custom branch. Before planting, preview what all eight rules make of an idea or of a draft.
- Expand, rephrase, amplify keywords, synthesize, ask "What if…?", add a twist, write a headline or flip the meaning. All eight are pure Unison functions. The original four rules are unchanged, so existing branches stay reproducible.
- Discover trending, most-branched, unexplored, fresh and deepest ideas, see the daily spark and 30-day activity, or jump to a random idea.
- Water ideas you like: one anonymous reaction per idea per day, with live counts and no stored IP addresses.
- Switch between the graph and an accessible list with infinite scroll. Replay how the garden grew, walk parents, children and siblings with the arrow keys, and focus a lineage.
- Search the whole public board and filter by rule, seed tree, leaves, saved ideas or ideas planted on this device.
- Share an idea through the Web Share API and its own server-rendered page (`/i/{id}`), or download it as an image card.
- Use the English or Romanian interface, detected automatically and switchable, in light or dark theme. On phones the app has bottom navigation and a bottom-sheet inspector. It can be installed as a PWA with offline-cached assets.
- Report a public idea privately by choosing a reason. The operator reviews, hides and restores branches through the local SSH/sudo interface, with an audit trail. Reports never remove content automatically.

Published text is public. Drafts, bookmarks and the list of ideas planted on this device stay in the browser and are lost if storage is cleared. Do not submit secrets or personal information. Links are not accepted in submitted text, and invisible, bidirectional-override or excessive combining characters are rejected. Re-submitting an existing seed or branch opens the existing idea instead of duplicating it. The transformations are deliberately simple text rules; the in-app guide describes each one.

## Development

Requirements: Node 24, Python 3.14, and UCM 1.2.0 with a prepared Unison codebase.

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
cp .env.example .env
npm --prefix frontend ci
```

Provide UCM at `ucm-bin/ucm-bin` or set `UNISON_BIN`. The existing VPS codebase in `unison/` contains `unisonProject/main` and its `base` namespace. A fresh clone must first provide this prepared codebase (or set `UNISON_CODEBASE` to one); the repository intentionally excludes runtime binaries and the local UCM database. Do not commit UCM credentials. Build from source in a fork of the codebase:

```bash
python3 scripts/build_unison.py
```

The compiler atomically replaces the executable only after success. `UNISON_OUTPUT` can select a temporary output for verification. Never treat an old `.uc` as proof that the current `.u` was compiled.

In two terminals:

```bash
# Terminal 1, project root. The example .env selects a disposable dev database.
backend/.venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8080

# Terminal 2
npm --prefix frontend run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/ws` to loopback port 8080; set `DEV_API_TARGET` for another development backend. `PUBLIC_ORIGIN` must exactly match the frontend origin, including scheme and port. Production uses its systemd environment instead of `.env`.

## Verification

```bash
backend/.venv/bin/python -m unittest discover -s backend -v
python3 -m unittest discover -s scripts -v
sudo scripts/check_nginx.sh   # on the VPS: vhost syntax against the host's shared includes
RUN_ENGINE_TESTS=1 backend/.venv/bin/python -m unittest discover -s backend -p test_engine.py -v
npm --prefix frontend test
npm --prefix frontend run lint -- --max-warnings=0
npm --prefix frontend run build
cd frontend
npx playwright install chromium
npm run test:e2e
```

API tests create temporary databases before importing the application. They exercise the Unicode/link text policy, duplicate reuse, per-client and global write budgets (IPv6 grouped by /64), previews, watering, discovery, share-page escaping and indexing rules, sitemap/feed validity, HTTP validation, origin/host/body/rate limits, persistence, cursor pagination, idempotent retries, migrations, WebSocket limits, slow clients and subprocess timeout/output/cancellation behavior. Engine integration tests run the **real compiled Unison executable**, check golden outputs and repeat Unicode/JSON edge cases. Operations tests cover deployment and daily backups on a live WAL database, retention, release pruning, the rollback guard and the hash-locked runtime. When `rclone` is installed, they also cover encrypted off-host round trips, tampering and truncation detection, and remote retention on a local crypt remote.

Playwright runs against the built frontend with isolated API/WebSocket fixtures. It checks product flows, previews, watering, discovery, Romanian locale, the PWA manifest and service worker, exports, failed writes, deep links, safe public text rendering, draft recovery, 320–1440px layouts, accessibility and SEO metadata. Fixtures do not claim to validate the Unison runtime. Actual full-stack candidate checks run with a disposable database before every deployment.

Production dependencies are pinned with hashes in `backend/requirements.lock`; regenerate it with pip-compile after changing `requirements.txt`. Audit with `pip-audit -r backend/requirements.lock --require-hashes --disable-pip` and `npm --prefix frontend audit --omit=dev --audit-level=moderate` (shipped code). Build tooling is audited at `critical`: it only processes repository-authored input, and an advisory without a patched release, such as GHSA-fc5q-39xc-vjpf in picomatch ≤4.0.7, must not block every build. GitHub Actions runs these checks with read-only permissions and full-SHA action pins. It also verifies that the lock installs from hashed wheels and runs shellcheck on the shell scripts. Dependabot proposes weekly dependency updates. No workflow deploys to the VPS or receives production secrets. Workflows run on GitHub after commits are pushed.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health` | Database connectivity, runtime-file presence and deployed revision |
| `GET /api/idea` | Ascending page; `before` / `after`, `limit` (1–500), `q`, `mutation`, `root_id`, `roots_only`, `leaves_only`, `ids` (up to 100). Rows include visible `children` and `water` counts |
| `POST /api/idea` | Create `{content, parent_id, mutation}`; optional `Idempotency-Key`. An identical seed or branch returns the existing idea with `X-Idea-Duplicate: true`; text that was moderated returns 409 |
| `GET /api/idea/{id}` | A public idea |
| `GET /api/idea/{id}/lineage` | Bounded ancestry from seed to selected idea |
| `GET /api/idea/{id}/preview` | What every rule would produce, with `existing_id` when that branch already exists |
| `POST /api/preview` | Preview the rules on an unsaved draft `{content}`; nothing is stored |
| `POST /api/idea/{id}/water` | Anonymous daily reaction: `{idea_id, water, counted}` |
| `GET /api/discover` | Trending, branching, unexplored, fresh and deepest ideas (8 each) |
| `GET /api/random` | A random visible idea |
| `POST /api/idea/{id}/report` | Private, deduplicated report `{reason}`; no free-text details or public report counts |
| `GET /api/stats` | Totals, depth, per-rule counts, waterings, 30-day activity and capacity |
| `GET /api/mutations` | Transformation names and descriptions |
| `WS /ws` | Same-origin change and watering notifications; moderation revision changes invalidate cached public views |
| `GET /i/{id}` | Server-rendered share page with Open Graph and JSON-LD. Indexable only 48 hours after creation and while neither the idea nor an ancestor has an open report |
| `GET /sitemap.xml`, `GET /feed.xml` | Landing page and eligible ideas; Atom feed of the latest eligible seeds |

Pagination headers: `X-Has-More`, `X-Next-Cursor`, `X-Board-Revision`. Use one cursor direction per request. Generated text is capped at 4096 characters, submitted seeds at 2000, branch depth at 32, and the default public board at 10000 records. Each client may plant 150 ideas a day and the whole board accepts 600 an hour; `DAILY_IDEAS_PER_CLIENT` and `GLOBAL_IDEAS_PER_HOUR` adjust this. Existing rows retain unknown timestamps as `null`. There is no arbitrary shared-record editing or deletion API. Hidden branches are excluded consistently from public detail, ancestry, pagination, filters, statistics and new mutations. See [moderation and its rollback policy](docs/MODERATION.md).

## Production and remaining work

[Operations and rollback](docs/OPERATIONS.md), [security audit](docs/SECURITY_AUDIT.md), [product plan](docs/PLAN.md) and [release verification](docs/RELEASE.md).

The service runs as `unisonapp` from a read-only, root-owned API release, with its own hash-locked virtualenv and engine copy under `/opt/unison-runtime`. The development checkout is not visible to it. It has a private writable database and loopback-only network access, with CPU, memory and process limits. Daily verified snapshots are copied to Google Drive, encrypted with rclone crypt, and every copy is checked by downloading and restoring it. Nginx retains Cloudflare origin protections, TLS, CSP and request/connection limits. Deployment keeps this application's port at 8097 and does not change other vhosts or tunnel routing.

Before broader public promotion, establish a regular moderation review process, private workspaces with ownership, an explicit retention policy, API alert delivery and full restore drills on a spare host. Hash links (`/#idea-{id}`) restore a client view. Search engines see the `/i/{id}` pages listed in the dynamic sitemap once they meet the indexing rule above. Search Console verification, indexing and external monitoring require actual operator setup and are not implied by repository configuration.
