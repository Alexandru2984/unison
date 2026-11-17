#!/usr/bin/env bash
# Deliberately specific to this VPS: no port guessing, Certbot or other vhosts.
set -Eeuo pipefail
umask 077
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if (( EUID != 0 )); then echo 'Run sudo ./deploy.sh after committing and validating the release.' >&2; exit 1; fi
if [[ "$project_dir" != /home/micu/unisonTrying ]]; then echo 'Review the fixed VPS paths before deploying from another checkout.' >&2; exit 1; fi
git_repo() { GIT_OPTIONAL_LOCKS=0 git -c safe.directory="$project_dir" -C "$project_dir" "$@"; }
exec 9>/run/lock/unison-deploy.lock
flock -n 9 || { echo 'Another Unison deployment is running.' >&2; exit 1; }
for program in git python3 npm nginx systemctl install runuser setsid curl tar; do command -v "$program" >/dev/null; done
id unisonapp >/dev/null
if [[ -n "$(git_repo status --porcelain)" ]]; then echo 'Commit or preserve working-tree changes before deployment.' >&2; exit 1; fi
[[ -f /etc/nginx/conf.d/cloudflare-origin-guard.conf && -f /etc/nginx/conf.d/cloudflare-realip.conf ]]
[[ -f /etc/letsencrypt/live/unison.micutu.com/fullchain.pem ]]
nginx -t
revision="$(git_repo rev-parse HEAD)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
site_root=/var/www/unison.micutu.com
api_root=/opt/unison-backend
backup_dir="/var/backups/unison-backend/$stamp"
frontend_release="$site_root/releases/${revision:0:12}-$stamp"
backend_release="$api_root/releases/${revision:0:12}-$stamp"
previous_frontend="$(readlink -f "$site_root/current")"
previous_backend=''
if [[ -L "$api_root/current" ]]; then previous_backend="$(readlink -f "$api_root/current")"; fi
if [[ -z "$previous_backend" && -z "${PREVIOUS_BACKEND_REVISION:-}" ]]; then
  echo 'First versioned deployment needs PREVIOUS_BACKEND_REVISION identifying the running source.' >&2
  exit 1
fi
owner="$(stat -c %U "$project_dir")"
run_builder() { runuser -u "$owner" -- bash -c 'umask 022; exec "$@"' unison-build "$@"; }
verification_dir=''
engine_build_dir=''
candidate_pid=''
armed=0
rollback() {
  local exit_status=$?
  trap - ERR
  set +e
  if [[ -n "$verification_dir" && -f "$verification_dir/server.log" && -d "$backup_dir" ]]; then
    install -m 0600 "$verification_dir/server.log" "$backup_dir/candidate.log"
    echo "Candidate diagnostics preserved at $backup_dir/candidate.log" >&2
  fi
  if (( armed )); then
    echo 'Deployment failed. Restoring previous frontend, API and Nginx files.' >&2
    ln -s "$previous_frontend" "$site_root/.rollback-$$"
    mv -Tf "$site_root/.rollback-$$" "$site_root/current"
    ln -s "$previous_backend" "$api_root/.rollback-$$"
    mv -Tf "$api_root/.rollback-$$" "$api_root/current"
    for name in unison.conf unison-limits.conf unison-headers.conf unison-proxy.conf; do
      case "$name" in
        unison.conf) destination=/etc/nginx/sites-available/unison ;;
        unison-limits.conf) destination=/etc/nginx/conf.d/unison-limits.conf ;;
        *) destination="/etc/nginx/snippets/$name" ;;
      esac
      if [[ -f "$backup_dir/$name" ]]; then install -m 0644 "$backup_dir/$name" "$destination"; else rm -f "$destination"; fi
    done
    # Retain the hardened versioned service: its previous-release symlink is
    # sufficient to restore code, even on the first migration from the checkout.
    systemctl daemon-reload
    systemctl restart unison-backend
    nginx -t && systemctl reload nginx
    echo "Rollback attempted. Inspect service health and private backups: $backup_dir" >&2
  fi
  exit "$exit_status"
}
cleanup() {
  if [[ -n "$candidate_pid" ]]; then kill -TERM -- "-$candidate_pid" 2>/dev/null || true; fi
  if [[ -n "$verification_dir" ]]; then rm -rf -- "$verification_dir"; fi
  if [[ -n "$engine_build_dir" ]]; then rm -rf -- "$engine_build_dir"; fi
}
trap rollback ERR
trap cleanup EXIT

# Build as the checkout owner, never as root. No development dependencies are
# added to the live environment; the test suite is run before this script.
run_builder "$project_dir/backend/.venv/bin/pip" install --disable-pip-version-check -r "$project_dir/backend/requirements.txt"
engine_build_dir="$(mktemp -d /tmp/unison-release-build.XXXXXX)"
chown "$owner" "$engine_build_dir"
# During the first migration the old service still reads the checkout's .uc.
# Build elsewhere so candidate verification cannot change its live behavior.
run_builder env UNISON_OUTPUT="$engine_build_dir/evolution.uc" python3 "$project_dir/scripts/build_unison.py"
run_builder npm --prefix "$project_dir/frontend" run build
run_builder env RUN_ENGINE_TESTS=1 UNISON_PROGRAM="$engine_build_dir/evolution.uc" "$project_dir/backend/.venv/bin/python" -m unittest discover -s "$project_dir/backend" -p test_engine.py -v
[[ -s "$project_dir/frontend/dist/index.html" ]]
# Explicitly set the parent mode: install -d otherwise applies the private
# deployment umask to a newly created /opt/unison-backend parent.
install -d -m 0755 "$site_root" "$site_root/releases" "$api_root" "$api_root/releases"
install -d -m 0700 "$backup_dir"
python3 "$project_dir/scripts/backup_database.py" /var/lib/unison-backend/evolution.db "$backup_dir/evolution.db"
for pair in '/etc/nginx/sites-available/unison:unison.conf' '/etc/nginx/conf.d/unison-limits.conf:unison-limits.conf' '/etc/nginx/snippets/unison-headers.conf:unison-headers.conf' '/etc/nginx/snippets/unison-proxy.conf:unison-proxy.conf' '/etc/systemd/system/unison-backend.service:service.unit'; do
  source_path="${pair%:*}"; backup_name="${pair##*:}"
  if [[ -f "$source_path" ]]; then cp "$source_path" "$backup_dir/$backup_name"; fi
 done
printf '%s\n' "$previous_frontend" > "$backup_dir/previous-frontend"
printf '%s\n' "$revision" > "$backup_dir/new-revision"

if [[ -z "$previous_backend" ]]; then
  previous_revision="$(git_repo rev-parse --verify "${PREVIOUS_BACKEND_REVISION}^{commit}")"
  previous_backend="$api_root/releases/${previous_revision:0:12}-bootstrap"
  # The caller supplies the pre-migration executable on the first rollout.
  [[ -n "${PREVIOUS_UNISON_PROGRAM:-}" && -s "$PREVIOUS_UNISON_PROGRAM" ]]
  if [[ ! -d "$previous_backend" ]]; then
    install -d -m 0755 "$previous_backend"
    git_repo archive "$previous_revision" backend | tar --strip-components=1 -x -C "$previous_backend"
    install -m 0644 "$PREVIOUS_UNISON_PROGRAM" "$previous_backend/evolution.uc"
    printf 'APP_REVISION=%s\n' "$previous_revision" > "$previous_backend/runtime.env"
    chmod -R a+rX "$previous_backend"
  fi
  [[ -s "$previous_backend/main.py" && -s "$previous_backend/evolution.uc" ]]
fi
printf '%s\n' "$previous_backend" > "$backup_dir/previous-backend"
install -d -m 0755 "$backend_release"
install -m 0644 "$project_dir/backend/main.py" "$project_dir/backend/security.py" "$project_dir/backend/requirements.txt" "$backend_release/"
install -m 0644 "$engine_build_dir/evolution.uc" "$backend_release/evolution.uc"
printf 'APP_REVISION=%s\n' "$revision" > "$backend_release/runtime.env"
chmod 0644 "$backend_release/runtime.env"
sha256sum "$backend_release/evolution.uc" > "$backend_release/engine.sha256"
chmod 0644 "$backend_release/engine.sha256"

# Start a candidate with a new disposable DB and a restricted write probe.
verification_dir="$(mktemp -d /tmp/unison-deploy-verify.XXXXXX)"
chown unisonapp:unisonapp "$verification_dir"
[[ -z "$(ss -H -ltn 'sport = :18791')" ]]
setsid runuser -u unisonapp -- env PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
  DB_PATH="$verification_dir/evolution.db" PUBLIC_ORIGIN=http://127.0.0.1:18791 \
  ALLOWED_HOSTS=127.0.0.1 APP_REVISION="$revision" UNISON_BIN="$project_dir/ucm-bin/ucm-bin" UNISON_PROGRAM="$backend_release/evolution.uc" \
  "$project_dir/backend/.venv/bin/uvicorn" main:app --app-dir "$backend_release" --host 127.0.0.1 --port 18791 --ws websockets --no-access-log > "$verification_dir/server.log" 2>&1 &
candidate_pid=$!
for ((attempt=0; attempt<30; attempt++)); do
  if curl -fsS --max-time 1 http://127.0.0.1:18791/api/health >/dev/null 2>&1; then break; fi
  kill -0 "$candidate_pid"
  sleep 0.2
done
kill -0 "$candidate_pid"
python3 "$project_dir/scripts/smoke_api.py" http://127.0.0.1:18791 "$revision"
kill -TERM -- "-$candidate_pid"
wait "$candidate_pid" || true
candidate_pid=''

install -d -m 0755 "$frontend_release"
cp -R "$project_dir/frontend/dist/." "$frontend_release/"
# Existing tabs may lazy-load an old hashed graph chunk after the symlink swap.
if [[ -d "$previous_frontend/assets" ]]; then cp --update=none "$previous_frontend/assets/"* "$frontend_release/assets/"; fi
printf '{"revision":"%s","built_at":"%s"}\n' "$revision" "$stamp" > "$frontend_release/release.json"
find "$frontend_release" -type d -exec chmod 0755 {} +
find "$frontend_release" -type f -exec chmod 0644 {} +

armed=1
install -m 0644 "$project_dir/infra/nginx/unison-limits.conf" /etc/nginx/conf.d/unison-limits.conf
install -m 0644 "$project_dir/infra/nginx/unison-headers.conf" /etc/nginx/snippets/unison-headers.conf
install -m 0644 "$project_dir/infra/nginx/unison-proxy.conf" /etc/nginx/snippets/unison-proxy.conf
install -m 0644 "$project_dir/nginx.conf" /etc/nginx/sites-available/unison
install -m 0644 "$project_dir/unison-backend.service" /etc/systemd/system/unison-backend.service
nginx -t
ln -s "$backend_release" "$api_root/.next-$$"
mv -Tf "$api_root/.next-$$" "$api_root/current"
ln -s "$frontend_release" "$site_root/.next-$$"
mv -Tf "$site_root/.next-$$" "$site_root/current"
systemctl daemon-reload
systemctl restart unison-backend
for ((attempt=0; attempt<30; attempt++)); do
  if curl -fsS --max-time 1 http://127.0.0.1:8097/api/health > "$backup_dir/health.json" 2>/dev/null; then break; fi
  sleep 0.2
done
python3 - "$backup_dir/health.json" "$revision" <<'PY'
import json, sys
health = json.load(open(sys.argv[1]))
assert health['status'] == 'ok' and health['engine_available'] and health['revision'] == sys.argv[2][:12], health
PY
systemctl reload nginx
curl -fsS --max-time 15 https://unison.micutu.com/api/health > "$backup_dir/public-health.json"
curl -fsS --max-time 15 https://unison.micutu.com/release.json > "$backup_dir/public-release.json"
python3 - "$backup_dir" "$revision" <<'PY'
import json, sys
from pathlib import Path
backup = Path(sys.argv[1])
assert json.loads((backup / 'public-health.json').read_text())['revision'] == sys.argv[2][:12]
assert json.loads((backup / 'public-release.json').read_text())['revision'] == sys.argv[2]
PY
armed=0
printf 'Deployed %s\nFrontend: %s\nAPI: %s\nPrivate backup: %s\n' "$revision" "$frontend_release" "$backend_release" "$backup_dir"
