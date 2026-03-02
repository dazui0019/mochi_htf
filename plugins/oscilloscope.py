from __future__ import annotations

import base64
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote


_PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+8e8AAAAASUVORK5CYII=")


class Plugin:
    name = "oscilloscope"

    def __init__(self) -> None:
        self._config = self.default_config()

    def config_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {
                    "key": "address",
                    "type": "string",
                    "label": "示波器地址",
                    "description": "仪器地址（可选），供命令模板使用，例如 TCPIP0::192.168.1.10::INSTR",
                },
                {
                    "key": "capture_mode",
                    "type": "string",
                    "label": "截图模式",
                    "description": "placeholder 或 cli",
                },
                {
                    "key": "cli_command",
                    "type": "string",
                    "label": "截图命令模板",
                    "description": "mode=cli 时使用，支持占位符 {output} {address} {run_id} {step_id} {label}",
                },
                {
                    "key": "default_timeout",
                    "type": "number",
                    "label": "默认命令超时(秒)",
                    "description": "mode=cli 时的命令超时，默认 20 秒",
                },
            ]
        }

    def default_config(self) -> dict[str, Any]:
        return {
            "address": "",
            "capture_mode": "placeholder",
            "cli_command": "",
            "default_timeout": 20.0,
        }

    def set_config(self, config: dict[str, Any]) -> None:
        merged = self.default_config()
        merged.update(config or {})
        self._config = merged

    def actions(self) -> list[str]:
        return ["capture_screenshot"]

    def self_check(self) -> dict[str, Any]:
        mode = self._capture_mode({})
        if mode == "cli" and not str(self._config.get("cli_command", "")).strip():
            return {
                "ok": False,
                "message": "capture_mode=cli 但未配置 cli_command",
            }
        return {
            "ok": True,
            "message": f"oscilloscope ready (mode={mode})",
        }

    def run(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        params = params or {}

        if action != "capture_screenshot":
            raise ValueError(f"Unsupported action: {action}")

        context = self._context(params)
        run_id = str(context.get("run_id") or "manual")
        step_id = str(context.get("step_id") or "step")
        label = str(params.get("label") or context.get("step_name") or "scope_capture")

        reports_dir = Path(str(context.get("reports_dir") or (Path.cwd() / "reports"))).resolve()
        artifact_dir = reports_dir / run_id / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        output_path = artifact_dir / self._build_filename(params, step_id, label)
        mode = self._capture_mode(params)

        if mode == "placeholder":
            output_path.write_bytes(_PNG_1X1)
        elif mode == "cli":
            command_template = str(params.get("command") or self._config.get("cli_command", "")).strip()
            if not command_template:
                raise ValueError("Missing cli command. Please set config.cli_command or params.command")

            address = str(params.get("address") or self._config.get("address", "")).strip()
            timeout = self._read_timeout(params)
            command = command_template.format(
                output=str(output_path),
                address=address,
                run_id=run_id,
                step_id=step_id,
                label=label,
            )
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                stdout = (completed.stdout or "").strip()
                detail = stderr or stdout or f"command exit code {completed.returncode}"
                raise RuntimeError(f"Capture command failed: {detail}")
            if not output_path.exists():
                raise RuntimeError("Capture command succeeded but output file was not created")
        else:
            raise ValueError("capture_mode must be 'placeholder' or 'cli'")

        rel_from_reports = output_path.relative_to(reports_dir).as_posix()
        rel_from_run_artifacts = output_path.relative_to(artifact_dir).as_posix()
        artifact_url = f"/api/reports/{quote(run_id, safe='')}/artifacts/{quote(rel_from_run_artifacts, safe='/')}"
        artifact = {
            "type": "image",
            "label": label,
            "path": f"reports/{rel_from_reports}",
            "filename": output_path.name,
            "url": artifact_url,
            "size_bytes": output_path.stat().st_size,
            "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        return {
            "ok": True,
            "action": action,
            "capture_mode": mode,
            "artifacts": [artifact],
        }

    def _capture_mode(self, params: dict[str, Any]) -> str:
        mode = str(params.get("capture_mode") or self._config.get("capture_mode", "placeholder")).strip().lower()
        if not mode:
            mode = "placeholder"
        return mode

    def _read_timeout(self, params: dict[str, Any]) -> float:
        raw = params.get("timeout")
        if raw is None:
            raw = self._config.get("default_timeout", 20.0)
        try:
            timeout = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout must be a number") from exc
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        return timeout

    @staticmethod
    def _context(params: dict[str, Any]) -> dict[str, Any]:
        value = params.get("__htf_context")
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _slug(text: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text or "")
        cleaned = cleaned.strip("._-")
        return cleaned or "capture"

    def _build_filename(self, params: dict[str, Any], step_id: str, label: str) -> str:
        raw = params.get("filename")
        if raw:
            name = Path(str(raw)).name
            return name

        ext = str(params.get("ext", "png")).strip().lower().lstrip(".") or "png"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return f"{self._slug(step_id)}_{self._slug(label)}_{timestamp}.{ext}"


def create_plugin() -> Plugin:
    return Plugin()
