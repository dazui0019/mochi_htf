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
from mochi_htf.plugin_manager import PluginManager


def create_app() -> FastAPI:
    config = load_config()
    case_store = CaseStore(config.testcases_dir)
    plugin_manager = PluginManager(config.plugins_dir)
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
