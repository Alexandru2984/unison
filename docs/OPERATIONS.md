# Operations and incident response

Production URL: `https://unison.micutu.com`. API service: `unison-backend.service`, bound to `127.0.0.1:8097`. Database: `/var/lib/unison-backend/evolution.db`. Frontend: `/var/www/unison.micutu.com/current` → immutable release. API: `/opt/unison-backend/current` → root-owned immutable source and matching compiled engine. Keep port 8097; do not auto-pick ports or modify other vhosts.

## Deploy

Run the backend/security tests, real engine integration tests, frontend build/lint and browser tests described in the README. Commit each finished stage before deployment. Then run `sudo ./deploy.sh`. The script serializes deployments, builds as the checkout owner, verifies a candidate on loopback port 18791 using a disposable database, takes an online SQLite backup, installs this application's configuration and swaps API/frontend symlinks. It checks local and public revisions and attempts rollback on failure. It neither changes Cloudflare routing nor manages certificates or other vhosts.

On the **first migration only**, preserve the old compiled executable before building and pass `PREVIOUS_BACKEND_REVISION` (the actual running Git revision) and `PREVIOUS_UNISON_PROGRAM` (an absolute path to that preserved executable) to `sudo env … ./deploy.sh`. This creates a root-owned fallback snapshot. Subsequent deployments discover the previous API symlink automatically.

Runtimes are immutable and content-addressed under `/opt/unison-runtime`. `venv-<hash>` is built once per `backend/requirements.lock` and interpreter, from wheels only, with every file checked against the committed hashes. `ucm-<hash>` is a root-owned copy of `ucm-bin`, verified after copying. Each API release links `venv` to its environment, and its `runtime.env` names the engine binary. The service unit runs only from `/opt/unison-backend/current`, with `ProtectHome=yes`: neither the developer checkout nor its `.venv` is visible to it. After `requirements.txt` changes, regenerate the lock with `pip-compile` (command in `backend/requirements-dev.txt`). Frontend releases keep the previous hashed assets so open tabs can still lazy-load their graph.

After a verified release, `scripts/prune_releases.py --apply` keeps the eight newest API and frontend releases, plus the current and previous ones. It also keeps the 20 newest deploy backups and every runtime a kept release references. Run it without `--apply` to see the plan. It never follows symlinks or leaves the configured directories. Backups remain local until an off-host destination is configured.

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

`unison-backup.timer` makes a daily snapshot as the service user. Each snapshot is verified with `PRAGMA integrity_check` and the newest 14 are kept in `/var/lib/unison-backups`. Snapshots have mode 0640 in a 0750 directory: group `unisonapp` has no members, and only the off-host job joins it, for its own process. Check it with `systemctl list-timers unison-backup.timer` and `journalctl -u unison-backup`. To restore:
1. Stop `unison-backend`.
2. Copy the current database and its `-wal`/`-shm` files aside.
3. Install the chosen snapshot as `/var/lib/unison-backend/evolution.db`, owned by `unisonapp` with mode 0600, and remove the stale `-wal`/`-shm` files.
4. Start the service.

### Off-host copies

After every successful snapshot, `unison-backup.service` starts `unison-offsite.service` (`OnSuccess=`). The job runs as a transient `DynamicUser` with no capabilities. It receives the rclone credential through `LoadCredential=` and cannot see the live database, the deployment backups or `/etc/unison-backend`. It:
1. Copies the newest snapshot, which must be at most 36 hours old, into private scratch space, checks it and compresses it deterministically.
2. Uploads the archive and a SHA-256 manifest to `gdrive-vps-crypt:apps/unison.micutu.com`. That rclone crypt remote encrypts contents and names before they leave the VPS. An existing remote archive is never overwritten.
3. Downloads both again, compares hashes, restores the database in scratch space and runs `PRAGMA integrity_check`. A remote copy that differs fails the job; delete that archive and its manifest manually once you understand why.
4. Applies retention: the newest archive of each of the last 30 days and of each of the last 12 months. Only `evolution-<UTC stamp>.db.gz` archives and their manifests in that folder are ever deleted, and Google Drive moves deleted files to its trash.

Check it with `journalctl -u unison-offsite` and `sudo cat /var/lib/unison-offsite/status.json`. When the host's `swift-vapor-alert@.service` template exists, deployment installs drop-ins so that a failure of either backup unit sends the host's operator alert.

The credential is `/etc/unison-backend/offsite-rclone.conf` (root, 0600). It holds only the `gdrive` and `gdrive-vps-crypt` remotes, the same ones the other applications on this VPS use. The job skips itself while the file is absent. To provision or rotate it, copy those two sections from an authorised rclone configuration. The crypt passwords decrypt every archive: keep them in a password manager outside this VPS, because losing the server also loses this copy of them.

To restore from Google Drive:

```bash
offsite() { sudo python3 -I /opt/unison-backend/current/offsite.py "$@" --remote gdrive-vps-crypt:apps/unison.micutu.com --config /etc/unison-backend/offsite-rclone.conf; }
offsite list
offsite fetch --output /root/evolution-restore.db   # newest; or --name evolution-<stamp>.db.gz
```

`fetch` verifies the manifest, decompresses with a size limit, checks integrity and refuses to overwrite. Install the resulting file with the restore steps above. On a new server, run the same script from the repository with `rclone` and the configuration file.

Limits: root on this VPS can use the token to delete the Drive copies, which then stay in the Drive trash for 30 days. The token has full Drive scope and is shared with the other applications. Protecting against a compromised host requires a write-once (object-locked) destination.

### Deployment backups and rollback

Each private deployment backup records `previous-frontend`, `previous-backend` and the previous `service.unit`. To roll back:
1. Atomically replace **both** `current` symlinks with the previous release paths.
2. Restore the saved application Nginx files and the saved unit.
3. Run `systemctl daemon-reload`, validate Nginx, restart this service and reload Nginx.

Releases made before the per-release runtimes need their original unit, which runs from the checkout's `.venv`. Check public health and `release.json` again. Do not reset the developer checkout or automatically restore the database: additive migrations preserve existing and newly submitted ideas.

Before switching an API release, run `sudo python3 scripts/rollback_compatible.py /absolute/previous/api/release /var/lib/unison-backend/evolution.db` and require exit status 0. Releases predating moderation must not serve a database containing hidden ideas. Automatic deployment rollback enforces this guard; when an old API would reveal hidden content, it stops the API for operator review instead. The guard drops to the database's service account to preserve WAL/SHM ownership.

## Report review

Use `sudo python3 scripts/moderate.py queue` to inspect pending reports and [the moderation guide](MODERATION.md) to inspect, hide, restore and review. Queue access is restricted by SSH/sudo and database filesystem permissions; there is no public admin route. Hiding preserves content, covers the entire descendant branch and publishes a revision change for connected browsers. Restoration respects independent child rules. Existing copies/downloads cannot be recalled. Review remains manual until a notification channel is deliberately configured.

## Abuse or suspected compromise

1. Record time, health status, service revision and affected endpoint. Preserve journal and this vhost's logs privately.
2. For write abuse, temporarily deny POST only at this application's Nginx location; validate with `nginx -t`, then reload. Reads can remain available.
3. Take an online SQLite backup. Do not delete public data as a first response.
4. For engine/service compromise, stop this service and serve the last static release while investigating. The dedicated account must stay isolated.
5. Identify the exploit, patch and test in a temporary database. Restore from a verified backup only when needed.
6. Assess actual data exposure, applicable reporting duties and recovery evidence with the owner. No automated external messages are sent.

## Remaining operator work

Connect API health/error alerts to an owner-selected channel. The backup units already report failures through the host's alert template. Rehearse a full restore on a spare host occasionally; each off-host run restores only into scratch space. Decide retention and moderation rules, and review Cloudflare origin rules. These cannot be considered complete merely because a script or log exists.
