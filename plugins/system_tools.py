from __future__ import annotations

import time
from typing import Any


class Plugin:
    name = "system_tools"

    def config_schema(self) -> dict[str, Any]:
        return {"fields": []}

    def default_config(self) -> dict[str, Any]:
        return {}

    def actions(self) -> list[str]:
        return ["delay"]

    def self_check(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "system_tools is ready",
        }

    def run(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        params = params or {}

        if action == "delay":
            seconds = self._parse_delay_seconds(params)
            time.sleep(seconds)
            return {
                "ok": True,
                "action": action,
                "seconds": seconds,
            }

        raise ValueError(f"Unsupported action: {action}")

    @staticmethod
    def _parse_delay_seconds(params: dict[str, Any]) -> float:
        if "milliseconds" in params:
            raw = params.get("milliseconds")
            try:
                milliseconds = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("Param 'milliseconds' must be a number") from exc
            if milliseconds < 0:
                raise ValueError("Param 'milliseconds' must be >= 0")
            return milliseconds / 1000.0

        raw = params.get("seconds", 1.0)
        try:
            seconds = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Param 'seconds' must be a number") from exc
        if seconds < 0:
            raise ValueError("Param 'seconds' must be >= 0")
        return seconds


def create_plugin() -> Plugin:
    return Plugin()
