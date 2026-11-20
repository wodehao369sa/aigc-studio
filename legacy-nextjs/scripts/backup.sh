#!/usr/bin/env bash
set -euo pipefail
SOURCE_DB="${DATABASE_URL:-/var/lib/aigc-studio/aigc-studio.db}"
SOURCE_MEDIA="${MEDIA_ROOT:-/var/lib/aigc-studio/media}"
DESTINATION="${1:?usage: backup.sh /path/to/backup-directory}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DESTINATION/$STAMP"
sqlite3 "$SOURCE_DB" ".backup '$DESTINATION/$STAMP/aigc-studio.db'"
tar -C "$(dirname "$SOURCE_MEDIA")" -czf "$DESTINATION/$STAMP/media.tar.gz" "$(basename "$SOURCE_MEDIA")"
echo "Backup written to $DESTINATION/$STAMP"
