# Idea Evolution: product release plan

Audit started: 2026-11-17. Existing application: React 19 + React Flow, FastAPI/SQLite, deterministic Unison CLI. Production: Cloudflare → Nginx → loopback API, isolated systemd account, static releases under `/var/www/unison.micutu.com`.

**Release status:** stages 1–6 completed and published on 2026-11-17. See [verification and remaining limitations](RELEASE.md). The next-iteration list below remains a roadmap, not a claim that accounts or external monitoring have been implemented.

**Follow-up status:** reporting, reversible subtree moderation, the SSH/sudo operator interface, client cache invalidation and the legacy-rollback guard are implemented and published. All original public ideas remain visible and unchanged. Accounts/private workspaces and external monitoring remain future work.

## Release order and acceptance criteria

1. **Inventory and audit.** Record reproducible findings, actual production protections, deployment drift, data boundaries and recovery instructions. Keep existing data and the local port choice (8097). Commit the audit and plan.
2. **API security and exploration.** Enforce body/origin/content validation, valid parents and bounded ancestry, rate and connection limits, bounded subprocess execution/output, slow-client isolation, stable timestamps and indexes. Add cursor pagination, individual idea lookup, root/search/mutation filters, statistics and a mutation catalogue. Preserve `/api/idea` response compatibility. Verify against temporary databases; commit.
3. **Reliable Unison engine.** Correct JSON escaping, compile reproducibly, exercise the real executable with Unicode, quotes, control characters and all four transformations. Do not substitute generated AI text for the deterministic engine. Commit source, build tooling and regression checks.
4. **Finished exploration workspace.** Responsive desktop/tablet/mobile layout; graph and list views; search and mutation/root/bookmark filters; selected-idea inspector; lineage focus; parent/child navigation; original/result comparison; branch creation; starter prompts; local draft recovery; private local bookmarks; copy/share; JSON/Markdown exports; graph orientation/fit; dark/light themes; accessible controls and reduced motion. Show loading, empty, error, offline and reconnect states. Make writes work when WebSockets fail. Verify in a real browser; commit.
5. **Safe production delivery.** Version the hardened configuration that actually runs. Replace the destructive deploy script with preflight checks, SQLite online backup, immutable frontend release, syntax checks, health checks and rollback. Keep other vhosts and Cloudflare configuration intact. Deploy and smoke-test this application only; commit.
6. **SEO, tests and CI last.** Product metadata, canonical/social preview, robots/sitemap, removal of starter branding, security/regression checks, frontend build/lint and isolated browser tests in CI. Pin CI dependencies, use minimal job permissions and dependency-update automation. Commit and record verification.

## Next product iterations

Prioritize these only after the release works correctly:

- Private workspaces, accounts and explicit ownership, with a reviewed session/CSRF model before editing/deleting shared data.
- Moderation/reporting and the SSH/sudo operator interface are implemented in the follow-up release; [review workflow](MODERATION.md). Retention rules, an owner review schedule and alert delivery still require operational setup before public promotion.
- Named collections and opt-in collaborative rooms; scoped events and per-room quotas.
- More useful deterministic transformations in Unison, with versioned engine provenance and golden fixtures.
- Multi-idea synthesis with two explicit parents and graph invariants.
- Versioned import with local preview, strict validation, quotas and explicit confirmation before public writes.
- Self-hosted, privacy-conscious aggregate analytics; measure activation and retention before building leaderboards or votes.
- Automated off-host backups and restore drills; capacity alerts and uptime monitoring integrated with an owner-selected service.
- Localization (Romanian/English), guided first session and share cards for individual public trees.

The public board is shared. Text submitted there is public; local drafts and bookmarks should stay on the device. No accounts, paid services, emails, third-party analytics or AI vendors are introduced in this release.
