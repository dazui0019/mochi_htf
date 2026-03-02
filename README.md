## Mochi HTF

Mochi HTF 是一个面向工控机单机场景的硬件测试框架 MVP。

### 功能
- Web UI（局域网访问）
- JSON 用例加载/编辑/保存
- 用例创建/删除
- 插件式设备扩展
- Action/Verify 工步执行（插件与动作均为下拉选择）
- Pass/Fail/Error/Stopped 运行状态
- 历史记录（SQLite，默认 1000 条）
- 历史详情页查看（Item/Step 折叠）
- JSON/Excel 报告导出（在历史详情页执行）

### 关键交互
- 用例加载后默认只读。
- 新建用例后自动加载，并默认进入编辑模式。
- 保存用例后自动退出编辑模式（回到只读）。
- 仅在只读模式允许开始测试。
- 点击“开始测试”后会先清空当前用例卡片上的上一轮 Item/Step 结果状态。
- 只读模式会隐藏 Item/Step 的新增、删除、上下移按钮。
- Item/Step 默认折叠；保存后保持当前折叠状态。
- 历史列表点击“测试用例名”可打开详情页，不再提供单独“打开”按钮。

### 目录
- `testcases/`：测试用例
- `plugins/`：插件
- `reports/`：报告
- `data/app.db`：历史记录
- `data/plugin_configs.json`：插件配置（串口号等）

### 启动
```bash
uv run python main.py
```

默认访问：`http://127.0.0.1:18765`  
局域网访问：`http://<工控机IP>:18765`

### 历史详情
- 在主页“执行与历史”中点击历史记录里的测试用例名称可打开详情页。
- 详情页地址示例：`/web/report.html?run_id=<run_id>`

### 示例
- 示例用例：`testcases/case_power_on_001.json`
- 示例插件：`plugins/sim_device.py`
- 电源控制示例：`testcases/case_power_ctrl_001.json` + `plugins/power_ctrl.py`
- 示波器截图示例：`testcases/case_scope_capture_001.json` + `plugins/oscilloscope.py`
- 波形附件示例：`testcases/case_waveform_demo_001.json` + `plugins/waveform_demo.py`

### 插件配置与自检
- UI 的“插件”面板按插件卡片展示，支持折叠/展开。
- 每个插件配置默认只读；点击“编辑配置”后可修改 JSON，保存后会自动重新加载该插件配置。
- 支持“自检”（单插件）和“全部自检”（批量）两种方式。
- 每个插件卡片右侧显示自检状态：`未自检` / `通过` / `失败` / `异常` / `不支持`。
- 插件卡片不显示自检返回详情，仅显示自检状态。
- 运行工步时会自动把该插件的已保存配置注入插件实例。
- 插件可选实现以下方法：
  - `default_config() -> dict`：默认配置
  - `config_schema() -> dict`：配置说明（用于 UI 展示）
  - `set_config(config: dict)`：在执行前接收合并后的配置
  - `self_check(...)`：插件自检，返回 `bool` 或 `{"ok": bool, ...}`

### 运行时上下文（`params.__htf_context`）
- 框架执行每个 Step 时，会向插件 `run(action, params)` 传入运行时上下文：`params.__htf_context`。
- 该字段为框架保留字段，测试用例中无需手工填写。
- 当前包含字段：
  - `run_id`
  - `case_id`
  - `item_id`
  - `step_id`
  - `step_name`
  - `reports_dir`
- 建议插件忽略未知字段，并避免使用 `__htf_` 前缀作为业务参数名。

### 示波器截图归档
- 新增 `oscilloscope` 插件动作：`capture_screenshot`。
- 执行时会把截图保存到：`reports/<run_id>/artifacts/`，并在步骤 `result.artifacts`（数组）中记录附件元数据。
- 历史详情页会按附件 `type` 渲染：`image` / `log` / `csv` / `waveform`。
- `waveform` 类型可提供 `series` 数组（例如电压/电流通道与采样点），详情页会显示通道和采样点数量。
- 默认 `capture_mode=placeholder`（用于打通流程）；实际接入请改为 `capture_mode=cli` 并配置 `cli_command`。
- `cli_command` 支持占位符：`{output}`、`{address}`、`{run_id}`、`{step_id}`、`{label}`。

### 规格文档
- `硬件测试框架_规格v1.md`
- `使用说明.md`
