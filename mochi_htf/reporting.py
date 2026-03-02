from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook


def _extract_artifact_paths(result: Any) -> str:
    if not isinstance(result, dict):
        return ""

    artifacts: list[dict[str, Any]] = []
    raw_artifacts = result.get("artifacts")
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts:
            if isinstance(item, dict):
                artifacts.append(item)

    # Backward compatibility for historical reports.
    legacy_artifact = result.get("artifact")
    if not artifacts and isinstance(legacy_artifact, dict):
        artifacts.append(legacy_artifact)

    paths: list[str] = []
    for artifact in artifacts:
        path = artifact.get("path") or artifact.get("url")
        if path:
            paths.append(str(path))

    return " | ".join(paths)


def write_report_json(report: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report_excel(report: dict[str, Any], output_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Result"

    headers = ["Item名", "Step名", "类型", "结果", "错误信息", "附件"]
    ws.append(headers)

    for item in report.get("items", []):
        for step in item.get("steps", []):
            ws.append(
                [
                    item.get("item_name", ""),
                    step.get("step_name", ""),
                    step.get("type", ""),
                    step.get("status", ""),
                    step.get("error", ""),
                    _extract_artifact_paths(step.get("result")),
                ]
            )

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 42
    ws.column_dimensions["F"].width = 60

    wb.save(output_path)
