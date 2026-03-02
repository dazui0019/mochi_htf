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
- 只读模式会隐藏 Item/Step 的新增、删除、上下移按钮。
- Item/Step 默认折叠；保存后保持当前折叠状态。
- 历史列表点击“测试用例名”可打开详情页，不再提供单独“打开”按钮。

### 目录
- `testcases/`：测试用例
- `plugins/`：插件
- `reports/`：报告
- `data/app.db`：历史记录

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

### 规格文档
- `硬件测试框架_规格v1.md`
- `使用说明.md`
