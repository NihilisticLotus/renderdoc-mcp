# Bread 工作流与 MCP 接入边界

2026-11-14 对照 Dev-RenderDoc 当前源码与“移植 Bread 事件级覆盖工作流”会话核对。
原生源码分析锚点为 Dev `5c8877b`；官方合并基线以主仓库 `UPSTREAM.md` 为唯一权威，本页不另立基线。
来源仍固定 Bread `1e58f1b852376f80713ee7b12b32e42d37250c46` 和 Metal `d6eba32f5316161094dbb1b573d2ba6a1513b819`。

## 已有与后续范围

| 阶段 | 当前接入情况 | MCP 对应工作 |
| --- | --- | --- |
| A / P1–P3 | PSO/SDK/MultiAction/CSV 与回放加速已有原生实现 | 沿用窗口与回放队列，不重复移植或添加检查点依赖 |
| B1 | 原生事件 Shader/CBuffer、独立 FP32 预览、GUI/MCP 共享撤销已接入 | 6 个事件工具；新增只读能力协商，导出固定 session/revision |
| B2 | RT 历史、临时分析恢复、共享 Buffer 持续修改仍待后续原生实现 | 现有 pixel history 不等于完整 RT 历史；事件 CB 覆盖不等于持续写 Buffer。必须在原生事务中保存/恢复选择与覆盖，并正确失效缓存 |
| B3 | Shader 工作区、别名、项目持久化、3D/UV 联动待实现 | 复用原生项目格式、捕获指纹和编辑身份；不得把当前导出 JSON 说成项目恢复 |
| B4 | 内嵌 AI、MCP Host、流程图、圈选提问、任务监视/恢复待实现 | 当前外部 stdio MCP 是被调用的服务，不是内嵌 MCP Host；需后续任务身份、取消和结果恢复协议 |
| B5 | Unity/UE 导出和可编辑效果重建/验证待实现 | 现有几何/贴图/DCC 交接是基础；引擎材质、骨骼、相机语义和效果需要独立证据与画面对比 |
| B6 | 新负载上的检查点评估待开展 | 在正确性、收益与显存证据成立后再接入，不能阻挡 B1–B5 |
| Metal | 通用修复审查与完整 Mac/GPU 能力线待开展 | Windows/D3D 测试不能代替 Metal 验收 |

这些后续目标保留完整范围；本轮完善的是当前 MCP 的接入与保护，不声明已经实现原生 B2–B6。

## 能力协商

先枚举窗口，再调用 `get_workflow_capabilities(window_id)`。这是新增的第 67 个工具，既有 66 项输入 schema 不变。

- `runtime`：实际 GUI 路径、运行时家族、嵌入 Python 与模块别名一致性。版本可能未知；不是构建哈希证明。
- `capture`：加载状态、路径、原生 session、API、本地文件标志和独立的远程回放连接标志。
- `event_editing`：完整前端方法是否存在、缺失方法、当前捕获是否符合本地 D3D11/12 的初步条件、开关、revision、活跃编辑和共享撤销数。
- `workflow_adapters`：本 MCP 已集成阶段与尚未集成阶段；不是上游仓库功能清单，也不凭版本号推断未来功能。

`capture_eligible` 只是前置筛选。远程 replay proxy、目标事件/阶段/CBV、GPU/驱动和资源状态仍由具体原生操作验证。查询不启用开关、不选择事件、不进行替换。
旧桥接没有此方法时明确返回 method-not-found；新版桥接连接旧 GUI 时列出缺失前端方法。升级须分别处理网关、选定前端桥接和 GUI 二进制。

## 统一身份与导出

`get_capture_status` 输出追加 `session_id/edit_revision/event_edits_active`，不改变输入。导出包固定前两者，逐次检查并在 manifest 记录保护等级。同路径重开、共享编辑版本变化或中途失去身份信息都拒绝继续。
旧 GUI/桥接可保留路径级导出，但 manifest 明示 `legacy_path_only`。没有原生原子快照，也不能检测未经过共享事务的修改；导出期间保持捕获与回放状态稳定。

事件编辑、全局替换、共享 Buffer 持续修改继续是三种不同语义。后续工具必须进入 CaptureContext 的同一状态所有者，维护 revision、失败回滚、缓存失效和资源退休；不能通过 MCP 自建替换/撤销栈冒充原生机制。

## 部署与验证

本轮修改源码与 editable 网关，不覆盖正式 GUI 或安装桥接。测试使用 Development GUI 加载源码桥接；用户现有窗口保持原状。需要升级时按 [运行时兼容说明](renderdoc-compatibility.md) 安装到所选前端，并重新加载该桥接、重连 MCP。

单测覆盖旧前端、限定 API/远程条件、显式窗口路由、同路径重开与编辑变更阻断。schema 必须先比较旧 66 项不变，再更新新增项快照。

本轮实际结果：107 项单测通过；fresh stdio schema 为 67 项，SHA256 `8f15ea80a9f956bab7256945bdaefde6740f5e872d2f19494feb85110028cc8e`。Windows x64 Development GUI 加载本版源码桥接，自有 D3D11/D3D12 三 draw 夹具各通过 205 项检查，包含新能力查询、capture status 身份一致性，以及既有 GUI/MCP 事件编辑、完整 FP32 输出和撤销恢复。实际 EXE/DLL 路径及哈希由每次运行的 `result.json` 记录。

本轮未重新构建 C++、未运行 x86、未重跑真实游戏捕获、未验收远程连接或设备丢失；不把已有 2026-11-13 全矩阵当作本轮测试。正式安装未更新。首次能力判断因 SWIG 枚举带 `GraphicsAPI.` 前缀误报，已修正并回归；最初验收驱动的启动发现竞态也已修正，失败批次不计入通过数。
