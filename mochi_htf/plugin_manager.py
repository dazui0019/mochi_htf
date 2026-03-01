from __future__ import annotations

import importlib.util
import inspect
import multiprocessing as mp
import queue
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PluginError(RuntimeError):
    """Base plugin error."""


class PluginTimeoutError(PluginError):
    """Raised when plugin execution exceeds timeout."""


class PluginExecutionError(PluginError):
    """Raised when plugin execution fails."""

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.details = details or ""


@dataclass(frozen=True)
class PluginInfo:
    name: str
    path: Path
    actions: list[str]


def _load_module_from_path(path: Path):
    module_name = f"mochi_htf_plugin_{path.stem}_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginError(f"Unable to load plugin module from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_plugin_instance(module: Any):
    factory = getattr(module, "create_plugin", None)
    if callable(factory):
        plugin = factory()
    else:
        cls = getattr(module, "Plugin", None)
        if not inspect.isclass(cls):
            raise PluginError("Plugin module must expose create_plugin() or class Plugin")
        plugin = cls()

    run_callable = getattr(plugin, "run", None)
    if not callable(run_callable):
        raise PluginError("Plugin instance must implement run(action, params)")

    return plugin


def _plugin_worker(module_path: str, action: str, params: dict[str, Any], out_queue: mp.Queue) -> None:
    try:
        module = _load_module_from_path(Path(module_path))
        plugin = _build_plugin_instance(module)
        result = plugin.run(action, params)
        out_queue.put({"ok": True, "result": result})
    except Exception as exc:  # noqa: BLE001
        out_queue.put(
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


class PluginManager:
    def __init__(self, plugins_dir: Path) -> None:
        self._plugins_dir = plugins_dir
        self._plugins: dict[str, PluginInfo] = {}
        self._load_errors: dict[str, str] = {}

    def refresh(self) -> None:
        plugins: dict[str, PluginInfo] = {}
        errors: dict[str, str] = {}

        for path in sorted(self._plugins_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue

            try:
                module = _load_module_from_path(path)
                plugin = _build_plugin_instance(module)
                name = str(getattr(plugin, "name", path.stem))

                actions_callable = getattr(plugin, "actions", None)
                actions = list(actions_callable()) if callable(actions_callable) else []

                if name in plugins:
                    raise PluginError(f"Duplicate plugin name: {name}")

                plugins[name] = PluginInfo(name=name, path=path, actions=actions)
            except Exception as exc:  # noqa: BLE001
                errors[path.name] = str(exc)

        self._plugins = plugins
        self._load_errors = errors

    def list_plugins(self) -> list[dict[str, Any]]:
        result = [
            {
                "name": info.name,
                "path": str(info.path),
                "actions": info.actions,
            }
            for info in sorted(self._plugins.values(), key=lambda p: p.name)
        ]

        for file_name, error in sorted(self._load_errors.items()):
            result.append(
                {
                    "name": f"<load-error:{file_name}>",
                    "path": str(self._plugins_dir / file_name),
                    "actions": [],
                    "error": error,
                }
            )

        return result

    def run_action(self, plugin_name: str, action: str, params: dict[str, Any], timeout: float) -> Any:
        info = self._plugins.get(plugin_name)
        if info is None:
            raise PluginError(f"Plugin not found: {plugin_name}")

        if timeout <= 0:
            raise PluginError("Timeout must be > 0")

        ctx = mp.get_context("spawn")
        out_queue: mp.Queue = ctx.Queue()

        proc = ctx.Process(
            target=_plugin_worker,
            args=(str(info.path), action, params or {}, out_queue),
            daemon=True,
        )

        proc.start()
        proc.join(timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join()
            raise PluginTimeoutError(f"Plugin timeout after {timeout}s")

        try:
            payload = out_queue.get_nowait()
        except queue.Empty as exc:
            raise PluginExecutionError("Plugin process exited without returning data") from exc

        if payload.get("ok"):
            return payload.get("result")

        raise PluginExecutionError(payload.get("error", "Plugin execution failed"), payload.get("traceback"))
