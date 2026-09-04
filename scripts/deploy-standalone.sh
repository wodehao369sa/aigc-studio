#!/usr/bin/env bash
set -euo pipefail

# Run from the project root after `pnpm build`. The server and static assets
# must come from the same .next build; mixing .next/ and standalone/.next/
# creates HTML/CSS hash mismatches and blank pages.
APP_DIR="${APP_DIR:-/opt/aigc-studio}"
BUILD_DIR="$APP_DIR/.next/standalone"

install -d "$BUILD_DIR/.next"
rsync -a --delete .next/standalone/ "$BUILD_DIR/"
rsync -a --delete .next/static/ "$BUILD_DIR/.next/static/"
if [ -d public ]; then rsync -a --delete public/ "$BUILD_DIR/public/"; fi
chown -R aigc:aigc "$BUILD_DIR"
systemctl restart aigc-studio.service
systemctl is-active --quiet aigc-studio.service
echo "AIGC Studio deployed from one consistent standalone build."
