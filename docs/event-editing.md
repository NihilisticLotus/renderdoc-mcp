# 事件 Shader/CBuffer 编辑与共享撤销

本功能需要带 `ICaptureContext.EditEventShader/EditEventCBuffer/UndoEventEdit` 的 RenderTest B1 GUI，以及本版桥接。旧前端返回明确的不支持错误。B1 新增 6 个工具形成 66 项基线；2026-11-14 新增能力查询后共 67 项，前 66 项输入 schema 不变。

## 使用顺序

1. `list_live_windows` 获取目标窗口，后续显式传 `window_id`。
   先调用 `get_workflow_capabilities(window_id)` 核对实际前端、捕获身份和 `event_editing.capture_eligible`；`enabled=false` 是默认状态。查询不选择事件、不启用编辑。旧桥接返回方法不存在时，需更新目标前端桥接并重新加载，不能用网关工具数量推断前端支持。
2. 打开 RDC 后，调用 `get_event_edit_state(eid=..., stage="ps", show=True)`，取得 `session_id`、`revision`、Shader 身份、各 CBuffer 的 slot/space/offset/size。`show=True` 打开同一个 GUI 编辑器。
3. 默认关闭。调用 `set_event_editing_enabled(session_id=..., enabled=True)`，仅在当前进程启用，不写配置。
4. 修改 Shader：调用 `apply_event_shader_edit`，传当前 session/revision/eid/expected_shader，选择源码 `source` 或 `source_path`，保留捕获的编译 flags，必要时显式 `entry_point`。`captured_shader=True` 使用原字节码建立独立浮点输出，可配合仅 CBuffer 编辑。
5. 修改 CBuffer：调用 `apply_event_cbuffer_edit`，传上一步查询的完整绑定身份。`values` 在 `edit_offset` 处写 float32，未改字节保留；整数、NaN payload 或任意精确位模式使用完整窗口的 `data_path` 二进制文件。
6. 查看 GUI 独立 RGBA32_FLOAT 预览和原始浮点像素，`get_event_edit_state(x=..., y=...)` 同时返回该独立纹理的原始 RGBA 浮点值；非有限数用 `nan/inf/-inf` 字符串表示，不把它们改成0或夹到显示范围。显示范围不改变纹理数据。
7. `undo_event_edit(session_id, revision)` 或 GUI“撤销上次编辑”使用同一历史；MCP 可以撤销 GUI 编辑，GUI 也可以撤销 MCP 编辑。`clear_event_edit(kind="shader"/"cbuffer", ...)` 也是可撤销的事务。

每次变更后使用返回的新 revision；捕获关闭、切换或同路径重开后必须重新查询 session。GUI 未提交草稿在桥接变更后不会自动覆盖新状态，应用会报版本冲突。撤销会选择历史记录所属事件。

## 语义与错误边界

- 事件覆盖仅影响指定事件/阶段及 CBV 窗口，临时资源在 draw 后恢复。不是全局 Shader 替换，不是共享 Buffer 持续写入。
- 旧 `apply_shader_edit/revert_shader_edit` 仍为全局语义；新前端将其登记到 CaptureContext 的全局替换映射，禁止与有效事件覆盖重叠。桥接自身全局映射按捕获 session 清理。
- 原生编译/回放错误不会变成成功；编译器 diagnostics 原文保留。编译失败、绑定不匹配、过期 session/revision 不新增撤销记录。
- 仅支持当前原生 B1 能力：本地 D3D11/D3D12。远程/不支持的 API 明确报错，不静默退为全局替换。独立浮点颜色预览需要受支持的 PS draw。
- 撤销历史最多 64 条，达到上限明确要求先撤销；当前进程关闭捕获释放全部状态。不承诺 B3 项目持久化。
- 这次只提交源代码并验证隔离运行目录，没有安装桥接、更新正式运行目录或重启现有 MCP host。

## 验证入口

`python -m unittest discover -s tests -t . -v`；`python scripts/verify_mcp_tool_schema.py`。
GUI/桥接实际联测位于 Dev-RenderDoc 的 `util/diagnostics/event_overrides/gui_mcp.py`，使用新的 stdio 会话和隔离的 `--ui-event-edit-test` GUI，检查实际加载 DLL 路径、完整浮点纹理字节、共享撤销和错误清理。结果及哈希见主仓库 `docs/diagnostics/event-override-gui-mcp-20261113.md/json`，不把此处模拟后端单测当成实际 GPU 验收。


B2扩展：RT历史、临时分析恢复和共享Buffer持续范围编辑见[b2-history-shared-buffer.md](b2-history-shared-buffer.md)。
B1的事件影子、B2共享Buffer和全局Shader替换仍保持不同语义，撤销使用同一原生会话。
