#!/usr/bin/env bash
# Syntax-check this repository's Nginx files against the host's shared
# includes, in an isolated prefix. Never reloads Nginx or writes live files.
# Run as root (sudo) so Nginx can read the certificate key, before deploying.
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d /tmp/unison-nginx-check.XXXXXX)"
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/snippets"
cp "$repo/infra/nginx/unison-headers.conf" "$repo/infra/nginx/unison-proxy.conf" "$work/snippets/"
cp /etc/nginx/snippets/block-dotfiles.conf "$work/snippets/"
cp /etc/nginx/mime.types "$work/"
cat > "$work/nginx.conf" <<CONF
pid $work/nginx.pid;
error_log $work/error.log;
events {}
http {
  include mime.types;
  include /etc/nginx/conf.d/cloudflare-origin-guard.conf;
  include /etc/nginx/conf.d/cloudflare-realip.conf;
  include $repo/infra/nginx/unison-limits.conf;
  include $repo/nginx.conf;
}
CONF
nginx -t -q -c "$work/nginx.conf" -p "$work"
echo "Nginx configuration for unison.micutu.com is valid."
