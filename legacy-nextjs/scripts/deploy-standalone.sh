#!/usr/bin/env bash
set -euo pipefail

# Run from the project root after `pnpm build`. The server and static assets
# must come from the same .next build; mixing .next/ and standalone/.next/
# creates HTML/CSS hash mismatches and blank pages.
APP_DIR="${APP_DIR:-/opt/aigc-studio}"
BUILD_DIR="$APP_DIR/.next/standalone"

if [ ! -d .next/standalone ] || [ ! -f .next/standalone/server.js ]; then
  echo "Missing .next/standalone/server.js. Run 'pnpm build' in this checkout before deploying." >&2
  exit 1
fi

if [ ! -d .next/static ]; then
  echo "Missing .next/static. Refusing to deploy an incomplete build." >&2
  exit 1
fi

install -d -o aigc -g aigc /var/lib/aigc-studio/media /var/lib/aigc-studio /etc/aigc-studio

install -d "$BUILD_DIR/.next"
rsync -a --delete .next/standalone/ "$BUILD_DIR/"
rsync -a --delete .next/static/ "$BUILD_DIR/.next/static/"
if [ -d public ]; then rsync -a --delete public/ "$BUILD_DIR/public/"; fi
chown -R aigc:aigc "$BUILD_DIR"
chmod 0750 /var/lib/aigc-studio /var/lib/aigc-studio/media
systemctl restart aigc-studio.service
systemctl is-active --quiet aigc-studio.service
echo "AIGC Studio deployed from one consistent standalone build."
