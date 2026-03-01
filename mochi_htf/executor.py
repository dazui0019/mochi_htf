from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mochi_htf.case_store import CaseStore
from mochi_htf.config import AppConfig
from mochi_htf.expression import ExpressionError, evaluate_expression
from mochi_htf.history_store import HistoryStore
from mochi_htf.models import TestCase, TestStep
from mochi_htf.plugin_manager import (
    PluginError,
    PluginExecutionError,
    PluginManager,
    PluginTimeoutError,
)
from mochi_htf.reporting import write_report_excel, write_report_json


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_value(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:  # noqa: BLE001
        return repr(value)


class ExecutionService:
    def __init__(
        self,
        config: AppConfig,
        case_store: CaseStore,
        plugin_manager: PluginManager,
        history_store: HistoryStore,
    ) -> None:
        self._config = config
        self._case_store = case_store
        self._plugin_manager = plugin_manager
        self._history_store = history_store

        self._state_lock = threading.Lock()
        self._current_report: dict[str, Any] | None = None
        self._runner_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def is_running(self) -> bool:
        with self._state_lock:
            return self._runner_thread is not None and self._runner_thread.is_alive()

    def start_run(self, case_id: str) -> str:
        with self._state_lock:
            if self._runner_thread is not None and self._runner_thread.is_alive():
                raise RuntimeError("A run is already in progress")

            case = self._case_store.load_case(case_id)
            self._plugin_manager.refresh()

            run_id = str(uuid.uuid4())
            self._stop_event.clear()

            thread = threading.Thread(
                target=self._run_case,
                args=(run_id, case),
                daemon=True,
            )

            self._runner_thread = thread
            thread.start()
            return run_id

    def stop_run(self) -> bool:
        with self._state_lock:
            running = self._runner_thread is not None and self._runner_thread.is_alive()

        if running:
            self._stop_event.set()
            return True

        return False

    def current_run(self) -> dict[str, Any]:
        with self._state_lock:
            running = self._runner_thread is not None and self._runner_thread.is_alive()
            report = copy.deepcopy(self._current_report)

        return {
            "running": running,
            "report": report,
        }

    def list_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._history_store.list_history(limit=limit)

    def get_report(self, run_id: str) -> dict[str, Any] | None:
        return self._history_store.get_report(run_id)

    def write_excel_report(self, run_id: str) -> Path:
        report = self._history_store.get_report(run_id)
        if report is None:
            raise FileNotFoundError(f"Report not found: {run_id}")

        output_path = self._config.reports_dir / f"{run_id}.xlsx"
        write_report_excel(report, output_path)
        return output_path

    def _set_current_report(self, report: dict[str, Any]) -> None:
        with self._state_lock:
            self._current_report = copy.deepcopy(report)

    def _run_case(self, run_id: str, case: TestCase) -> None:
        report: dict[str, Any] = {
            "run_id": run_id,
            "case_id": case.id,
            "case_name": case.name,
            "status": "Running",
            "started_at": _utc_now_iso(),
            "ended_at": None,
            "items": [],
            "summary": {
                "Pass": 0,
                "Fail": 0,
                "Error": 0,
                "Total": 0,
            },
        }

        self._set_current_report(report)

        try:
            for item in case.items:
                item_result = {
                    "item_id": item.id,
                    "item_name": item.name,
                    "status": "Pass",
                    "steps": [],
                }
                has_fail = False
                report["items"].append(item_result)
                self._set_current_report(report)

                for step in item.steps:
                    if self._stop_event.is_set():
                        item_result["status"] = "Stopped"
                        break

                    step_result = self._run_step(step)
                    item_result["steps"].append(step_result)

                    if step_result["status"] == "Fail":
                        has_fail = True

                    if step_result["status"] == "Error":
                        item_result["status"] = "Error"

                    self._refresh_summary(report)
                    self._set_current_report(report)

                    if step_result["status"] == "Error":
                        break

                if item_result["status"] not in {"Error", "Stopped"} and has_fail:
                    item_result["status"] = "Fail"

                self._refresh_summary(report)
                self._set_current_report(report)

                if self._stop_event.is_set():
                    break

        except Exception as exc:  # noqa: BLE001
            report["status"] = "Error"
            report["fatal_error"] = str(exc)
        finally:
            report["ended_at"] = _utc_now_iso()
            self._refresh_summary(report)
            self._finalize_run_status(report)

            json_path = self._config.reports_dir / f"{run_id}.json"
            write_report_json(report, json_path)
            self._history_store.save_report(report)
            self._set_current_report(report)

            with self._state_lock:
                self._runner_thread = None
                self._stop_event.clear()

    def _run_step(self, step: TestStep) -> dict[str, Any]:
        started_at = _utc_now_iso()
        start_time = time.perf_counter()

        status = "Pass"
        error_message = ""
        result: Any = None

        try:
            timeout = step.timeout or self._config.default_step_timeout
            result = self._plugin_manager.run_action(
                plugin_name=step.plugin,
                action=step.action,
                params=step.params,
                timeout=timeout,
            )

            if step.type == "Verify":
                expr = step.expr or "False"
                passed = evaluate_expression(expr, result)
                if not passed:
                    status = "Fail"

        except (PluginTimeoutError, PluginExecutionError, PluginError, ExpressionError) as exc:
            status = "Error"
            error_message = str(exc)
        except Exception as exc:  # noqa: BLE001
            status = "Error"
            error_message = f"Unexpected step error: {exc}"

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "step_id": step.id,
            "step_name": step.name,
            "type": step.type,
            "status": status,
            "error": error_message,
            "started_at": started_at,
            "ended_at": _utc_now_iso(),
            "duration_ms": elapsed_ms,
            "result": _safe_value(result),
        }

    @staticmethod
    def _refresh_summary(report: dict[str, Any]) -> None:
        summary = {
            "Pass": 0,
            "Fail": 0,
            "Error": 0,
            "Total": 0,
        }

        for item in report.get("items", []):
            for step in item.get("steps", []):
                status = step.get("status")
                if status in ("Pass", "Fail", "Error"):
                    summary[status] += 1

        summary["Total"] = summary["Pass"] + summary["Fail"] + summary["Error"]
        report["summary"] = summary

    def _finalize_run_status(self, report: dict[str, Any]) -> None:
        if report.get("status") == "Error":
            return

        if self._stop_event.is_set():
            report["status"] = "Stopped"
            return

        summary = report.get("summary", {})
        if summary.get("Error", 0) > 0:
            report["status"] = "Error"
        elif summary.get("Fail", 0) > 0:
            report["status"] = "Fail"
        else:
            report["status"] = "Pass"
