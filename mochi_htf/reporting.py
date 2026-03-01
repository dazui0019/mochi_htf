from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook


def write_report_json(report: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report_excel(report: dict[str, Any], output_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Result"

    headers = ["Item名", "Step名", "类型", "结果", "错误信息"]
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
                ]
            )

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 42

    wb.save(output_path)
