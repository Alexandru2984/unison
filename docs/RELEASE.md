# Product release verification

Date: 2026-11-17. Deployment status is finalized after public smoke checks.

## Local checks

- 26 backend tests pass with `RUN_ENGINE_TESTS=1`: HTTP/security/persistence boundaries plus the real compiled Unison engine. Golden outputs and repeated Unicode/JSON cases verify the executable.
- 2 operational tests pass: consistent backup of a live WAL database and rejection of overwriting an existing backup.
- 5 frontend utility tests pass: live-result reconciliation, bounded Unicode diff, safe Markdown export, storage failure handling and word counts.
- 8 Chromium product tests cover publishing/mutations, retry idempotency, search/bookmarks/export, deep links/draft recovery, safe rendering of public text, pagination, responsive layouts and SEO. Accessibility checks cover all transformation badges, light/dark graph/list states and the mobile guide.
- TypeScript strict mode, production build, ESLint with zero warnings, Bash syntax and ShellCheck are required before deployment.
- Dependency audits after updates: no known advisories reported by `pip-audit` / `npm audit`. This is a point-in-time result, not a guarantee of vulnerability-free software.
- Actual API + Unison flows were exercised through Chromium against a temporary database on loopback; no test ideas were submitted to production.

## Production gate

The deployment script must compile the source, run actual engine integration checks, run health/create/all-four-mutation/lineage/validation/statistics probes on its disposable candidate, verify a live SQLite backup, then compare local and public revision responses. After deployment, verify the public page in Chromium, API filters/detail/lineage, WebSocket connection, security headers, genuine 404 responses, crawl assets and database record preservation. Keep the previous frontend/API releases and the private backup.

## Scope and remaining work

GitHub workflows are prepared and locally exercised; they have not run on GitHub until these commits are pushed. CI browser tests use isolated fixtures, while the real engine is exercised locally and by the VPS candidate. No remote push, account creation, external message, paid integration or new analytics service is part of this release.

The public board still needs moderation and reporting before promotion. Private workspaces, accounts/ownership, retention rules, alert delivery and scheduled off-host backups remain the next priorities. Only the landing page is submitted in the sitemap; hash-based public idea links are client navigation, not individually indexed documents.
