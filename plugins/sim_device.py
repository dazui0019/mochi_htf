from __future__ import annotations

import random


class Plugin:
    name = "sim_device"

    def actions(self) -> list[str]:
        return ["send_command", "read_state", "read_voltage"]

    def run(self, action: str, params: dict):
        if action == "send_command":
            cmd = str(params.get("cmd", ""))
            return {"ack": True, "cmd": cmd}

        if action == "read_state":
            return 1

        if action == "read_voltage":
            low = float(params.get("low", 4.8))
            high = float(params.get("high", 5.2))
            return round(random.uniform(low, high), 3)

        raise ValueError(f"Unsupported action: {action}")
