# Product release verification

**Published:** https://unison.micutu.com/

## v2.1 release: off-host backups (2026-11-18)

Deployed code revision: `6efc9b410c37a88a05bb85dcf310c0513b53be08`. It covers the verified, encrypted off-host backups (`371684e`) and the first-load fix (`6efc9b4`).

Before deployment:
- Operations: 20 tests. Nine of them are new, and they drive a real rclone crypt remote on local disk: encrypted names and contents, idempotent reruns, tampering and truncation detection, stale or invalid snapshots, retention that touches only its own archives, and restore. Backend: 69 tests. Frontend: 14 unit and 26 Playwright tests, lint, build, shellcheck.
- The new Playwright test delays the first response so that the socket opens during the initial load. It failed against the previous build (two cancelled requests) and passes with the fix.
- The sandbox was rehearsed in transient units built from the real unit file, using a synthetic database:
  - with the group, the upload succeeded;
  - without `SupplementaryGroups=unisonapp`, snapshots were unreadable;
  - a read-only listing of the Drive folder worked from inside the sandbox.
- The credential `/etc/unison-backend/offsite-rclone.conf` (root, 0600) holds only the `gdrive` and `gdrive-vps-crypt` remotes. Its secrets match the existing configuration, compared by hash without being displayed.

Deployment: `sudo ./deploy.sh` exited 0, the candidate smoke passed, and there was no rollback. Private backup: `/var/backups/unison-backend/20261118T123756Z`. Both backup units received the `OnFailure=swift-vapor-alert@%n.service` drop-in.

After deployment:
- `systemctl start unison-backup.service` wrote `evolution-20261118T123920Z.db` with mode 0640 in a 0750 directory. `OnSuccess=` then started the upload: 69,632 bytes became a 3,111-byte archive, which was uploaded, downloaded, restored and verified in 24 s. `status.json` records the result.
- Restore drill in a private-tmp unit: `offsite.py list` and `fetch` produced a database byte-identical to the local snapshot, with `integrity_check` ok and 14 ideas. The credential file was not modified.
- The raw Drive folder contains no plaintext `evolution` or `unison` names.
- The public fingerprint is unchanged (`5f2d135734f70053`, the same 14 ids). Health, `release.json` and the security headers are correct. The five public browser checks pass even when no cancelled request is tolerated.

Known: the Google token has full Drive scope and is shared with the other applications on this VPS, and root on the VPS could delete the copies (Drive trash keeps them for 30 days). CI runs on GitHub only after a push.

## v2 release (2026-11-18)

Deployed code revision: `74863e70f8498eaa42565760415f78fd47f7d534`. This documentation commit follows the deployment; `/api/health` and `/release.json` identify the running code. Stages E1–E7 and the audit findings they fix are listed in [PLAN.md](PLAN.md#v2-iteration-2026-11-18) and [SECURITY_AUDIT.md](SECURITY_AUDIT.md#audit-2026-11-18-v2-iteration).

Before deployment:
- Backend: 69 tests, including the real compiled engine. Operations: 11 tests. Frontend: 14 unit and 25 Playwright tests, lint at zero warnings, production build.
- The engine build is byte-identical to the previous scratch build. `pip-audit` on the hash lock is clean. Shipped npm dependencies have no advisories. Build tooling carries GHSA-fc5q-39xc-vjpf (picomatch ≤4.0.7, no patched release; build-time only).
- Migration rehearsal on a private copy of production, made through the SQLite backup API and deleted afterwards:
  - the 14 ideas kept a byte-identical fingerprint (IDs, parents, roots, depth, rule, text, hidden flag);
  - only the `content_key` column and the `idea_water` table were added, and the key was backfilled for 14/14;
  - all 14 share pages returned 200, the sitemap listed 15 URLs, the feed had 2 entries, and discovery and previews answered;
  - the previous release passed `rollback_compatible.py` against the migrated copy.
- `scripts/check_nginx.sh` passed, and `shellcheck` and `systemd-analyze verify` found no unit errors.

Deployment (`sudo ./deploy.sh`, exit 0, no rollback):
- Hash-locked virtualenv `/opt/unison-runtime/venv-8d6615843eb0`, built from wheels with `pip check`. UCM copy `/opt/unison-runtime/ucm-207af0a3b6db`, tree hash verified.
- Engine tests passed against the copied runtime.
- The loopback candidate passed on a disposable database: all eight rules, previews, watering, discovery, share pages, the moderation lifecycle and preservation.
- Private backup at `/var/backups/unison-backend/20261118T045924Z`. Pruning found nothing to remove (7 frontend and 8 API releases, 7 deploy backups).

After deployment:
- The **14 original ideas** have the same public fingerprint (`5f2d135734f70053`) before and after. No idea, reaction or report was written by verification.
- The service runs `/opt/unison-backend/current/venv/bin/uvicorn` with `ProtectHome=yes`. `/home/micu` is not accessible from its mount namespace. `runtime.env` names the copied UCM.
- `unison-backup.timer` is enabled. A manual run succeeded as `unisonapp` and wrote a 0600 snapshot to `/var/lib/unison-backups`.
- Headers:
  - HTML has one `Cache-Control: no-store`;
  - hashed assets have one `public, max-age=31536000, immutable`;
  - the CSP, HSTS and frame headers are present on HTML, share pages, sitemap, feed and manifest;
  - POST to `/index.html` and `/i/{id}` returns 403;
  - an unknown `/i/{id}` returns 404 with `X-Robots-Tag: noindex, nofollow`.
- Chromium on the public domain was checked at 1366px, at 390px, in Discover, in the inspector deep link, in the Romanian locale (`lang="ro"`) and on the share page. There were no console, page or CSP errors and no failed application requests. The live WebSocket connected and the service worker registered. Cloudflare's own `/cdn-cgi/` beacons were excluded from the request checks.

Known and accepted:
- Cloudflare's zone "Browser Cache TTL" rewrites `sw.js` and `robots.txt` to `max-age=14400`, although the origin sends `no-cache`. Browsers bypass the HTTP cache for service-worker update checks, so new workers still install. Setting the zone to "Respect existing headers" would remove the difference, but it is a Cloudflare change outside this release.
- On the first WebSocket open, the client re-synchronizes once. This aborts and repeats the initial statistics and seed requests (about three small extra requests per visit). The behavior is correct; skipping that first re-sync is a candidate for the next release.
- All 14 legacy ideas have unknown (`NULL`) creation times. They count as mature for indexing and do not appear in the 30-day activity chart.

## Initial release (2026-11-17)

Deployed code revision: `206c6004a210178c23a2008a09a3fa8e4f6b978a`.

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

The public board now has reporting and operator moderation; the owner must actually review the queue. Private workspaces, accounts/ownership, retention rules, alert delivery and off-host copies of the daily backups remain the next priorities. Since v2, the dynamic sitemap lists `/i/{id}` pages that are at least 48 hours old and have no open reports.
