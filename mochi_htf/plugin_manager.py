from __future__ import annotations

import copy
import importlib.util
import inspect
import json
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
    config_schema: dict[str, Any]
    default_config: dict[str, Any]
    supports_self_check: bool


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


def _ensure_mapping(value: Any, method_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PluginError(f"{method_name}() must return a dict")
    return dict(value)


def _apply_plugin_config(plugin: Any, plugin_config: dict[str, Any]) -> None:
    setter = getattr(plugin, "set_config", None)
    if callable(setter):
        setter(copy.deepcopy(plugin_config))


def _invoke_plugin_run(
    plugin: Any,
    action: str,
    params: dict[str, Any],
    plugin_config: dict[str, Any],
) -> Any:
    run_callable = plugin.run
    signature = inspect.signature(run_callable)
    parameters = list(signature.parameters.values())
    names = [p.name for p in parameters]
    positional_slots = sum(
        1
        for p in parameters
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    accepts_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in parameters)
    accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters)

    if "plugin_config" in names:
        return run_callable(action, params, plugin_config=plugin_config)

    if "config" in names:
        return run_callable(action, params, config=plugin_config)

    if accepts_varargs or positional_slots >= 3:
        return run_callable(action, params, plugin_config)

    if accepts_kwargs:
        return run_callable(action, params, plugin_config=plugin_config)

    return run_callable(action, params)


def _normalize_self_check_result(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"ok": value}
    if isinstance(value, dict):
        payload = dict(value)
        if "ok" not in payload:
            payload["ok"] = True
        payload["ok"] = bool(payload["ok"])
        return payload
    return {"ok": True, "result": value}


def _invoke_plugin_self_check(plugin: Any, plugin_config: dict[str, Any]) -> dict[str, Any]:
    self_check = getattr(plugin, "self_check", None)
    if not callable(self_check):
        raise PluginError("Plugin does not implement self_check()")

    signature = inspect.signature(self_check)
    parameters = list(signature.parameters.values())
    names = [p.name for p in parameters]
    positional_slots = sum(
        1
        for p in parameters
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    accepts_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in parameters)
    accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters)

    if "plugin_config" in names:
        return _normalize_self_check_result(self_check(plugin_config=plugin_config))

    if "config" in names:
        return _normalize_self_check_result(self_check(config=plugin_config))

    if accepts_varargs or positional_slots >= 1:
        return _normalize_self_check_result(self_check(plugin_config))

    if accepts_kwargs:
        return _normalize_self_check_result(self_check(plugin_config=plugin_config))

    return _normalize_self_check_result(self_check())


def _plugin_worker(
    module_path: str,
    action: str,
    params: dict[str, Any],
    plugin_config: dict[str, Any],
    out_queue: mp.Queue,
) -> None:
    try:
        module = _load_module_from_path(Path(module_path))
        plugin = _build_plugin_instance(module)
        _apply_plugin_config(plugin, plugin_config)
        result = _invoke_plugin_run(plugin, action, params, plugin_config)
        out_queue.put({"ok": True, "result": result})
    except Exception as exc:  # noqa: BLE001
        out_queue.put(
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


def _plugin_self_check_worker(module_path: str, plugin_config: dict[str, Any], out_queue: mp.Queue) -> None:
    try:
        module = _load_module_from_path(Path(module_path))
        plugin = _build_plugin_instance(module)
        _apply_plugin_config(plugin, plugin_config)
        result = _invoke_plugin_self_check(plugin, plugin_config)
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
    def __init__(self, plugins_dir: Path, plugin_config_path: Path | None = None) -> None:
        self._plugins_dir = plugins_dir
        self._config_path = plugin_config_path or (plugins_dir.parent / "data" / "plugin_configs.json")
        self._plugins: dict[str, PluginInfo] = {}
        self._load_errors: dict[str, str] = {}
        self._plugin_configs: dict[str, dict[str, Any]] = self._load_plugin_configs()

    def _load_plugin_configs(self) -> dict[str, dict[str, Any]]:
        if not self._config_path.exists():
            return {}
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}

        cleaned: dict[str, dict[str, Any]] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, dict):
                cleaned[key] = dict(value)
        return cleaned

    def _save_plugin_configs(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(self._plugin_configs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _merge_configs(
        default_config: dict[str, Any],
        saved_config: dict[str, Any],
        override_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged = copy.deepcopy(default_config)
        merged.update(copy.deepcopy(saved_config))
        if override_config:
            merged.update(copy.deepcopy(override_config))
        return merged

    def _require_plugin_info(self, plugin_name: str) -> PluginInfo:
        info = self._plugins.get(plugin_name)
        if info is None:
            raise PluginError(f"Plugin not found: {plugin_name}")
        return info

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
                raw_actions = actions_callable() if callable(actions_callable) else []
                if raw_actions is None:
                    raw_actions = []
                if not isinstance(raw_actions, list):
                    raise PluginError("actions() must return a list")
                actions = [str(action) for action in raw_actions if str(action)]

                config_schema_callable = getattr(plugin, "config_schema", None)
                raw_config_schema = config_schema_callable() if callable(config_schema_callable) else {}
                config_schema = _ensure_mapping(raw_config_schema, "config_schema")

                default_config_callable = getattr(plugin, "default_config", None)
                raw_default_config = default_config_callable() if callable(default_config_callable) else {}
                default_config = _ensure_mapping(raw_default_config, "default_config")

                supports_self_check = callable(getattr(plugin, "self_check", None))

                if name in plugins:
                    raise PluginError(f"Duplicate plugin name: {name}")

                plugins[name] = PluginInfo(
                    name=name,
                    path=path,
                    actions=actions,
                    config_schema=config_schema,
                    default_config=default_config,
                    supports_self_check=supports_self_check,
                )
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
                "config_schema": copy.deepcopy(info.config_schema),
                "default_config": copy.deepcopy(info.default_config),
                "config": self.get_plugin_config(info.name),
                "supports_self_check": info.supports_self_check,
            }
            for info in sorted(self._plugins.values(), key=lambda p: p.name)
        ]

        for file_name, error in sorted(self._load_errors.items()):
            result.append(
                {
                    "name": f"<load-error:{file_name}>",
                    "path": str(self._plugins_dir / file_name),
                    "actions": [],
                    "config_schema": {},
                    "default_config": {},
                    "config": {},
                    "supports_self_check": False,
                    "error": error,
                }
            )

        return result

    def get_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        info = self._require_plugin_info(plugin_name)
        saved_config = self._plugin_configs.get(plugin_name, {})
        return self._merge_configs(info.default_config, saved_config)

    def set_plugin_config(self, plugin_name: str, plugin_config: dict[str, Any]) -> dict[str, Any]:
        info = self._require_plugin_info(plugin_name)

        if not isinstance(plugin_config, dict):
            raise PluginError("Plugin config must be a JSON object")

        try:
            json.dumps(plugin_config, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            raise PluginError(f"Plugin config is not JSON serializable: {exc}") from exc

        self._plugin_configs[plugin_name] = dict(plugin_config)
        self._save_plugin_configs()
        return self._merge_configs(info.default_config, self._plugin_configs[plugin_name])

    def get_plugin_details(self, plugin_name: str) -> dict[str, Any]:
        info = self._require_plugin_info(plugin_name)
        return {
            "name": info.name,
            "path": str(info.path),
            "actions": copy.deepcopy(info.actions),
            "config_schema": copy.deepcopy(info.config_schema),
            "default_config": copy.deepcopy(info.default_config),
            "config": self.get_plugin_config(plugin_name),
            "supports_self_check": info.supports_self_check,
        }

    def run_action(self, plugin_name: str, action: str, params: dict[str, Any], timeout: float) -> Any:
        info = self._require_plugin_info(plugin_name)

        if timeout <= 0:
            raise PluginError("Timeout must be > 0")

        plugin_config = self.get_plugin_config(plugin_name)

        ctx = mp.get_context("spawn")
        out_queue: mp.Queue = ctx.Queue()

        proc = ctx.Process(
            target=_plugin_worker,
            args=(str(info.path), action, params or {}, plugin_config, out_queue),
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

    def self_check(
        self,
        plugin_name: str,
        timeout: float = 5.0,
        override_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        info = self._require_plugin_info(plugin_name)

        if not info.supports_self_check:
            raise PluginError(f"Plugin does not support self-check: {plugin_name}")

        if timeout <= 0:
            raise PluginError("Timeout must be > 0")

        if override_config is not None and not isinstance(override_config, dict):
            raise PluginError("Self-check override config must be a JSON object")

        plugin_config = self._merge_configs(
            info.default_config,
            self._plugin_configs.get(plugin_name, {}),
            override_config,
        )

        ctx = mp.get_context("spawn")
        out_queue: mp.Queue = ctx.Queue()

        proc = ctx.Process(
            target=_plugin_self_check_worker,
            args=(str(info.path), plugin_config, out_queue),
            daemon=True,
        )

        proc.start()
        proc.join(timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join()
            raise PluginTimeoutError(f"Self-check timeout after {timeout}s")

        try:
            payload = out_queue.get_nowait()
        except queue.Empty as exc:
            raise PluginExecutionError("Plugin self-check process exited without returning data") from exc

        if payload.get("ok"):
            result = payload.get("result")
            if isinstance(result, dict):
                return result
            return {"ok": True, "result": result}

        raise PluginExecutionError(payload.get("error", "Plugin self-check failed"), payload.get("traceback"))
