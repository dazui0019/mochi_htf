from __future__ import annotations

import random


class Plugin:
    name = "sim_device"

    def __init__(self) -> None:
        self._config = self.default_config()

    def config_schema(self) -> dict:
        return {
            "fields": [
                {
                    "key": "port",
                    "type": "string",
                    "label": "串口号",
                    "description": "例如 COM3 或 /dev/ttyUSB0",
                },
                {
                    "key": "baudrate",
                    "type": "integer",
                    "label": "波特率",
                    "description": "串口通信波特率",
                },
            ]
        }

    def default_config(self) -> dict:
        return {
            "port": "COM1",
            "baudrate": 115200,
        }

    def set_config(self, config: dict) -> None:
        merged = self.default_config()
        merged.update(config or {})
        self._config = merged

    def self_check(self) -> dict:
        return {
            "ok": True,
            "message": "sim_device is ready",
            "connection": {
                "port": self._config.get("port"),
                "baudrate": self._config.get("baudrate"),
            },
        }

    def actions(self) -> list[str]:
        return ["send_command", "read_state", "read_voltage"]

    def run(self, action: str, params: dict):
        if action == "send_command":
            cmd = str(params.get("cmd", ""))
            return {
                "ack": True,
                "cmd": cmd,
                "port": self._config.get("port"),
                "baudrate": self._config.get("baudrate"),
            }

        if action == "read_state":
            return 1

        if action == "read_voltage":
            low = float(params.get("low", 4.8))
            high = float(params.get("high", 5.2))
            return round(random.uniform(low, high), 3)

        raise ValueError(f"Unsupported action: {action}")
