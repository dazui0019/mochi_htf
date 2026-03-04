---
name: mochi-htf-plugin-dev
description: Develop and update plugins for the mochi_htf project. Use when the user asks to create, modify, debug, or document plugins in plugins/, add plugin actions, wire config/self_check, return result.artifacts, add plugin testcases, or fix plugin-report compatibility.
---

# Mochi HTF Plugin Dev

## Goal

Implement plugin-related changes in `mochi_htf` with minimal breakage and predictable behavior across:
- plugin discovery and execution
- plugin config and self-check
- testcase authoring
- report rendering/export for plugin results

## Primary Workflow

1. Verify current workspace is the `mochi_htf` project:
- Confirm `plugins/`, `testcases/`, `mochi_htf/plugin_manager.py` exist.

2. Read project plugin guidance first:
- Open `插件开发文档.md` at repository root.
- Follow its conventions before changing code.

3. Load only relevant framework files based on task:
- Plugin loading/signature behavior: `mochi_htf/plugin_manager.py`
- Runtime param injection (`__htf_context`): `mochi_htf/executor.py`
- Report rendering for artifacts: `web/report.html`
- Excel export behavior: `mochi_htf/reporting.py`

4. Implement plugin changes:
- Create/update `plugins/<plugin_name>.py`.
- Prefer `class Plugin` + `create_plugin()`.
- Keep `actions()` aligned with real `run()` branches.

5. Add/adjust testcase when useful:
- Add or update `testcases/*.json` to demonstrate new action(s).

6. Validate before finishing:
- Run `python -m py_compile` for changed Python files.
- Run a minimal direct plugin invocation snippet when possible.

7. Update docs only if behavior/protocol changed:
- `README.md`
- `使用说明.md`
- `硬件测试框架_规格v1.md`

## Plugin Contract (Project-Specific)

- Required:
  - `run(action: str, params: dict) -> Any`
- Recommended:
  - `name`
  - `actions()`
  - `default_config()`
  - `config_schema()`
  - `set_config(config)`
  - `self_check(...)`

### Params rules

- Treat `params` as user business parameters.
- `params.__htf_context` is framework-reserved runtime context (auto-injected).
- Do not require users to provide `__htf_context` manually.
- Ignore unknown `__htf_*` keys.

### Result rules

- Prefer returning `result.artifacts: []` for displayable artifacts.
- Known types in this project UI:
  - `image`
  - `log`
  - `csv`
  - `waveform`
  - `metric`

### `metric` quick shape

```json
{
  "artifacts": [
    {"type": "metric", "name": "voltage", "value": 13.5, "unit": "V"}
  ]
}
```

Multi-channel metric:

```json
{
  "artifacts": [
    {
      "type": "metric",
      "items": [
        {"name": "CH1_voltage", "value": 13.5, "unit": "V"},
        {"name": "CH2_voltage", "value": 13.3, "unit": "V"}
      ]
    }
  ]
}
```

## Common Task Patterns

### Create a new plugin

- Add new file under `plugins/`.
- Implement at least `name`, `actions()`, `run()`.
- If device plugin: add `default_config/config_schema/set_config/self_check`.
- Add testcase under `testcases/`.

### Add action to existing plugin

- Update `actions()` and `run()` together.
- Add param validation with clear error messages.
- Add/update testcase step for new action.

### Add artifact output to plugin

- Return `artifacts[]` instead of custom ad-hoc top-level fields.
- If artifact is large, store file under `reports/<run_id>/artifacts/` and return `path/url`.

### Debug plugin execution failure

- Check action name mismatch between testcase and plugin `actions()`.
- Check `run()` exceptions and timeout behavior.
- Check config merges (`default_config` + saved config).
- Check JSON-serializability of returned result.

## Done Criteria

- Plugin loads successfully in `/api/plugins`.
- Target action appears and runs.
- Testcase (if added) is runnable.
- Report behavior matches returned artifact/result shape.
- Changed behavior is documented when needed.
