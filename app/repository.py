"""SQLite data access for providers, models, assets, tasks and tokens.

All SQL lives here so services stay free of query strings.  Rows are converted
to the dataclasses in :mod:`app.entities` at this boundary.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .db import Database
from .entities import (
    Asset,
    Conversation,
    ModelConfig,
    ModelPromptBinding,
    PromptTemplate,
    Provider,
    Tag,
    Task,
    TaskAssetLink,
    TaskDetail,
    TaskListResult,
    TaskSummary,
)


def new_id() -> str:
    return str(uuid.uuid4())


def _decode(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


# --- providers ---------------------------------------------------------------

def list_providers(db: Database) -> list[Provider]:
    rows = db.query(
        """
        SELECT id, provider_type, name, base_url, enabled, max_concurrency
        FROM providers
        ORDER BY name
        """
    )
    return [
        Provider(
            id=row["id"],
            provider_type=row["provider_type"],
            name=row["name"],
            base_url=row["base_url"],
            enabled=bool(row["enabled"]),
            max_concurrency=row["max_concurrency"],
        )
        for row in rows
    ]


def get_provider(db: Database, provider_id: str) -> Provider | None:
    row = db.query_one(
        """
        SELECT id, provider_type, name, base_url, enabled, max_concurrency
        FROM providers WHERE id = ?
        """,
        (provider_id,),
    )
    return (
        Provider(
            id=row["id"],
            provider_type=row["provider_type"],
            name=row["name"],
            base_url=row["base_url"],
            enabled=bool(row["enabled"]),
            max_concurrency=row["max_concurrency"],
        )
        if row
        else None
    )


def upsert_provider(
    db: Database,
    provider_id: str,
    provider_type: str,
    name: str,
    base_url: str,
    enabled: bool = True,
    max_concurrency: int = 1,
) -> None:
    db.execute(
        """
        INSERT INTO providers (id, provider_type, name, base_url, enabled, max_concurrency)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            base_url = excluded.base_url,
            enabled = excluded.enabled,
            max_concurrency = excluded.max_concurrency
        """,
        (provider_id, provider_type, name, base_url, int(enabled), max_concurrency),
    )


def delete_providers_except(db: Database, provider_ids: list[str]) -> None:
    if not provider_ids:
        db.execute("DELETE FROM providers")
        return
    placeholders = ",".join("?" for _ in provider_ids)
    db.execute(f"DELETE FROM providers WHERE id NOT IN ({placeholders})", provider_ids)


def update_provider(db: Database, provider_id: str, enabled: bool, max_concurrency: int) -> bool:
    cursor = db.execute(
        "UPDATE providers SET enabled = ?, max_concurrency = ? WHERE id = ?",
        (int(enabled), max_concurrency, provider_id),
    )
    return cursor.rowcount > 0


# --- models ------------------------------------------------------------------


def _parse_model(row: sqlite3.Row) -> ModelConfig:
    return ModelConfig(
        id=row["id"],
        provider_id=row["provider_id"],
        external_model_id=row["external_model_id"],
        name=row["name"],
        version=row["version"],
        description=row["description"],
        capabilities=_decode(row["capabilities_json"], []),
        parameter_schema=_decode(row["parameter_schema_json"], []),
        input_constraints=_decode(row["input_constraints_json"], {}),
        enabled=bool(row["enabled"]),
        sort_order=row["sort_order"],
    )


def list_models(
    db: Database,
    provider_ids: list[str] | None = None,
    capability: str | None = None,
    include_disabled: bool = False,
) -> list[ModelConfig]:
    sql = """
        SELECT id, provider_id, external_model_id, name, version, description,
               capabilities_json, parameter_schema_json, input_constraints_json,
               enabled, sort_order
        FROM models
    """
    conditions: list[str] = []
    params: list[Any] = []
    if provider_ids is not None:
        if not provider_ids:
            return []
        placeholders = ",".join("?" for _ in provider_ids)
        conditions.append(f"provider_id IN ({placeholders})")
        params.extend(provider_ids)
    if not include_disabled:
        conditions.append("enabled = 1")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY sort_order, name"

    models = [_parse_model(row) for row in db.query(sql, params)]
    if capability:
        models = [model for model in models if capability in model.capabilities]
    return models


def get_model(db: Database, model_id: str) -> ModelConfig | None:
    row = db.query_one(
        """
        SELECT id, provider_id, external_model_id, name, version, description,
               capabilities_json, parameter_schema_json, input_constraints_json,
               enabled, sort_order
        FROM models WHERE id = ?
        """,
        (model_id,),
    )
    return _parse_model(row) if row else None


def create_model(db: Database, model: ModelConfig) -> None:
    db.execute(
        """
        INSERT INTO models (
            id, provider_id, external_model_id, name, version, description,
            capabilities_json, parameter_schema_json, input_constraints_json,
            enabled, sort_order
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            model.id,
            model.provider_id,
            model.external_model_id,
            model.name,
            model.version,
            model.description,
            json.dumps(model.capabilities, ensure_ascii=False),
            json.dumps(model.parameter_schema, ensure_ascii=False),
            json.dumps(model.input_constraints, ensure_ascii=False),
            int(model.enabled),
            model.sort_order,
        ),
    )


def update_model(db: Database, model: ModelConfig) -> bool:
    cursor = db.execute(
        """
        UPDATE models SET
            provider_id = ?, external_model_id = ?, name = ?, version = ?,
            description = ?, capabilities_json = ?, parameter_schema_json = ?,
            input_constraints_json = ?, enabled = ?, sort_order = ?
        WHERE id = ?
        """,
        (
            model.provider_id,
            model.external_model_id,
            model.name,
            model.version,
            model.description,
            json.dumps(model.capabilities, ensure_ascii=False),
            json.dumps(model.parameter_schema, ensure_ascii=False),
            json.dumps(model.input_constraints, ensure_ascii=False),
            int(model.enabled),
            model.sort_order,
            model.id,
        ),
    )
    return cursor.rowcount > 0


def delete_model(db: Database, model_id: str) -> bool:
    cursor = db.execute("DELETE FROM models WHERE id = ?", (model_id,))
    return cursor.rowcount > 0


# --- assets ------------------------------------------------------------------


def _parse_asset(row: sqlite3.Row) -> Asset:
    return Asset(
        id=row["id"],
        storage_key=row["storage_key"],
        original_filename=row["original_filename"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        metadata=_decode(row["metadata_json"], {}),
        created_at=row["created_at"],
    )


def get_asset(db: Database, asset_id: str) -> Asset | None:
    row = db.query_one(
        """
        SELECT id, storage_key, original_filename, mime_type, size_bytes,
               metadata_json, created_at
        FROM assets WHERE id = ?
        """,
        (asset_id,),
    )
    return _parse_asset(row) if row else None


def insert_asset(db: Database, asset: Asset) -> None:
    db.execute(
        """
        INSERT INTO assets (
            id, storage_key, original_filename, mime_type, size_bytes,
            metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset.id,
            asset.storage_key,
            asset.original_filename,
            asset.mime_type,
            asset.size_bytes,
            json.dumps(asset.metadata, ensure_ascii=False),
            asset.created_at,
        ),
    )


def delete_asset(db: Database, asset_id: str) -> None:
    db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def count_asset_references(db: Database, asset_id: str) -> int:
    row = db.query_one("SELECT COUNT(*) AS count FROM task_assets WHERE asset_id = ?", (asset_id,))
    return int(row["count"]) if row else 0


# --- tasks -------------------------------------------------------------------


def _parse_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        provider_id=row["provider_id"],
        model_id=row["model_id"],
        capability=row["capability"],
        mode=row["mode"],
        parameters=_decode(row["parameters_json"], {}),
        status=row["status"],
        progress=row["progress"],
        external_task_id=row["external_task_id"],
        external_video_id=row["external_video_id"],
        error=row["error"],
        result_text=row["result_text"] if "result_text" in row.keys() else None,
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        parent_task_id=row["parent_task_id"],
        result_asset_id=row["result_asset_id"],
        conversation_id=row["conversation_id"] if "conversation_id" in row.keys() else None,
        is_favorite=bool(row["is_favorite"]) if "is_favorite" in row.keys() else False,
        favorited_at=row["favorited_at"] if "favorited_at" in row.keys() else None,
        original_prompt=row["original_prompt"] if "original_prompt" in row.keys() else None,
        prompt_template_id=row["prompt_template_id"] if "prompt_template_id" in row.keys() else None,
        enhanced_prompt=row["enhanced_prompt"] if "enhanced_prompt" in row.keys() else None,
        enhance_error=row["enhance_error"] if "enhance_error" in row.keys() else None,
    )


def get_task(db: Database, task_id: str) -> Task | None:
    row = db.query_one(
        """
        SELECT id, provider_id, model_id, capability, mode, parameters_json,
               status, progress, external_task_id, external_video_id, error,
               result_text, created_at, started_at, completed_at,
               parent_task_id, result_asset_id, conversation_id,
               is_favorite, favorited_at,
               original_prompt, prompt_template_id, enhanced_prompt, enhance_error
        FROM tasks WHERE id = ?
        """,
        (task_id,),
    )
    return _parse_task(row) if row else None


def insert_task(db: Database, task: Task) -> None:
    db.execute(
        """
        INSERT INTO tasks (
            id, provider_id, model_id, capability, mode, parameters_json,
            status, progress, external_task_id, external_video_id, error,
            result_text, created_at, started_at, completed_at,
            parent_task_id, result_asset_id, conversation_id,
            is_favorite, favorited_at,
            original_prompt, prompt_template_id, enhanced_prompt, enhance_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.id,
            task.provider_id,
            task.model_id,
            task.capability,
            task.mode,
            json.dumps(task.parameters, ensure_ascii=False),
            task.status,
            task.progress,
            task.external_task_id,
            task.external_video_id,
            task.error,
            task.result_text,
            task.created_at,
            task.started_at,
            task.completed_at,
            task.parent_task_id,
            task.result_asset_id,
            task.conversation_id,
            int(task.is_favorite),
            task.favorited_at,
            task.original_prompt,
            task.prompt_template_id,
            task.enhanced_prompt,
            task.enhance_error,
        ),
    )


def update_task_fields(db: Database, task_id: str, **fields: Any) -> bool:
    if not fields:
        return False
    columns = ", ".join(f"{name} = ?" for name in fields)
    values = list(fields.values())
    cursor = db.execute(f"UPDATE tasks SET {columns} WHERE id = ?", (*values, task_id))
    return cursor.rowcount > 0


def insert_task_asset(db: Database, task_id: str, asset_id: str, role: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO task_assets (task_id, asset_id, role) VALUES (?, ?, ?)",
        (task_id, asset_id, role),
    )


def list_task_assets(db: Database, task_id: str) -> list[TaskAssetLink]:
    rows = db.query(
        """
        SELECT ta.role, a.id
        FROM task_assets ta
        JOIN assets a ON a.id = ta.asset_id
        WHERE ta.task_id = ?
        ORDER BY ta.role
        """,
        (task_id,),
    )
    links: list[TaskAssetLink] = []
    for row in rows:
        asset = get_asset(db, row["id"])
        if asset:
            links.append(TaskAssetLink(role=row["role"], asset=asset))
    return links


def get_task_detail(db: Database, task_id: str) -> TaskDetail | None:
    task = get_task(db, task_id)
    if not task:
        return None
    row = db.query_one("SELECT name FROM models WHERE id = ?", (task.model_id,))
    return TaskDetail(
        **{
            **task.__dict__,
            "model_name": row["name"] if row else task.model_id,
            "assets": list_task_assets(db, task.id),
            "tags": get_task_tags(db, task.id),
        }
    )


def list_task_summaries(
    db: Database,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    capability: str | None = None,
    favorite_only: bool = False,
    tag: str | None = None,
    order_by: str = "created_at",
) -> TaskListResult:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    # 对话任务只在会话内展示，不进入任务记录。
    conditions: list[str] = ["t.conversation_id IS NULL"]
    params: list[Any] = []
    if status:
        conditions.append("t.status = ?")
        params.append(status)
    if capability:
        conditions.append("t.capability = ?")
        params.append(capability)
    if favorite_only:
        conditions.append("t.is_favorite = 1")
        conditions.append("t.status = 'succeeded'")
        conditions.append("t.result_asset_id IS NOT NULL")
    if tag:
        conditions.append(
            "t.id IN (SELECT tt.task_id FROM task_tags tt "
            "JOIN tags tg ON tg.id = tt.tag_id WHERE tg.name = ?)"
        )
        params.append(tag)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total_row = db.query_one(f"SELECT COUNT(*) AS count FROM tasks t{where}", params)
    total = int(total_row["count"]) if total_row else 0

    order = (
        "t.favorited_at DESC, t.created_at DESC"
        if order_by == "favorited_at"
        else "t.created_at DESC"
    )
    rows = db.query(
        f"""
        SELECT
            t.id, t.status, t.capability, t.mode,
            json_extract(t.parameters_json, '$.prompt') AS prompt,
            COALESCE(m.name, t.model_id) AS model_name,
            t.created_at, t.completed_at, t.progress, t.error,
            t.result_asset_id, a.mime_type AS result_mime_type,
            t.result_text, t.is_favorite, t.favorited_at
        FROM tasks t
        LEFT JOIN models m ON m.id = t.model_id
        LEFT JOIN assets a ON a.id = t.result_asset_id
        {where}
        ORDER BY {order}
        LIMIT ? OFFSET ?
        """,
        (*params, page_size, (page - 1) * page_size),
    )
    tags_map = tags_for_tasks(db, [row["id"] for row in rows])
    items = [
        TaskSummary(
            id=row["id"],
            status=row["status"],
            capability=row["capability"],
            mode=row["mode"],
            prompt=row["prompt"] if isinstance(row["prompt"], str) else None,
            model_name=row["model_name"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            progress=row["progress"],
            error=row["error"],
            result_asset_id=row["result_asset_id"],
            result_mime_type=row["result_mime_type"],
            result_text=row["result_text"],
            is_favorite=bool(row["is_favorite"]),
            favorited_at=row["favorited_at"],
            tags=tags_map.get(row["id"], []),
        )
        for row in rows
    ]
    return TaskListResult(items=items, page=page, page_size=page_size, total=total)


def find_pollable_task(db: Database) -> Task | None:
    """Return the next task the in-process poller should work on.

    Running tasks with an external id are queried first; pending tasks are
    submitted when capacity allows.  Ordering is by creation time so the oldest
    task always makes progress.
    """
    row = db.query_one(
        """
        SELECT id FROM tasks
        WHERE status = 'running' AND external_task_id IS NOT NULL
        ORDER BY created_at ASC
        LIMIT 1
        """
    )
    if row:
        return get_task(db, row["id"])
    row = db.query_one(
        """
        SELECT id FROM tasks
        WHERE status = 'pending' AND external_task_id IS NULL
        ORDER BY created_at ASC
        LIMIT 1
        """
    )
    return get_task(db, row["id"]) if row else None


def count_running(db: Database, provider_id: str) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS count FROM tasks WHERE provider_id = ? AND status = 'running'",
        (provider_id,),
    )
    return int(row["count"]) if row else 0


# --- tags --------------------------------------------------------------------


def _parse_tag(row: sqlite3.Row) -> Tag:
    return Tag(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        count=int(row["count"]) if "count" in row.keys() else 0,
    )


def list_tags(db: Database) -> list[Tag]:
    rows = db.query(
        """
        SELECT t.id, t.name, t.created_at, COUNT(tt.task_id) AS count
        FROM tags t
        LEFT JOIN task_tags tt ON tt.tag_id = t.id
        GROUP BY t.id
        ORDER BY count DESC, t.name
        """
    )
    return [_parse_tag(row) for row in rows]


def get_task_tags(db: Database, task_id: str) -> list[str]:
    rows = db.query(
        """
        SELECT t.name
        FROM task_tags tt
        JOIN tags t ON t.id = tt.tag_id
        WHERE tt.task_id = ?
        ORDER BY t.name
        """,
        (task_id,),
    )
    return [row["name"] for row in rows]


def tags_for_tasks(db: Database, task_ids: list[str]) -> dict[str, list[str]]:
    if not task_ids:
        return {}
    placeholders = ",".join("?" for _ in task_ids)
    rows = db.query(
        f"""
        SELECT tt.task_id, t.name
        FROM task_tags tt
        JOIN tags t ON t.id = tt.tag_id
        WHERE tt.task_id IN ({placeholders})
        ORDER BY t.name
        """,
        task_ids,
    )
    result: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
    for row in rows:
        result[row["task_id"]].append(row["name"])
    return result


def get_or_create_tag(db: Database, name: str, created_at: int) -> str:
    row = db.query_one("SELECT id FROM tags WHERE name = ?", (name,))
    if row:
        return row["id"]
    tag_id = new_id()
    db.execute(
        "INSERT INTO tags (id, name, created_at) VALUES (?, ?, ?)",
        (tag_id, name, created_at),
    )
    return tag_id


def set_task_tags(db: Database, task_id: str, names: list[str], created_at: int) -> None:
    db.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip()
        if not name or len(name) > 40 or name in seen:
            continue
        seen.add(name)
        tag_id = get_or_create_tag(db, name, created_at)
        db.execute(
            "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)",
            (task_id, tag_id),
        )


def set_task_favorite(db: Database, task_id: str, favorite: bool, favorited_at: int | None) -> None:
    db.execute(
        "UPDATE tasks SET is_favorite = ?, favorited_at = ? WHERE id = ?",
        (int(favorite), favorited_at, task_id),
    )


def count_favorite_results(db: Database) -> int:
    row = db.query_one(
        """
        SELECT COUNT(*) AS count FROM tasks
        WHERE conversation_id IS NULL AND is_favorite = 1
          AND status = 'succeeded' AND result_asset_id IS NOT NULL
        """
    )
    return int(row["count"]) if row else 0


def count_tags_in_favorites(db: Database) -> dict[str, int]:
    rows = db.query(
        """
        SELECT tg.name AS name, COUNT(DISTINCT t.id) AS count
        FROM task_tags tt
        JOIN tags tg ON tg.id = tt.tag_id
        JOIN tasks t ON t.id = tt.task_id
        WHERE t.conversation_id IS NULL AND t.is_favorite = 1
          AND t.status = 'succeeded' AND t.result_asset_id IS NOT NULL
        GROUP BY tg.id
        """
    )
    return {row["name"]: int(row["count"]) for row in rows}


def delete_task(db: Database, task_id: str) -> None:
    db.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    db.execute("DELETE FROM task_assets WHERE task_id = ?", (task_id,))
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


# --- conversations -----------------------------------------------------------


def _parse_conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        provider_id=row["provider_id"],
        model_id=row["model_id"],
        title=row["title"],
        system_prompt=row["system_prompt"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_conversation(db: Database, conversation: Conversation) -> None:
    db.execute(
        """
        INSERT INTO conversations (id, provider_id, model_id, title, system_prompt, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conversation.id,
            conversation.provider_id,
            conversation.model_id,
            conversation.title,
            conversation.system_prompt,
            conversation.created_at,
            conversation.updated_at,
        ),
    )


def get_conversation(db: Database, conversation_id: str) -> Conversation | None:
    row = db.query_one(
        """
        SELECT id, provider_id, model_id, title, system_prompt, created_at, updated_at
        FROM conversations WHERE id = ?
        """,
        (conversation_id,),
    )
    return _parse_conversation(row) if row else None


def list_conversations(db: Database) -> list[Conversation]:
    rows = db.query(
        """
        SELECT id, provider_id, model_id, title, system_prompt, created_at, updated_at
        FROM conversations ORDER BY updated_at DESC
        """
    )
    return [_parse_conversation(row) for row in rows]


def update_conversation_fields(db: Database, conversation_id: str, **fields: Any) -> bool:
    if not fields:
        return False
    columns = ", ".join(f"{name} = ?" for name in fields)
    cursor = db.execute(
        f"UPDATE conversations SET {columns} WHERE id = ?", (*fields.values(), conversation_id)
    )
    return cursor.rowcount > 0


def list_conversation_tasks(db: Database, conversation_id: str) -> list[Task]:
    rows = db.query(
        """
        SELECT id, provider_id, model_id, capability, mode, parameters_json,
               status, progress, external_task_id, external_video_id, error,
               result_text, created_at, started_at, completed_at,
               parent_task_id, result_asset_id, conversation_id
        FROM tasks WHERE conversation_id = ? ORDER BY created_at ASC, id ASC
        """,
        (conversation_id,),
    )
    return [_parse_task(row) for row in rows]


def delete_conversation(db: Database, conversation_id: str) -> None:
    db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


# --- reference tokens --------------------------------------------------------


def create_reference_token(db: Database, token: str, task_id: str, asset_id: str, expires_at: int) -> None:
    db.execute(
        """
        INSERT INTO reference_tokens (token, task_id, asset_id, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (token, task_id, asset_id, expires_at),
    )


def get_reference_token(db: Database, task_id: str, asset_id: str, now: int) -> str | None:
    row = db.query_one(
        """
        SELECT token FROM reference_tokens
        WHERE task_id = ? AND asset_id = ? AND invalidated_at IS NULL AND expires_at > ?
        LIMIT 1
        """,
        (task_id, asset_id, now),
    )
    return row["token"] if row else None


def get_reference_asset(db: Database, token: str, now: int) -> Asset | None:
    row = db.query_one(
        """
        SELECT a.id, a.storage_key, a.original_filename, a.mime_type,
               a.size_bytes, a.metadata_json, a.created_at
        FROM reference_tokens rt
        JOIN assets a ON a.id = rt.asset_id
        WHERE rt.token = ?
          AND rt.invalidated_at IS NULL
          AND rt.expires_at > ?
        """,
        (token, now),
    )
    return _parse_asset(row) if row else None


def invalidate_task_tokens(db: Database, task_id: str, now: int) -> None:
    db.execute(
        "UPDATE reference_tokens SET invalidated_at = ? WHERE task_id = ? AND invalidated_at IS NULL",
        (now, task_id),
    )


# --- prompt enhancement ------------------------------------------------------


def _parse_prompt_template(row: sqlite3.Row) -> PromptTemplate:
    return PromptTemplate(
        id=row["id"],
        name=row["name"],
        content=row["content"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        as_system=bool(row["as_system"]) if "as_system" in row.keys() else False,
    )


def create_prompt_template(db: Database, template: PromptTemplate) -> None:
    db.execute(
        """
        INSERT INTO prompt_templates (id, name, content, as_system, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            template.id,
            template.name,
            template.content,
            int(template.as_system),
            template.created_at,
            template.updated_at,
        ),
    )


def list_prompt_templates(db: Database) -> list[PromptTemplate]:
    rows = db.query(
        "SELECT id, name, content, as_system, created_at, updated_at FROM prompt_templates ORDER BY name"
    )
    return [_parse_prompt_template(row) for row in rows]


def get_prompt_template(db: Database, template_id: str) -> PromptTemplate | None:
    row = db.query_one(
        "SELECT id, name, content, as_system, created_at, updated_at FROM prompt_templates WHERE id = ?",
        (template_id,),
    )
    return _parse_prompt_template(row) if row else None


def update_prompt_template(db: Database, template: PromptTemplate) -> bool:
    cursor = db.execute(
        "UPDATE prompt_templates SET name = ?, content = ?, as_system = ?, updated_at = ? WHERE id = ?",
        (template.name, template.content, int(template.as_system), template.updated_at, template.id),
    )
    return cursor.rowcount > 0


def delete_prompt_template(db: Database, template_id: str) -> None:
    db.execute("DELETE FROM model_prompt_templates WHERE template_id = ?", (template_id,))
    db.execute("DELETE FROM prompt_templates WHERE id = ?", (template_id,))


def _parse_binding(row: sqlite3.Row) -> ModelPromptBinding:
    return ModelPromptBinding(
        model_id=row["model_id"],
        template_id=row["template_id"],
        enhancer_model_id=row["enhancer_model_id"],
        is_default=bool(row["is_default"]),
        sort_order=row["sort_order"],
        capability=row["capability"] if "capability" in row.keys() else None,
    )


def list_bindings(db: Database, model_id: str) -> list[ModelPromptBinding]:
    rows = db.query(
        """
        SELECT model_id, template_id, enhancer_model_id, capability, is_default, sort_order
        FROM model_prompt_templates WHERE model_id = ? ORDER BY sort_order, template_id
        """,
        (model_id,),
    )
    return [_parse_binding(row) for row in rows]


def get_default_binding(
    db: Database, model_id: str, capability: str | None = None
) -> ModelPromptBinding | None:
    rows = list_bindings(db, model_id)
    if capability:
        for row in rows:
            if row.is_default and row.capability == capability:
                return row
    for row in rows:
        if row.is_default:
            return row
    return rows[0] if rows else None


def set_bindings(db: Database, model_id: str, bindings: list[ModelPromptBinding]) -> None:
    db.execute("DELETE FROM model_prompt_templates WHERE model_id = ?", (model_id,))
    for binding in bindings:
        db.execute(
            """
            INSERT INTO model_prompt_templates
              (model_id, template_id, enhancer_model_id, capability, is_default, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                model_id,
                binding.template_id,
                binding.enhancer_model_id,
                binding.capability,
                int(binding.is_default),
                binding.sort_order,
            ),
        )


# --- global enhancement default ---------------------------------------------


def get_enhance_config(db: Database) -> dict | None:
    row = db.query_one(
        """
        SELECT id, enabled, template_id, enhancer_model_id, updated_at
        FROM prompt_enhance_config WHERE id = 'default'
        """
    )
    return dict(row) if row else None


def set_enhance_config(
    db: Database,
    enabled: bool,
    template_id: str | None,
    enhancer_model_id: str | None,
    updated_at: int,
) -> None:
    db.execute(
        """
        INSERT INTO prompt_enhance_config (id, enabled, template_id, enhancer_model_id, updated_at)
        VALUES ('default', ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            enabled = excluded.enabled,
            template_id = excluded.template_id,
            enhancer_model_id = excluded.enhancer_model_id,
            updated_at = excluded.updated_at
        """,
        (int(enabled), template_id, enhancer_model_id, updated_at),
    )
