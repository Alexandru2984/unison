# Security and production audit

Date: 2026-11-17. Scope: this repository and this application's effective Nginx/systemd configuration. No load testing, destructive probes or writes to the live idea database during investigation.

## Confirmed findings at baseline

| ID | Severity | Evidence and impact | Remediation stage |
| --- | --- | --- | --- |
| SEC-01 | High | `deploy.sh` copies an obsolete HTTP vhost over production, disables the default vhost, runs Certbot, changes ports on every run and restarts before validating Nginx. It can remove production protections and disrupt unrelated services. | 5 |
| SEC-02 | High | Checked-in service runs as the developer account; actual service runs as `unisonapp` with filesystem/network restrictions. A redeploy would enlarge the impact of an application compromise. | 5 |
| SEC-03 | Medium | API has no request-body, write-origin or application rate limit. Nginx currently supplies body/rate limits, but direct/local or future deployment paths lack defense in depth. | 2 |
| SEC-04 | Medium | `broadcast_idea` awaits every socket sequentially without a deadline. One slow client can delay HTTP writes and broadcasts to other users. No application socket cap. | 2 |
| SEC-05 | Medium | A single idea lock is held while a subprocess runs. Work can queue behind slow mutations; cancellation does not explicitly reap the child; `communicate()` buffers unbounded output. | 2 |
| SEC-06 | Medium | `escapeJsonText` does not escape backslashes, tabs or carriage returns. The wrapper accepts malformed JSON as raw result text. Inputs can produce incorrect persisted output. | 3 |
| SEC-07 | Medium | Base ideas accept arbitrary `parent_id`; parent integrity and ancestry depth are not enforced. Null/control characters can reach argv and produce server failures. | 2 |
| SEC-08 | Medium | No documented backup/restore/deploy rollback; no CI; tests cover only seven direct-function cases and do not exercise HTTP, subprocess failures or socket backpressure. | 2, 5, 6 |
| SEC-09 | Low | Validation drops submitted content from error responses (good), but the process has no generic safe JSON error response or consistent application security/cache headers. | 2 |
| UX-01 | High product impact | No mobile breakpoint, long content overlaps fixed graph layout, no visible request errors, no polling/reconnect, and a write relies on a WebSocket event to become visible. | 4 |
| UX-02 | Medium product impact | Selecting a node rebuilds the fetch callback, reconnects the socket and refetches the board; a global Dagre instance retains stale graph state. No search, pagination, detail or export. | 4 |
| OPS-01 | Medium | Actual frontend is an older immutable release; building `frontend/dist` alone will not update the public site. Repository port (8088) and local/active port (8097) disagree. | 5 |
| ENGINE-01 | High product impact | Executing the live `.uc` with synthetic input returned an older plain-text transformation, while checked-in source described the richer JSON-producing engine. No build/provenance gate ensured executable/source agreement. | 3, 5 |
| DEP-01 | Medium/High advisories | Registry audits reported OpenTelemetry `CVE-2026-126360` and 10 frontend package reports (9 moderate, 1 high, including transitive reports for the same underlying advisories). These are dependency findings, not proof that every advisory is exploitable through this app. | Patched |

No SQL injection or shell command injection was identified in the reviewed routes: SQL values are parameterized and subprocesses use an argument vector. This is a scoped finding, not a guarantee that no vulnerability exists.

## Existing production protections to preserve

- API binds to loopback; docs/OpenAPI disabled; mutation allowlist, input/result limits, runtime timeout and total idea quota already exist.
- Dedicated `unisonapp` user, state directory mode 0700, `NoNewPrivileges`, strict filesystem isolation, loopback-only egress and memory/task limits. `systemd-analyze security` baseline: **2.7**.
- Nginx has TLS, Cloudflare origin gating, CSP, HSTS, clickjacking/MIME protections, body/rate/connection limits and WebSocket origin checks.
- Security header inheritance for Nginx error locations must be checked when adding `Retry-After`; Nginx header directives are inherited as a set.
- Effective origin routing must be inspected without printing tunnel credentials. No tunnel configuration changes are required for this release.

## CISO review

### Threat model (STRIDE)

1. **Denial of service:** anonymous writes/mutations/sockets consume processes, database capacity or broadcast time. Likelihood high, impact medium/high. Bound work at Nginx and application layers.
2. **Tampering:** anyone can publish unwanted text to the shared board. Likelihood high, impact medium. The board is intentionally public; no editing/deleting arbitrary shared records will be added. Moderation remains required before promotion.
3. **Information disclosure / privilege escalation:** visitors submit personal text to a public board; a backend exploit could affect readable files and state. Likelihood medium, impact high. Show the public-data boundary and retain the dedicated service sandbox.

### Blast radius

All public ideas can be read without authentication. At audit time the live database had 14 records; account/user counts and annual loss estimates are unknown. Do not invent financial estimates. The dedicated service's state database is writable; the source checkout is read-only inside the service, and the new API release is root-owned. The sandbox allows loopback networking, so a compromised process could also attempt to reach other local services; their authentication is outside this application's review. A deployment as the developer account would expose much more of the VPS.

### Detection

Current: Nginx application access/error logs and service journal, with no verified alert delivery. Review 429/5xx bursts, mutation timeouts, engine failures, connection-cap rejections and health failures. Desired detection: alert after three consecutive failed health checks or sustained 5xx/429 increases within five minutes. An actual alert channel and measured MTTD require operator setup; log messages alone are not monitoring.

### Response

See [operations runbook](OPERATIONS.md). Before publishing changes, walk through: broken frontend release → switch symlink back; broken backend → restore matching source revision and restart; suspected abuse → temporarily deny writes at this vhost, preserve logs and take SQLite online backup. Record the actual verification after deployment. No claim of an externally monitored or independently certified service is made.

### Regulatory and vendors

Personal data may be submitted voluntarily as public text. Avoid secrets and personal information; drafts/bookmarks are device-local. No cardholder/health processing is designed here. Legal scope, DPAs and reporting duties are unassessed. Cloudflare, the VPS provider and package registries are existing supply-chain dependencies; no new data-processing vendor is added. Incident reporting decisions require assessment of the actual data and applicable obligations.

### Verdict

**Mitigate then ship.** Preserve the effective production sandbox, implement bounded processing and restoreable deployment, and document remaining moderation/alerting limitations. Dependency audit results and final test evidence are recorded in the release notes.

## Technical references

- [Starlette middleware and trusted host handling](https://www.starlette.io/middleware/)
- [Nginx proxy timeouts and forwarded headers](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [Nginx response header inheritance](https://nginx.org/en/docs/http/ngx_http_headers_module.html)
- [Unison executable compilation](https://www.unison-lang.org/docs/usage-topics/running-programs/)
- [Cloudflare JavaScript Detections and CSP nonce support](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/javascript-detections/)

## Remediation verification

The release adds strict origin/host/content/body validation, per-client rate limits with bounded limiter memory, a four-socket per-client / 48-socket application cap, two bounded mutation slots, cancellation-safe process-group cleanup, output limits and strict JSON parsing. Parent integrity, depth, capacity and idempotent writes are enforced before persistence. Slow socket sends run concurrently with deadlines. SQLite migrations are additive and indexed; unknown historical timestamps remain unknown.

Deployment now uses a dedicated account, root-owned API releases with matching compiled engines, an online verified backup, a disposable full-stack candidate, atomic release switches and automatic rollback attempts. The effective hardened Nginx/systemd configuration is versioned; only this vhost is changed. Security headers are retained in the 429/asset locations. GitHub Actions has minimal permissions, immutable action pins and no production secrets or deploy job.

Public-browser verification identified Cloudflare Bot Fight Mode's injected inline JavaScript conflicting with the pre-existing CSP. A per-response Nginx request-ID nonce lets Cloudflare authorize its injected scripts, as its official documentation supports, without allowing arbitrary inline application scripts. HTML uses no-store and disables conditional 304 responses so a new nonce cannot be paired with previously cached HTML. Cloudflare remains responsible for its own injected browser code and bot policy; no zone-wide settings are changed.

`pip-audit` and `npm audit` returned no known advisories after updates. A limited full-history scan for AWS access-key prefixes, GitHub tokens and private-key PEM markers found no matches; this is not an exhaustive secret-detector result. The final release report records exact check results and production verification. Remaining requirements before promotion: an actual moderation review schedule, explicit retention/ownership decisions, active alerts and scheduled off-host backups.

## Moderation follow-up review

Anonymous reports are private, enumerated, rate limited, deduplicated and storage bounded; they do not trigger automatic hiding. Operator access uses existing SSH/sudo and private database permissions. The CLI drops to the service account before SQLite access and records operator decisions without duplicating idea text in the audit trail. There is no public admin credential or endpoint.

Subtree visibility is enforced in all read variants, statistics, new mutations and idempotent replays. A second parent check closes the engine/CLI race. WebSockets publish notifications rather than idea text; monotonic moderation revisions invalidate loaded browser content and stale responses. Tests cover hidden-data reads, overlapping hide/restore rules, real CLI use, a live WebSocket notification, fallback refresh, comparisons/exports and a delayed write response. Existing offline/downloaded copies and legacy browser code cannot be retroactively recalled.

Legacy API rollback is blocked after content has been hidden, preventing a pre-moderation query implementation from republishing it. SQLite identifier bounds now reject oversized values as 422. See [threat model and operator procedure](MODERATION.md) and [release evidence](RELEASE.md). The queue is still manually reviewed; no external alerts, automatic classifier, account ownership system or retention purge has been introduced.
