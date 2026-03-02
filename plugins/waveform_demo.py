from __future__ import annotations

import math
from typing import Any


class Plugin:
    name = "waveform_demo"

    def __init__(self) -> None:
        self._config = self.default_config()

    def config_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {
                    "key": "default_samples",
                    "type": "integer",
                    "label": "默认采样点数",
                    "description": "未在 params 指定时使用，默认 120",
                },
                {
                    "key": "default_interval_ms",
                    "type": "number",
                    "label": "默认采样间隔(ms)",
                    "description": "未在 params 指定时使用，默认 1.0 ms",
                },
            ]
        }

    def default_config(self) -> dict[str, Any]:
        return {
            "default_samples": 120,
            "default_interval_ms": 1.0,
        }

    def set_config(self, config: dict[str, Any]) -> None:
        merged = self.default_config()
        merged.update(config or {})
        self._config = merged

    def actions(self) -> list[str]:
        return ["capture_waveform"]

    def self_check(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "waveform_demo is ready",
        }

    def run(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action != "capture_waveform":
            raise ValueError(f"Unsupported action: {action}")

        params = params or {}
        samples = self._read_positive_int(params, "samples", int(self._config.get("default_samples", 120)))
        interval_ms = self._read_positive_float(params, "interval_ms", float(self._config.get("default_interval_ms", 1.0)))

        v_base = self._read_float(params, "voltage_base", 12.0)
        v_amp = self._read_float(params, "voltage_amp", 0.2)
        c_base = self._read_float(params, "current_base", 1.5)
        c_amp = self._read_float(params, "current_amp", 0.08)
        freq_hz = self._read_positive_float(params, "freq_hz", 100.0)

        voltage_points: list[dict[str, float]] = []
        current_points: list[dict[str, float]] = []
        csv_lines = ["t_ms,voltage_v,current_a"]

        for i in range(samples):
            t_ms = i * interval_ms
            t_s = t_ms / 1000.0
            phase = 2.0 * math.pi * freq_hz * t_s
            voltage = v_base + v_amp * math.sin(phase)
            current = c_base + c_amp * math.cos(phase + math.pi / 6.0)

            voltage_points.append({"t_ms": round(t_ms, 6), "value": round(voltage, 6)})
            current_points.append({"t_ms": round(t_ms, 6), "value": round(current, 6)})
            csv_lines.append(f"{t_ms:.6f},{voltage:.6f},{current:.6f}")

        csv_content = "\n".join(csv_lines)
        v_min = min(p["value"] for p in voltage_points)
        v_max = max(p["value"] for p in voltage_points)
        c_min = min(p["value"] for p in current_points)
        c_max = max(p["value"] for p in current_points)

        artifacts = [
            {
                "type": "waveform",
                "label": "voltage_current_waveform",
                "series": [
                    {"name": "voltage", "unit": "V", "points": voltage_points},
                    {"name": "current", "unit": "A", "points": current_points},
                ],
                "meta": {
                    "samples": samples,
                    "interval_ms": interval_ms,
                    "freq_hz": freq_hz,
                },
            },
            {
                "type": "csv",
                "label": "voltage_current_csv",
                "content": csv_content,
            },
            {
                "type": "log",
                "label": "waveform_summary",
                "content": (
                    f"samples={samples}, interval_ms={interval_ms}, freq_hz={freq_hz}\n"
                    f"voltage[V]: min={v_min:.6f}, max={v_max:.6f}\n"
                    f"current[A]: min={c_min:.6f}, max={c_max:.6f}"
                ),
            },
        ]

        return {
            "ok": True,
            "action": action,
            "summary": {
                "samples": samples,
                "interval_ms": interval_ms,
                "freq_hz": freq_hz,
                "voltage_min": round(v_min, 6),
                "voltage_max": round(v_max, 6),
                "current_min": round(c_min, 6),
                "current_max": round(c_max, 6),
            },
            "artifacts": artifacts,
        }

    @staticmethod
    def _read_float(params: dict[str, Any], key: str, default: float) -> float:
        value = params.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Param '{key}' must be a number") from exc

    @staticmethod
    def _read_positive_float(params: dict[str, Any], key: str, default: float) -> float:
        value = Plugin._read_float(params, key, default)
        if value <= 0:
            raise ValueError(f"Param '{key}' must be > 0")
        return value

    @staticmethod
    def _read_positive_int(params: dict[str, Any], key: str, default: int) -> int:
        raw = params.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Param '{key}' must be an integer") from exc
        if value <= 0:
            raise ValueError(f"Param '{key}' must be > 0")
        return value


def create_plugin() -> Plugin:
    return Plugin()
