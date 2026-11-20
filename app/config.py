"""Application configuration read from environment variables.

Keep every value explicit here so the rest of the code never calls
``os.environ`` directly.  Defaults target a local development checkout; the
systemd unit overrides them for production (see ``deploy/environment.example``).
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- storage -----------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", str(BASE_DIR / "data" / "aigc-studio.db"))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media"))).resolve()

# --- public facing -----------------------------------------------------------
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# --- provider credentials ----------------------------------------------------
PROVIDERS_CONFIG_PATH = Path(
    os.environ.get("PROVIDERS_CONFIG_PATH", str(BASE_DIR / "providers.yaml"))
)

# --- limits ------------------------------------------------------------------
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_RESULT_BYTES = int(os.environ.get("MAX_RESULT_BYTES", str(500 * 1024 * 1024)))
MEDIA_WARN_BYTES = int(os.environ.get("MEDIA_WARN_BYTES", str(4 * 1024**3)))
MEDIA_LIMIT_BYTES = int(os.environ.get("MEDIA_LIMIT_BYTES", str(5 * 1024**3)))

# --- outbound HTTP -----------------------------------------------------------
PROVIDER_TIMEOUT_SECONDS = float(os.environ.get("PROVIDER_TIMEOUT_SECONDS", "120"))

# --- in-process poller -------------------------------------------------------
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "5"))
# One provider task is polled per tick; keep the default conservative for 2C2G.
POLL_BATCH_SIZE = int(os.environ.get("POLL_BATCH_SIZE", "1"))
