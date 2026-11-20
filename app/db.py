"""SQLite connection management and schema initialization.

The project deliberately keeps SQLite (single file, zero external services).
A single connection guarded by a re-entrant lock is enough for a single user
application; FastAPI's threadpool serializes access through the lock.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import DATABASE_URL

SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    max_concurrency INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    external_model_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT,
    description TEXT,
    capabilities_json TEXT NOT NULL,
    parameter_schema_json TEXT NOT NULL,
    input_constraints_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    storage_key TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    mode TEXT,
    parameters_json TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    external_task_id TEXT,
    external_video_id TEXT,
    error TEXT,
    result_text TEXT,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    completed_at INTEGER,
    parent_task_id TEXT,
    result_asset_id TEXT,
    conversation_id TEXT,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    favorited_at INTEGER,
    original_prompt TEXT,
    prompt_template_id TEXT,
    enhanced_prompt TEXT,
    enhance_error TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    PRIMARY KEY (task_id, tag_id)
);

CREATE TABLE IF NOT EXISTS prompt_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    as_system INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS model_prompt_templates (
    model_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    enhancer_model_id TEXT NOT NULL,
    capability TEXT,
    is_default INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (model_id, template_id)
);

CREATE TABLE IF NOT EXISTS prompt_enhance_config (
    id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    template_id TEXT,
    enhancer_model_id TEXT,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    title TEXT,
    system_prompt TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS task_assets (
    task_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (task_id, asset_id, role)
);

CREATE TABLE IF NOT EXISTS reference_tokens (
    token TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    invalidated_at INTEGER
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at ON tasks(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_conversation ON tasks(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_tags_tag ON task_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_task_tags_task ON task_tags(task_id);
CREATE INDEX IF NOT EXISTS idx_model_prompt_templates_model ON model_prompt_templates(model_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_task_assets_task ON task_assets(task_id);
CREATE INDEX IF NOT EXISTS idx_task_assets_asset ON task_assets(asset_id);
CREATE INDEX IF NOT EXISTS idx_reference_tokens_task ON reference_tokens(task_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
"""


class Database:
    """Thread-safe wrapper around a single SQLite connection."""

    def __init__(self, url: str) -> None:
        path = Path(url)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(url, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 10000")

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def query(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, seq)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _migrate(connection: sqlite3.Connection) -> None:
    """Best-effort compatibility with databases created by the old Next.js app."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()}
    if columns and "result_text" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN result_text TEXT")
        connection.commit()
    if columns and "conversation_id" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN conversation_id TEXT")
        connection.commit()
    if columns and "is_favorite" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        connection.commit()
    if columns and "favorited_at" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN favorited_at INTEGER")
        connection.commit()
    for column, ddl in (
        ("original_prompt", "ALTER TABLE tasks ADD COLUMN original_prompt TEXT"),
        ("prompt_template_id", "ALTER TABLE tasks ADD COLUMN prompt_template_id TEXT"),
        ("enhanced_prompt", "ALTER TABLE tasks ADD COLUMN enhanced_prompt TEXT"),
        ("enhance_error", "ALTER TABLE tasks ADD COLUMN enhance_error TEXT"),
    ):
        if columns and column not in columns:
            connection.execute(ddl)
            connection.commit()
    template_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(prompt_templates)").fetchall()
    }
    if template_columns and "as_system" not in template_columns:
        connection.execute("ALTER TABLE prompt_templates ADD COLUMN as_system INTEGER NOT NULL DEFAULT 0")
        connection.commit()
    binding_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(model_prompt_templates)").fetchall()
    }
    if binding_columns and "capability" not in binding_columns:
        connection.execute("ALTER TABLE model_prompt_templates ADD COLUMN capability TEXT")
        connection.commit()


def initialize_database(db: Database) -> None:
    with db._lock:
        db._conn.executescript(SCHEMA)
        _migrate(db._conn)
        db._conn.executescript(INDEXES)
