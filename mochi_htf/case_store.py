from __future__ import annotations

import json
from pathlib import Path

from mochi_htf.models import TestCase


class CaseStore:
    def __init__(self, testcases_dir: Path) -> None:
        self._testcases_dir = testcases_dir

    def list_cases(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []

        for path in sorted(self._testcases_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                case = TestCase.model_validate(data)
                result.append(
                    {
                        "id": case.id,
                        "name": case.name,
                        "version": case.version,
                        "file": path.name,
                    }
                )
            except Exception:  # noqa: BLE001
                result.append(
                    {
                        "id": path.stem,
                        "name": f"<invalid:{path.name}>",
                        "version": "",
                        "file": path.name,
                    }
                )

        return result

    def load_case(self, case_id: str) -> TestCase:
        case_path = self._find_case_path(case_id)
        if case_path is not None:
            data = json.loads(case_path.read_text(encoding="utf-8"))
            return TestCase.model_validate(data)

        raise FileNotFoundError(f"Case not found: {case_id}")

    def save_case(self, case_id: str, case: TestCase) -> Path:
        output_case = case
        if case.id != case_id:
            output_case = case.model_copy(update={"id": case_id})

        output_path = self._testcases_dir / f"{case_id}.json"
        output_path.write_text(output_case.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path

    def delete_case(self, case_id: str) -> Path:
        case_path = self._find_case_path(case_id)
        if case_path is None:
            raise FileNotFoundError(f"Case not found: {case_id}")
        case_path.unlink()
        return case_path

    def _find_case_path(self, case_id: str) -> Path | None:
        for path in sorted(self._testcases_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if data.get("id") == case_id:
                return path

        direct_path = self._testcases_dir / f"{case_id}.json"
        if direct_path.exists():
            return direct_path

        return None
