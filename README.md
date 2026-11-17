# Idea Evolution

A public playground for exploring how ideas branch. React presents the workspace, FastAPI persists the graph in SQLite, and **Unison executes the four deterministic text transformations**. This is a single-server application with live updates, not a distributed worker cluster or an AI text generator.

Production: **https://unison.micutu.com/**

## Explore

- Plant a seed or write a custom branch from an existing idea.
- Expand, rephrase, amplify keywords or synthesize with pure Unison functions.
- Switch between the graph and the accessible mobile-friendly list.
- Search the entire public board; filter transformations, recent seed trees or saved ideas.
- Inspect a full idea, trace its ancestry, focus a lineage and navigate loaded children.
- Compare a branch with its parent using word-level changes.
- Keep up to 100 bookmarks and a recoverable draft in this browser.
- Copy text or a direct public idea link; export loaded ideas or a lineage as JSON/Markdown.
- Use light/dark themes, starter prompts, keyboard shortcuts, graph orientation and zoom controls.
- See request errors, loading/empty states, offline status and reconnect progress. POST results appear immediately; WebSocket reconnection and polling keep other updates current.

Published text is public. Drafts and bookmarks stay on the device and are lost if browser storage is cleared. Do not submit secrets or personal information. The transformations are deliberately simple text rules; the guide describes what each rule does.

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
RUN_ENGINE_TESTS=1 backend/.venv/bin/python -m unittest discover -s backend -p test_engine.py -v
npm --prefix frontend test
npm --prefix frontend run lint -- --max-warnings=0
npm --prefix frontend run build
cd frontend
npx playwright install chromium
npm run test:e2e
```

API tests create temporary databases before importing the application. They exercise HTTP validation, origin/host/body/rate limits, persistence, cursor pagination, idempotent retries, migrations, WebSocket limits, slow clients and subprocess timeout/output/cancellation behavior. Engine integration tests run the **real compiled Unison executable**, check golden outputs and repeat Unicode/JSON edge cases. Backup tests exercise a live WAL database and reject overwriting an existing backup.

Playwright runs against the built frontend with isolated API/WebSocket fixtures. It checks product flows, exports, failed writes, deep links, safe public text rendering, draft recovery, 320–1440px layouts, accessibility and SEO files. Fixtures do not claim to validate the Unison runtime. Actual full-stack candidate checks run with a disposable database before every deployment.

Audit dependencies with `pip-audit -r backend/requirements.txt --no-deps --disable-pip` and `npm --prefix frontend audit --audit-level=moderate`. GitHub Actions runs these checks with read-only permissions and full-SHA action pins. Dependabot proposes weekly dependency updates. No workflow deploys to the VPS or receives production secrets. Workflows run on GitHub after commits are pushed.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health` | Database connectivity, runtime-file presence and deployed revision |
| `GET /api/idea` | Ascending page; `before` / `after`, `limit` (1–500), `q`, `mutation`, `root_id`, `roots_only`, `ids` (up to 100) |
| `POST /api/idea` | Create `{content, parent_id, mutation}`; optional `Idempotency-Key` for safe retries |
| `GET /api/idea/{id}` | A public idea |
| `GET /api/idea/{id}/lineage` | Bounded ancestry from seed to selected idea |
| `GET /api/stats` | Idea/seed totals, depth, per-rule counts and capacity |
| `GET /api/mutations` | Transformation names and descriptions |
| `WS /ws` | Same-origin server-to-client idea updates |

Pagination headers: `X-Has-More`, `X-Next-Cursor`. Use one cursor direction per request. Generated text is capped at 4096 characters, submitted seeds at 2000, branch depth at 32, and the default public board at 10000 records. Existing rows retain unknown timestamps as `null`. There is no arbitrary shared-record editing or deletion API.

## Production and remaining work

[Operations and rollback](docs/OPERATIONS.md), [security audit](docs/SECURITY_AUDIT.md), [product plan](docs/PLAN.md) and [release verification](docs/RELEASE.md).

The service runs as `unisonapp` with a read-only root-owned API release, a private writable database, loopback-only network access and CPU/memory/process limits. Nginx retains Cloudflare origin protections, TLS, CSP and request/connection limits. Deployment keeps this application's port at 8097 and does not change other vhosts or tunnel routing.

Before broader public promotion, prioritize moderation/reporting, private workspaces with ownership, an explicit retention policy, alert delivery, scheduled off-host backups and restore drills. Individual hash links restore a client view; the sitemap indexes the product landing page, not every public idea. Search Console verification, indexing and external monitoring require actual operator setup and are not implied by repository configuration.
