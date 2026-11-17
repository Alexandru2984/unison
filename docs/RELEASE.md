# Product release verification

Date: 2026-11-17. **Published:** https://unison.micutu.com/

Deployed code revision: `206c6004a210178c23a2008a09a3fa8e4f6b978a`. A documentation-only verification commit follows deployment; `/api/health` and `/release.json` identify the running code.

## Moderation follow-up release

- Private visitor reports, deduplication, bounded report storage, reversible subtree hiding/restoration and an OS-authorized operator CLI are published. There is no public administrator API. See [moderation instructions](MODERATION.md).
- All public reads and mutations respect visibility. Independent child rules survive parent restoration. Live change notifications and HTTP revision checks purge new clients' loaded text, seed/graph/list data, comparisons, bookmarks' loaded content and export selections; delayed responses cannot reinsert stale records. Existing downloads/offline copies and old browser versions require separate consideration.
- **56 tests pass:** 35 backend tests including the real engine and 9 moderation/boundary cases, 3 operational checks, 5 utility checks and 13 Chromium cases. Build/strict TypeScript, zero-warning ESLint, ShellCheck and dependency audits pass. No known dependency advisories were reported.
- The deployment candidate exercised two deduplicated reports, private queue inspection, hiding all five synthetic records, public 404/exclusion checks, restoring them and checking preservation. These actions used a disposable database only.
- Public Chromium checks opened and cancelled the report dialog on desktop and a 390px phone view, verified live sync and recorded zero API writes and zero browser exceptions/console errors. Mobile dialog accessibility is also checked in the isolated browser suite.
- Public health/release revisions agree. All 14 original ideas retain their original IDs, parents, text and mutations; moderation revision is 0 and the real report queue/operator audit are empty. No production idea was hidden, restored or reported for testing.
- Oversized SQLite identifiers return 422 rather than server errors, including the new reporting route and existing parent/cursor/detail/lineage parameters.
- Pre-release backup: `/var/backups/unison-backend/20261117T044933Z/evolution.db`, verified with 14 records, integrity ok and mode 0600. Latest rollout backup: `/var/backups/unison-backend/20261117T045244Z/evolution.db`.
- Deployment rollback refuses a pre-moderation API when hidden records exist, failing closed instead of republishing them. The guard and overlapping-rule restoration are tested.
- Commits retain the repository owner's existing author/committer identity, without coauthor trailers. No push or GitHub-hosted workflow run was performed.

## Initial release local checks

- 26 backend tests pass with `RUN_ENGINE_TESTS=1`: HTTP/security/persistence boundaries plus the real compiled Unison engine. Golden outputs and repeated Unicode/JSON cases verify the executable.
- 2 operational tests pass: consistent backup of a live WAL database and rejection of overwriting an existing backup.
- 5 frontend utility tests pass: live-result reconciliation, bounded Unicode diff, safe Markdown export, storage failure handling and word counts.
- 8 Chromium product tests cover publishing/mutations, retry idempotency, search/bookmarks/export, deep links/draft recovery, safe rendering of public text, pagination, responsive layouts and SEO. Accessibility checks cover all transformation badges, light/dark graph/list states and the mobile guide.
- TypeScript strict mode, production build, ESLint with zero warnings, Bash syntax and ShellCheck are required before deployment.
- Dependency audits after updates: no known advisories reported by `pip-audit` / `npm audit`. This is a point-in-time result, not a guarantee of vulnerability-free software.
- Actual API + Unison flows were exercised through Chromium against a temporary database on loopback; no test ideas were submitted to production.

## Production gate

The deployment script must compile the source, run actual engine integration checks, run health/create/all-four-mutation/lineage/validation/statistics probes on its disposable candidate, verify a live SQLite backup, then compare local and public revision responses. After deployment, verify the public page in Chromium, API filters/detail/lineage, WebSocket connection, security headers, genuine 404 responses, crawl assets and database record preservation. Keep the previous frontend/API releases and the private backup.

Completed:

- Candidate passed health, seed creation, all four real transformations, lineage, invalid-parent rejection, statistics and catalogue checks in its disposable database.
- Local and public health/release revisions agree. Service, Nginx and Cloudflare tunnel are active; the API runs as `unisonapp` from its root-owned release.
- All **14 original production ideas** retain identical IDs, parents, text and mutation values. No test idea was posted to the public board.
- Public API detail/lineage/statistics/catalogue and robots/sitemap/social image return 200. Unknown pages, unknown ideas, missing assets and disabled OpenAPI return genuine 404 responses with security headers.
- Chromium on the actual public domain verified graph/list, live WebSocket sync, deep-link restoration, light/dark themes and a 390px mobile layout. No JavaScript exceptions or console errors remained after the Cloudflare CSP nonce correction.
- Two independent HTML responses have different 128-bit nonces matching the Cloudflare-injected script attributes. Conditional HTML requests return 200/no-store, avoiding stale nonce reuse. Public API security headers are emitted once.
- The allowed public WebSocket origin connects. A foreign origin is rejected with 403 in this vhost's access log; Cloudflare surfaced that failed upgrade to the test client as 502. Existing bot policy also rejects some generic Python HTTP clients. Browser/curl flows work; no zone-wide Cloudflare policy was changed.
- Actual compiled engine tests also passed under a transient systemd sandbox with the service account, read-only source, private devices/tmp, loopback-only IP policy, 64-task and 384MB limits. Observed peak memory: 48.8MB. The live service's `systemd-analyze security` score remains 2.7.
- Latest private backup: `/var/backups/unison-backend/20261117T040716Z/evolution.db`. The earlier successful release backup was restored into a temporary database: 14 records, `PRAGMA integrity_check = ok`, mode 0600. No production restore was performed.
- Pre-activation failure handling was exercised when a candidate could not traverse its release parent; activation stopped, permissions and Git ownership handling were corrected, and subsequent candidates passed. The rollback procedure was reviewed as a tabletop; a full live rollback was not intentionally triggered.
- Temporary QA servers on ports 5179, 18091 and 18791 are stopped. Other vhosts and tunnel routing were preserved.

## Scope and remaining work

GitHub workflows are prepared and locally exercised; they have not run on GitHub until these commits are pushed. CI browser tests use isolated fixtures, while the real engine is exercised locally and by the VPS candidate. No remote push, account creation, external message, paid integration or new analytics service is part of this release.

The public board now has reporting and operator moderation; the owner must actually review the queue. Private workspaces, accounts/ownership, retention rules, alert delivery and scheduled off-host backups remain the next priorities. Only the landing page is submitted in the sitemap; hash-based public idea links are client navigation, not individually indexed documents.
