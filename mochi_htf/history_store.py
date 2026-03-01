from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, db_path: Path, max_records: int) -> None:
        self._db_path = db_path
        self._max_records = max_records
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_history (
                    run_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    case_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    report_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_run_history_started_at
                ON run_history(started_at DESC)
                """
            )
            conn.commit()

    def save_report(self, report: dict[str, Any]) -> None:
        payload = json.dumps(report, ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_history(
                    run_id, case_id, case_name, status, started_at, ended_at, report_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report["run_id"],
                    "",
                    report.get("case_name", ""),
                    report.get("status", ""),
                    report.get("started_at", ""),
                    report.get("ended_at", None),
                    payload,
                ),
            )

            conn.execute(
                """
                DELETE FROM run_history
                WHERE run_id IN (
                    SELECT run_id
                    FROM run_history
                    ORDER BY started_at DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (self._max_records,),
            )
            conn.commit()

    def get_report(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM run_history WHERE run_id = ?",
                (run_id,),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row["report_json"])

    def list_history(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, self._max_records))

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, status, started_at, ended_at, report_json
                FROM run_history
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            report = json.loads(row["report_json"])
            result.append(
                {
                    "run_id": row["run_id"],
                    "case_name": report.get("case_name", ""),
                    "status": row["status"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "summary": report.get("summary", {}),
                }
            )

        return result
