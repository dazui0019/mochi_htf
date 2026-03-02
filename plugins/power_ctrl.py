from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class Plugin:
    name = "power_ctrl"

    def __init__(self) -> None:
        self._config = self.default_config()
        self._exe_path = Path(__file__).resolve().parent / "power_ctrl_cli_dir" / "power_ctrl_cli_dir.exe"

    def config_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {
                    "key": "address",
                    "type": "string",
                    "label": "电源地址",
                    "description": "VISA 资源地址，例如 USB0::0x2EC7::0x6700::xxxxxxxxxxxxxxxxxx::INSTR",
                }
            ]
        }

    def default_config(self) -> dict[str, Any]:
        return {"address": ""}

    def set_config(self, config: dict[str, Any]) -> None:
        merged = self.default_config()
        merged.update(config or {})
        self._config = merged

    def actions(self) -> list[str]:
        return [
            "set_power",
            "set_output",
        ]

    def self_check(self) -> dict[str, Any]:
        try:
            address = self._require_address()
            result = self._run_cli(["-a", address, "-t"], timeout=8.0)
            if result["returncode"] == 0:
                return {
                    "ok": True,
                    "message": "电源通信正常",
                    "address": address,
                    "stdout": result["stdout"],
                }
            return {
                "ok": False,
                "message": "电源通信失败",
                "address": address,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": str(exc),
            }

    def run(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        params = params or {}
        address = self._require_address()

        if action == "set_power":
            voltage = self._require_float(params, "voltage")
            current = self._require_float(params, "current")
            cli_result = self._run_cli(["-a", address, "-v", str(voltage), "-c", str(current)], timeout=10.0)
            self._raise_if_failed(cli_result, action)
            return {
                "ok": True,
                "action": action,
                "address": address,
                "voltage": voltage,
                "current": current,
                "stdout": cli_result["stdout"],
            }

        if action == "set_output":
            output = str(params.get("output", "")).strip().lower()
            if output not in {"on", "off"}:
                raise ValueError("Param 'output' must be 'on' or 'off'")
            cli_result = self._run_cli(["-a", address, "-o", output], timeout=10.0)
            self._raise_if_failed(cli_result, action)
            return {
                "ok": True,
                "action": action,
                "address": address,
                "output": output,
                "stdout": cli_result["stdout"],
            }

        raise ValueError(f"Unsupported action: {action}")

    def _require_address(self) -> str:
        address = str(self._config.get("address", "")).strip()
        if not address:
            raise ValueError("Plugin config 'address' is required, please set power supply VISA address first")
        return address

    @staticmethod
    def _require_float(params: dict[str, Any], key: str) -> float:
        if key not in params:
            raise ValueError(f"Missing required param: {key}")
        try:
            return float(params[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Param '{key}' must be a number") from exc

    def _run_cli(self, args: list[str], timeout: float) -> dict[str, Any]:
        if not self._exe_path.exists():
            raise RuntimeError(f"CLI executable not found: {self._exe_path}")

        command = [str(self._exe_path), *args]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": command,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }

    @staticmethod
    def _raise_if_failed(result: dict[str, Any], action: str) -> None:
        if int(result.get("returncode", -1)) == 0:
            return
        stderr = str(result.get("stderr", "")).strip()
        stdout = str(result.get("stdout", "")).strip()
        detail = stderr or stdout or "unknown error"
        raise RuntimeError(f"power_ctrl action '{action}' failed: {detail}")


def create_plugin() -> Plugin:
    return Plugin()
