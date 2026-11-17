# Operations and incident response

Production URL: `https://unison.micutu.com`. API service: `unison-backend.service`, bound to `127.0.0.1:8097`. Database: `/var/lib/unison-backend/evolution.db`. Frontend: `/var/www/unison.micutu.com/current` → immutable release. API: `/opt/unison-backend/current` → root-owned immutable source and matching compiled engine. Keep port 8097; do not auto-pick ports or modify other vhosts.

## Deploy

Run the backend/security tests, real engine integration tests, frontend build/lint and browser tests described in the README. Commit each finished stage before deployment. Then run `sudo ./deploy.sh`. The script serializes deployments, builds as the checkout owner, verifies a candidate on loopback port 18791 using a disposable database, takes an online SQLite backup, installs this application's configuration and swaps API/frontend symlinks. It checks local and public revisions and attempts rollback on failure. It neither changes Cloudflare routing nor manages certificates or other vhosts.

On the **first migration only**, preserve the old compiled executable before building and pass `PREVIOUS_BACKEND_REVISION` (the actual running Git revision) and `PREVIOUS_UNISON_PROGRAM` (an absolute path to that preserved executable) to `sudo env … ./deploy.sh`. This creates a root-owned fallback snapshot. Subsequent deployments discover the previous API symlink automatically.

The shared virtual environment receives only pinned runtime requirements. Dependency downgrades require explicit review during rollback; the first rollout only patches OpenTelemetry without changing its API. Frontend releases retain the previous hashed assets so open tabs can still lazy-load their graph. Old releases and backups are retained; prune deliberately after verifying recovery and retention needs. Backups remain local until an off-host destination is configured.

## Read-only diagnosis

```bash
systemctl status unison-backend --no-pager
sudo journalctl -u unison-backend --since '15 minutes ago' --no-pager
curl --fail http://127.0.0.1:8097/api/health
curl --fail https://unison.micutu.com/api/health
sudo nginx -t
readlink -f /var/www/unison.micutu.com/current
```

Do not print `.env`, tunnel credentials, private keys or authentication headers in issue reports. Do not send submitted idea content to logs.

## Backup and recovery

Use SQLite's online backup API while the service is live; copying just the `.db` file can miss transactions in the WAL. Store backups outside the checkout with mode 0600 and record the corresponding Git revision. Check `PRAGMA integrity_check` against the backup. Keep old frontend releases until the new release passes local and public checks.

Each private deployment backup records `previous-frontend` and `previous-backend`. To roll back, atomically replace **both** `current` symlinks with these previous release paths, restore the saved application Nginx files, validate Nginx, restart this service and reload Nginx. Keep the versioned hardened service unit: it reads code and the matching engine from the API symlink. Check public health and `release.json` again. Do not reset the developer checkout or automatically restore the database: additive migrations preserve existing and newly submitted ideas. Restore a database only with the service stopped, after backing up the current state, and account for its WAL/SHM files.

## Abuse or suspected compromise

1. Record time, health status, service revision and affected endpoint. Preserve journal and this vhost's logs privately.
2. For write abuse, temporarily deny POST only at this application's Nginx location; validate with `nginx -t`, then reload. Reads can remain available.
3. Take an online SQLite backup. Do not delete public data as a first response.
4. For engine/service compromise, stop this service and serve the last static release while investigating. The dedicated account must stay isolated.
5. Identify the exploit, patch and test in a temporary database. Restore from a verified backup only when needed.
6. Assess actual data exposure, applicable reporting duties and recovery evidence with the owner. No automated external messages are sent.

## Remaining operator work

Connect health/error alerts to an owner-selected channel, schedule encrypted off-host backups, test restoration periodically, decide retention/moderation rules, and review Cloudflare origin rules. These cannot be considered complete merely because a script or log exists.
