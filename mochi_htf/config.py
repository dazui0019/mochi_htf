from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    testcases_dir: Path
    plugins_dir: Path
    reports_dir: Path
    data_dir: Path
    plugin_config_path: Path
    static_dir: Path
    db_path: Path
    history_limit: int = 1000
    default_step_timeout: float = 5.0


def load_config() -> AppConfig:
    root = Path(os.getenv("MOCHI_HTF_HOME", Path.cwd())).resolve()

    testcases_dir = root / "testcases"
    plugins_dir = root / "plugins"
    reports_dir = root / "reports"
    data_dir = root / "data"
    plugin_config_path = data_dir / "plugin_configs.json"
    static_dir = root / "web"
    db_path = data_dir / "app.db"

    for path in (testcases_dir, plugins_dir, reports_dir, data_dir, static_dir):
        path.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        project_root=root,
        testcases_dir=testcases_dir,
        plugins_dir=plugins_dir,
        reports_dir=reports_dir,
        data_dir=data_dir,
        plugin_config_path=plugin_config_path,
        static_dir=static_dir,
        db_path=db_path,
    )
