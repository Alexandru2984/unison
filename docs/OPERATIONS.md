# Operations and incident response

Production URL: `https://unison.micutu.com`. API service: `unison-backend.service`, bound to `127.0.0.1:8097`. Database: `/var/lib/unison-backend/evolution.db`. Frontend: `/var/www/unison.micutu.com/current` → immutable release. Keep port 8097; do not auto-pick ports or modify other vhosts.

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

To roll back the UI, atomically replace `current` with a symlink to the previous release. To roll back the API, restore a matching known-good source revision and restart the service; do not blindly reset a checkout with user changes. Restore a database only with the service stopped, after backing up the current state, and account for its WAL/SHM files. Migrations in this release must remain additive so earlier API code can read the database.

## Abuse or suspected compromise

1. Record time, health status, service revision and affected endpoint. Preserve journal and this vhost's logs privately.
2. For write abuse, temporarily deny POST only at this application's Nginx location; validate with `nginx -t`, then reload. Reads can remain available.
3. Take an online SQLite backup. Do not delete public data as a first response.
4. For engine/service compromise, stop this service and serve the last static release while investigating. The dedicated account must stay isolated.
5. Identify the exploit, patch and test in a temporary database. Restore from a verified backup only when needed.
6. Assess actual data exposure, applicable reporting duties and recovery evidence with the owner. No automated external messages are sent.

## Remaining operator work

Connect health/error alerts to an owner-selected channel, schedule encrypted off-host backups, test restoration periodically, decide retention/moderation rules, and review Cloudflare origin rules. These cannot be considered complete merely because a script or log exists.
