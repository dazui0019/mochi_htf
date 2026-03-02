from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mochi_htf.case_store import CaseStore
from mochi_htf.config import load_config
from mochi_htf.executor import ExecutionService
from mochi_htf.history_store import HistoryStore
from mochi_htf.models import RunStartRequest, TestCase
from mochi_htf.plugin_manager import (
    PluginError,
    PluginExecutionError,
    PluginManager,
    PluginTimeoutError,
)


def create_app() -> FastAPI:
    config = load_config()
    case_store = CaseStore(config.testcases_dir)
    plugin_manager = PluginManager(config.plugins_dir, config.plugin_config_path)
    plugin_manager.refresh()
    history_store = HistoryStore(config.db_path, max_records=config.history_limit)
    executor = ExecutionService(
        config=config,
        case_store=case_store,
        plugin_manager=plugin_manager,
        history_store=history_store,
    )

    app = FastAPI(title="Mochi HTF", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.config = config
    app.state.case_store = case_store
    app.state.plugin_manager = plugin_manager
    app.state.executor = executor

    app.mount("/web", StaticFiles(directory=config.static_dir), name="web")

    @app.get("/")
    def root() -> FileResponse:
        index_path = config.static_dir / "index.html"
        return FileResponse(index_path)

    @app.get("/api/plugins")
    def list_plugins() -> dict[str, Any]:
        plugin_manager.refresh()
        return {"plugins": plugin_manager.list_plugins()}

    @app.get("/api/plugins/{plugin_name}/config")
    def get_plugin_config(plugin_name: str) -> dict[str, Any]:
        plugin_manager.refresh()
        try:
            return plugin_manager.get_plugin_details(plugin_name)
        except PluginError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/plugins/{plugin_name}/config")
    def put_plugin_config(plugin_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        plugin_manager.refresh()

        config_payload = payload.get("config", payload)
        if not isinstance(config_payload, dict):
            raise HTTPException(status_code=400, detail="Plugin config must be a JSON object")

        try:
            merged = plugin_manager.set_plugin_config(plugin_name, config_payload)
            details = plugin_manager.get_plugin_details(plugin_name)
            details["config"] = merged
            return {"ok": True, "plugin": details}
        except PluginError as exc:
            status = 404 if str(exc).startswith("Plugin not found") else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.post("/api/plugins/{plugin_name}/self-check")
    def plugin_self_check(plugin_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        plugin_manager.refresh()

        body = payload or {}
        timeout = body.get("timeout", 5.0)
        override_config = body.get("config")

        try:
            timeout = float(timeout)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid timeout: {timeout}") from exc

        if override_config is not None and not isinstance(override_config, dict):
            raise HTTPException(status_code=400, detail="Self-check config must be a JSON object")

        try:
            result = plugin_manager.self_check(
                plugin_name=plugin_name,
                timeout=timeout,
                override_config=override_config,
            )
            return {"ok": True, "plugin": plugin_name, "result": result}
        except PluginTimeoutError as exc:
            raise HTTPException(status_code=408, detail=str(exc)) from exc
        except PluginExecutionError as exc:
            detail = str(exc)
            if exc.details:
                detail = f"{detail}\n{exc.details}"
            raise HTTPException(status_code=500, detail=detail) from exc
        except PluginError as exc:
            status = 404 if str(exc).startswith("Plugin not found") else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.get("/api/cases")
    def list_cases() -> dict[str, Any]:
        return {"cases": case_store.list_cases()}

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, Any]:
        try:
            case = case_store.load_case(case_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return case.model_dump()

    @app.put("/api/cases/{case_id}")
    def put_case(case_id: str, case: TestCase) -> dict[str, Any]:
        path = case_store.save_case(case_id, case)
        return {"ok": True, "path": str(path)}

    @app.delete("/api/cases/{case_id}")
    def delete_case(case_id: str) -> dict[str, Any]:
        try:
            path = case_store.delete_case(case_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "path": str(path)}

    @app.post("/api/runs/start")
    def start_run(payload: RunStartRequest) -> dict[str, Any]:
        try:
            run_id = executor.start_run(payload.case_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return {"ok": True, "run_id": run_id}

    @app.post("/api/runs/stop")
    def stop_run() -> dict[str, Any]:
        accepted = executor.stop_run()
        return {"ok": True, "accepted": accepted}

    @app.get("/api/runs/current")
    def current_run() -> dict[str, Any]:
        return executor.current_run()

    @app.get("/api/runs/history")
    def history(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
        return {"history": executor.list_history(limit=limit)}

    @app.get("/api/reports/{run_id}.json")
    def report_json(run_id: str) -> dict[str, Any]:
        report = executor.get_report(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report

    @app.get("/api/reports/{run_id}.xlsx")
    def report_excel(run_id: str) -> FileResponse:
        try:
            output_path = executor.write_excel_report(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return FileResponse(
            path=output_path,
            filename=f"{run_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return app
