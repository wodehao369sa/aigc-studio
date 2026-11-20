#!/usr/bin/env bash
set -euo pipefail
SOURCE_DB="${DATABASE_URL:-/var/lib/aigc-studio/aigc-studio.db}"
SOURCE_MEDIA="${MEDIA_ROOT:-/var/lib/aigc-studio/media}"
DESTINATION="${1:?usage: backup.sh /path/to/backup-directory}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DESTINATION/$STAMP"
python3 - "$SOURCE_DB" "$DESTINATION/$STAMP/aigc-studio.db" <<'PY'
import sqlite3
import sys

source, destination = sys.argv[1], sys.argv[2]
src = sqlite3.connect(source)
dst = sqlite3.connect(destination)
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
tar -C "$(dirname "$SOURCE_MEDIA")" -czf "$DESTINATION/$STAMP/media.tar.gz" "$(basename "$SOURCE_MEDIA")"
echo "Backup written to $DESTINATION/$STAMP"
