"""Small persistent project store for the React tunnel workspace.

The legacy calculation engine remains unchanged.  This store only owns the
project catalogue and the saved tunnel configuration/results that the React
client needs to reopen a study.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("TUNNEL_PROJECTS_DB", ROOT / "data" / "tunnel_projects.sqlite3"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tunnel_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                client TEXT,
                location TEXT,
                designer TEXT,
                study_date TEXT,
                reference TEXT,
                calculation_type TEXT NOT NULL DEFAULT 'Iluminación de túneles',
                standard TEXT NOT NULL DEFAULT 'CIE 88:2004 / CIE 140',
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                config_json TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_opened_at TEXT
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tunnel_projects)").fetchall()}
        if "last_opened_at" not in columns:
            connection.execute("ALTER TABLE tunnel_projects ADD COLUMN last_opened_at TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in ("config_json", "result_json"):
        if item.get(key):
            try:
                item[key] = json.loads(item[key])
            except (TypeError, ValueError):
                item[key] = None
    return item


def list_projects() -> list[dict[str, Any]]:
    init_db()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM tunnel_projects ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    return [_record(row) for row in rows]


def get_project(project_id: int) -> dict[str, Any] | None:
    init_db()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM tunnel_projects WHERE id = ?", (project_id,)
        ).fetchone()
    return _record(row) if row else None


def mark_project_opened(project_id: int) -> dict[str, Any] | None:
    """Registra la última entrada del usuario en el estudio."""
    init_db()
    with _connect() as connection:
        connection.execute(
            "UPDATE tunnel_projects SET last_opened_at=? WHERE id=?",
            (_now(), project_id),
        )
    return get_project(project_id)


def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = _now()
    values = _normalise(payload)
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tunnel_projects
              (project_name, client, location, designer, study_date, reference,
               calculation_type, standard, notes, status, config_json,
               result_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*values, now, now),
        )
        project_id = cursor.lastrowid
    return get_project(int(project_id))  # type: ignore[return-value]


def update_project(project_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    init_db()
    if get_project(project_id) is None:
        return None
    values = _normalise(payload)
    with _connect() as connection:
        connection.execute(
            """
            UPDATE tunnel_projects SET
              project_name=?, client=?, location=?, designer=?, study_date=?,
              reference=?, calculation_type=?, standard=?, notes=?, status=?,
              config_json=?, result_json=?, updated_at=?
            WHERE id=?
            """,
            (*values, _now(), project_id),
        )
    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    init_db()
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM tunnel_projects WHERE id = ?", (project_id,)
        )
    return cursor.rowcount > 0


def _normalise(payload: dict[str, Any]) -> tuple[Any, ...]:
    name = str(payload.get("project_name") or "").strip()
    if not name:
        raise ValueError("El nombre del proyecto es obligatorio.")

    def json_value(key: str) -> str | None:
        value = payload.get(key)
        if value in (None, ""):
            return None
        return json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value

    return (
        name,
        str(payload.get("client") or "").strip() or None,
        str(payload.get("location") or "").strip() or None,
        str(payload.get("designer") or "").strip() or None,
        str(payload.get("study_date") or "").strip() or None,
        str(payload.get("reference") or "").strip() or None,
        str(payload.get("calculation_type") or "Iluminación de túneles").strip(),
        str(payload.get("standard") or "CIE 88:2004 / CIE 140").strip(),
        str(payload.get("notes") or "").strip() or None,
        str(payload.get("status") or "draft").strip(),
        json_value("config_json"),
        json_value("result_json"),
    )
