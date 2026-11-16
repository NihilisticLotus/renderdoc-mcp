# RenderDoc / RenderTest MCP 兼容性

## 适用变更

主源码提交 `210fc381165b93e559f6e1d7a2f101bb871345b7` 将 Windows Development
运行时从 RenderDoc 品牌名配对为 RenderTest；后续提交 `595f643f1f6bcde2228ed8d651e882177e2ae003`
补齐普通 GUI 启动兼容并加入完整场景截帧验证。完整运行时改名基于 `4b870f6..210fc38`
（219 个文件）；主源码记录为 `docs/diagnostics/l6-identity-20261105.md`、
`docs/diagnostics/l6-retained-identities.json` 和
`docs/diagnostics/rider-debugging-20261105.md`。
随后 GUI 工作区增加了 `CaptureSettings.compatibilityProfile="wuthering-d3d11"`：
自动识别 Wuthering Waves 根程序和 Shipping 程序，仅在本机 Windows GUI Launch
补充 `RENDERTEST_D3D11_ENTRY_HOOKS=1`、子进程捕获和 `-dx11 -krqlv=uhd`。手动环境项优先，
重复参数去重，冲突 API 参数会报错；Inject、remote、standard 不自动套用该 profile。
直接底层 `ExecuteAndInject` 不经过 GUI 解析器，调用方需自行传递等价配置。MCP 只消费已经
产生的捕获，不发起上述 Launch/Inject 流程。GUI 自动 Launch 的本机证据在
`E:/RenderDocProject/renderdoc/docs/diagnostics/wuthering-gui-20261105.md`。

## 影响与兼容措施

| 范围 | 影响 | MCP 兼容措施 | 本轮结论 |
| --- | --- | --- | --- |
| GUI / CLI / DLL 文件名 | 新输出为 `qrendertest.exe`、`rendertestcmd.exe`、`rendertest.dll`；旧名称仍可能与它们并存在同一构建目录 | `RENDERTEST_PATH` 显式选择新运行时；`RENDERDOC_PATH` 继续选旧文件布局，并在新布局独占时也可识别新名称。新路径缺少 CLI 时直接报错，不回退到旧目录 | 已完成并由双布局发现测试覆盖 |
| Python / SWIG replay 模块 | 新模块名 `rendertest`，旧 `renderdoc` 应指向同一 SWIG 模块实例；`qrenderdoc` 保持原名 | 扩展优先导入 `rendertest`，把 `renderdoc` 注册为同一对象；检测到两对象冲突时拒绝启动。RenderDoc 与 RenderDuck 旧路径仍保留 | 已完成并有同实例/冲突测试；新 GUI 实机结果见下文验收记录 |
| 扩展安装与加载 | Qt `AppDataLocation` 随 GUI 可执行程序名分开；新 GUI 使用 `qrendertest` 目录，旧 GUI 使用 `qrenderdoc` | `install_ext.py --frontend rendertest` 写入 `%APPDATA%/qrendertest`，默认前端仍写旧目录，RenderDuck 独立路径不变 | 已完成并用隔离 APPDATA 检查 |
| Qt/Python ABI | MCP 网关外部 Python 与 RenderTest GUI 内嵌 Python 不要求相同版本；SWIG `.pyd` 不应从 MCP 的 Python 进程导入 | Bridge 代码在 GUI 内嵌解释器运行，回报实际 Python 版本、主程序路径、runtime family 与模块身份；不在外部 MCP 进程导入 `.pyd` | 已完成静态兼容检查和新 GUI 实测；非 Windows GUI ABI 未在本机测试 |
| C API 与 replay marker | 新增真实 `RENDERTEST_GetAPI`，保留 `RENDERDOC_GetAPI`；两个 marker 都识别 | Bridge 扩展使用 GUI 内嵌 Python/qrenderdoc API，不直接按 DLL 导出名绑定；离线 CLI 按明确路径选择家族 | 旧/新 Python 导入实测；MCP 未直接测试两个 C 导出地址，主源码测试覆盖 |
| 捕获、配置与日志目录 | 捕获/日志临时目录从 `%TEMP%/RenderDoc` 改为 `%TEMP%/RenderTest`；核心配置从 `%APPDATA%/renderdoc` 改为 `%APPDATA%/rendertest`；GUI 配置由各自 `AppDataLocation` 决定 | MCP 捕获工具使用显式 `.rdc` 路径；它不扫描 RenderDoc 日志或写核心配置。安装器只改所选 GUI 的 `UI.config`。bridge IPC 仍在 `%TEMP%/renderdoc_mcp_bridge` | 路径消费者已核对；日志解析不是 MCP 当前能力 |
| Native API hooks / 调试日志 | Native D3D11/DXGI hook 是可选项；Development 日志默认保留 | MCP 不打开 Native hook 开关、不以缺少预期探测错误作为成功；连接以桥接 `ping`、runtime metadata 和工具返回状态为准 | 未因 MCP 开启实验 hook；诊断窗口/连接使用实际状态 |
| GUI 启动兼容策略 | GUI 新增 `wuthering-d3d11` profile：由根 `Wuthering Waves.exe` 与 `Client/Binaries/Win64/Client-Win64-Shipping.exe` 识别，补充子进程捕获、`-dx11 -krqlv=uhd` 与 `RENDERTEST_D3D11_ENTRY_HOOKS=1`；手动环境项优先，remote/standard/Inject 不自动应用 | MCP 只连接已运行的 GUI、读取/回放 `.rdc`，工具面没有启动或注入游戏的 API；不覆盖该策略，也不把 Replay/OpenCapture 结果说成 GUI Launch 策略验证 | 与主仓库策略边界一致；实际自动 Launch 证据来自本机 GUI 回归记录，MCP 只验收其生成的 frame4834 捕获 |
| MCP 工具名与输入 schema | 新旧名称变更不要求改 MCP 方法名/参数 | 保留现有 bridge 方法和 60 个工具输入 schema；窗口列表增加 runtime metadata，供新旧实例甄别 | `tools/list` 输入 schema 哈希及数量在实机验证记录中 |
| 打包/安装器/非 Windows | 主源码同时调整打包和非 Windows 路径，但本机真实 GUI 为 Windows | 当前适配只更新 Windows MCP 安装/发现流程，不宣称其它平台包兼容 | Linux/macOS、MSI 与 Android 未由 MCP 本机验收 |

## 配置 RenderTest

外部 MCP 网关可以同时保留旧 RenderDoc 与新 RenderTest 根目录：

```toml
[mcp_servers.renderdoc.env]
RENDERDOC_PATH = "C:/RenderDocCustom.backup-20261105-133303"
RENDERTEST_PATH = "C:/RenderDocCustom"
```

`RENDERTEST_PATH` 只影响离线 CLI/缩略图发现；实时连接仍由已加载的 GUI 扩展提供。
如果它被显式指定但 `rendertestcmd.exe` 不存在，发现操作会失败并指出缺失路径，
不会用旧 `RENDERDOC_PATH` 宣称通过。验证新 GUI 时安装到独立目录：

```powershell
& .\venv\Scripts\python.exe scripts\install_ext.py --frontend rendertest --incremental --skip-decompiler
```

安装后启动 `qrendertest.exe` 并重连 MCP。已有 RenderDoc 窗口和捕获不需要关闭。
确认 `list_live_windows` 的 `runtime.runtime_family` 为 `rendertest`，并核对
`runtime.frontend_executable` 与 `rendertest.dll` 的实际路径及 SHA256。

## 必须记录的回归证据

1. 新旧路径发现测试、模块别名对象相等测试及 MCP 现有单元测试通过。
2. 新 MCP stdio 会话完成 initialize、tools/list 和 schema 对比；记录工具数、名称、
   输入 schema 的规范化哈希。适配修改不应单方面删除旧工具或改变必填参数。
3. 新 `qrendertest.exe` 窗口的主程序路径和 `rendertest.dll` 路径、SHA256 与目标构建一致；
旧 `qrenderdoc.exe` 或备份目录中的 `renderdoc.dll` 测试不能替代这一项。
4. 通过该窗口打开已有 `.rdc`，检查事件/资源/纹理/管线/shader 读取，并完成至少一种
   调试或导出操作。记录捕获路径/API、错误与大文件加载/重连情况。
5. 检查重连/失败路径；显式新路径不完整时，不能静默切到旧运行时。保留活跃用户窗口。
6. 未运行的 API、后端、平台和包格式明确列为限制，不宣称全部兼容。

工具 schema 的审阅快照存放在 `tests/fixtures/mcp_tool_schema.json`。运行
`python scripts/verify_mcp_tool_schema.py` 会启动新的 stdio MCP 会话并比较真实
`tools/list` 输入 schema；有意变更前先审阅 diff 和兼容行为，再显式更新快照。

## 本机验收

本次先在 RenderTest `x64/Development` 上执行了 live smoke test，之后又按最新部署切换到
`C:/RenderDocCustom`。只记录实际连接窗口的路径和加载文件哈希；静态读码或旧版 MCP 工具响应
不作为实机通过证据。

### 2026-11-05 Development 版 live smoke test（早于正式部署）

- 新 MCP stdio 握手成功；FastMCP 4.1.0，协议 `2025-11-25`，实际 `tools/list` 为 60 个工具。
  当前适配只改 bridge runtime 元数据、路径发现和前端扩展安装，没有改工具声明/输入定义；
  完整输入 schema 用 `verify_mcp_tool_schema.py` 固化并校验，哈希为
  `423c6cfebec31283cccbde6a47e461e7a6258ed50effa9ed65343100c386c391`。
- Live bridge 观察到窗口 `42452-9570fd95`，PID 42452，family `rendertest`、runtime 1.48、
  executable `E:/RenderDocProject/renderdoc/x64/Development/qrendertest.exe`、内嵌 Python 3.6.4、
  replay module `rendertest`、legacy alias 同对象。`Get-Process.Modules` 指向同目录
  `rendertest.dll`，SHA256 `E6CE52E81EB3777185E7691C60435A0DBEB6A75BCAF4982F2AE5F0A52603E9BC`；
  不把共存的旧 `renderdoc.dll` 当作证据。磁盘上 `rendertestcmd.exe` SHA256 为
  `2EDE5A54EF864E58AB76D96374DCAB343F3CA02DAF11ECB49A7244210AE5545A`。
- 经 live MCP `open_capture` 打开
  `E:/RenderDocProject/captures/Wuthering_GUI_auto_20261105_frame4834.rdc`：1,176,339,128 bytes，
  D3D11。`list_passes`、`find_events` 与 `get_frame_packet` 都返回真实 capture 数据；前 25 个
  pass markers 包含 Compute/Colour/Depth-only 等类型，draw 搜索返回 `DrawIndexed` 事件。
  该操作只证明可打开和枚举，不单独算作完整场景通过。
- GUI 进程在后续 live 调试调用前退出；本线程没有重启或关闭 GUI/游戏。为完成安全的 MCP 导出
  检查，在隔离工作目录内用 fresh MCP stdio `open_capture` 走离线 fallback；它选择了
  `RENDERTEST_PATH` 下的 `rendertestcmd.exe` 并导出嵌入缩略图。截图视觉包含人物、三维环境、
  小地图、任务、队伍、生命值和技能 HUD。导出文件为
  `E:/RenderDocProject/work/mcp-compat-20261105/.state/thumbs/cap_437ca5d8dfb5.jpg`；
  截图与主仓库记录的场景视觉检查一致。主仓库已确认此帧 SHA256 为
  `4E12D130B9F9913E3C3F222E93EBE739922D6074BAA8F201E09979CF27214B0C`；MCP 本轮不使用登录帧
  `frame2883` 作为场景通过证据。
- 尚未完成 GUI 恢复后的 pipeline/shader inspection、纹理资源导出和 pixel-debug 操作；
  live bridge 后续不可用且本任务要求保留 GUI 会话。离线缩略图视觉检查不能替代这些 live 工具。
- `RENDERTEST_PATH` 已加入 Codex MCP 环境，同时保留旧 `RENDERDOC_PATH`。已运行的 MCP host
  进程没有被重启；后续连接需要刷新 host 才会读取新环境，现存服务和窗口保持不动。

### 595f643 正式部署后的 MCP 路径刷新

- 主仓库已将 `595f643f1f6bcde2228ed8d651e882177e2ae003` 完整部署到
  `C:/RenderDocCustom`，保留的旧安装位于 `C:/RenderDocCustom.backup-20261105-133303`。
  新目录包含 x64/x86 的 `qrendertest.exe`、`rendertest.dll`、`rendertestcmd.exe` 及两种
  Python module 名称所需文件；主仓库部署清单与回放证据在
  `E:/RenderDocProject/work/deploy-custom-20261105/`。
- Codex MCP 环境已刷新为 `RENDERTEST_PATH=C:/RenderDocCustom` 和
  `RENDERDOC_PATH=C:/RenderDocCustom.backup-20261105-133303`。路径发现选新 family；旧变量继续
  指向保留的旧 RenderDoc 安装，避免把旧 fallback 丢掉。配置 TOML 重新解析成功，备份保存在
  `C:/Users/Huangcaiyi/.local/share/renderdoc-mcp/backups/codex-config-before-595f-deploy-20261105.toml`。
- 新部署 x64 文件哈希：`qrendertest.exe`
  `D3FAAAC375B706988A0A4B6828FD4CE4C9F101A9CF4AE9F137F917F0450537C8`；`rendertest.dll`
  `0CE31D46E1B99BF4E1143DD8762EF91C71470042F9AEF882669A078AF236DF2D`；`rendertestcmd.exe`
  `22BEBEFB90EE6DDEE4DBBA37E8FF675C9ED79BD4229CC4F7FE6331C43982AA84`。主仓库另行确认正式目录
  DLL 的直接加载与 frame4834 回放；MCP 进程没有加载新的 GUI DLL，因为当时没有活动 GUI。
- 正式目录的主仓库回放证据 `installed-replay-frame4834.json` 为 `PASS`：runtime 是
  `C:/RenderDocCustom/rendertest.dll`、driver D3D11、1093 actions、366 textures、final event
  11083；对应 PNG 在 `E:/RenderDocProject/work/deploy-custom-20261105/`。这是主仓库直接
  加载与回放证据，不冒充 MCP GUI bridge 的 pipeline/shader 查询。其安装命令 `version` 输出
  `rendertestcmd x64 v1.48 built from 595f643f1f6bcde2228ed8d651e882177e2ae003`。
- 配置刷新后的 fresh MCP stdio 会话仍是 60 个工具，schema SHA256
  `423c6cfebec31283cccbde6a47e461e7a6258ed50effa9ed65343100c386c391`。通过此会话的离线
  `open_capture` 明确从新 `RENDERTEST_PATH` 使用 `rendertestcmd.exe`，处理 1.17 GB 的
  frame4834 并导出嵌入缩略图；`get_capture_status` 回报同一路径与大小。该离线接口的 API 字段
  为 `null`，故 API 已知性来自之前 live 窗口的 D3D11 返回值和主仓库回放检查，而不是缩略图工具。
  MCP 导出文件 `.state/thumbs/cap_437ca5d8dfb5.jpg` 为 396,170 bytes，SHA256
  `8917C438CBBFD5FFE5E76A6ADC75A5D5C4DD3F714FF4D4C34CC3A629AAB429C1`；隔离 MCP 工作目录是
  `E:/RenderDocProject/work/mcp-compat-595f-20261105/`。
- 更新后的 bridge 已安装到 `%APPDATA%/qrendertest/extensions/renderdoc_mcp_bridge`，与正式 GUI
  相同 basename 的 AppData namespace 对应；安装文件与源代码哈希一致。`register` 日志也按
  runtime family 输出 `RenderTest`，避免新 GUI 被旧日志标成 RenderDoc。正式目录的 live bridge
  尚未由本线程启动验证。
- 当前 MCP host 会在下次连接时读取更新后的环境；现有服务没有重启。最新部署根目录的 GUI
  bridge 尚未在本轮 MCP 会话中实时连接，因此 pipeline/shader/texture live 导出和 pixel-debug
  仍需 GUI 后续可用时补验。用户主线程已有同一正式部署的 frame4834 直接加载、回放与画面导出证据。


## 2026-11-13 B1 GUI/MCP 统一事件编辑（未部署）

| 生产者/消费者 | 契约与本地检查 |
| --- | --- |
| GUI/DLL/helper | 主仓库Development x64/x86保持rendertest身份；测试进程逐一核对实际加载DLL路径与SHA256，未覆盖正式目录 |
| Python | 新增9个CaptureContext UI-thread invoker，双架构GUI绑定一致性通过；桥接仍使用renderdoc别名，同一模块/type registry |
| Capture identity/replay | GetCaptureSessionID + EventEditRevision；新6工具调用原CaptureContext与Replay队列，不另建事件撤销栈 |
| Existing global Shader tools | 原输入schema不变；新前端登记原全局替换映射，与有效事件层互斥，捕获重开清理桥接映射 |
| New preview result | get_event_edit_state的x/y查询实际RGBA32_FLOAT原始像素，越界明确报错；回放回调异常在BlockInvoke返回后显式传播 |
| Extension/config/discovery | 包名、AppData namespace、bridge IPC与window_id发现不变；验收从source/bridge_extension加载，不替换安装桥接 |
| Old frontend/remote | 缺少新CaptureContext API明确不支持；原生不支持的远程编辑/API由原接口拒绝。未新做Mac/Linux或远程GUI验收 |

fresh tools/list：原60项schema逐项不变，新增6项，共66项；最终schema SHA256 `db65100de5a83462087b27a99f18ce3d9830d973e4a184aec5ffd800dafdff94`。
102项本地MCP回归通过。实际live证据包括新的stdio session、目标窗口ID、构建GUI与loaded DLL路径、双API/双架构编辑、GUI/MCP交叉撤销、指定像素读取及越界错误；主仓库 `docs/diagnostics/event-override-gui-mcp-20261113.md/json`保存完整进程和文件哈希。不是旧GUI或上游测试结果。

用户本轮要求暂不部署：未安装新bridge、未更新C:/RenderDocCustom、未重启既有host；新功能在源码及隔离构建验收中可用。用法见[event-editing.md](event-editing.md)。


## 2026-11-14 B2 历史与共享 Buffer（未部署）

| 生产者/消费者 | 兼容结论 |
| --- | --- |
| GUI/DLL/CLI/helper | Development x64/x86原身份与双架构配对不变，隔离宿主逐一核对实际加载DLL路径/SHA256；不改正式目录 |
| Python/SWIG | 3个controller方法、2个CaptureContext方法与结构反射/数组同步；两架构GUI绑定一致性通过，renderdoc/rendertest同一type registry；长事务释放GIL |
| MCP输入与结果 | 原67工具schema逐项不变，新增5个B2工具共72；snapshot原始字节/hash与RGB8显示分开；新heartbeat_status为可选实例元数据 |
| 会话/队列/撤销 | 复用B1 window_id、capture UUID、revision和CaptureContext单一undo；原生回放串行，跨入口撤销/捕获重开/全局替换互斥均实测 |
| IPC/扩展/配置/launcher | 原文件命名、temp/AppData namespace和launcher保持不变；独立纯文件心跳线程与GIL释放防止长回放假离线，不放宽客户端存活阈值或重试写请求 |
| 旧前端/远程/API | 缺能力明确错误，本地仅D3D11/12；远程proxy及未支持资源依赖拒绝，没有旧安装fallback |

113项本地回归通过，fresh tools/list及真实GUI/MCP证据见[B2用法与边界](b2-history-shared-buffer.md)。
主仓库13个独立回放进程验证双架构/双API/双语浅深、历史/共享/统一撤销和真实RDC；
原生接口未在Mac/Linux、新远程会话或设备故障注入条件下验收。本轮不部署、不安装bridge、不重启已有host。


## 2026-11-16 B3.1 原生 Shader 工作区（未部署）

| 生产者/消费者 | 兼容结论 |
| --- | --- |
| GUI/DLL/CLI/helper | 原名字、配置与双架构核心/helper配对不变；新界面只在窗口/ShaderViewer/事件编辑器显式打开 |
| Python/SWIG | 两项 CaptureContext 接口、UI invoker及长事务GIL释放同步；两架构绑定一致性通过，旧/新模块别名仍共用type registry |
| MCP schema | 新增 shader_workspace；旧72项完全不变，共73项；5项专用契约回归，118项全量回归通过 |
| 状态与队列 | 文档、编译候选、原始/成功源码快照均由CaptureContext持有；bridge不另存状态。应用调用B1事件事务和统一撤销 |
| IPC/配置/launcher | 沿用原bridge实例、capture UUID、文件协议、配置路径和launcher；不安装bridge，不修改旧窗口 |
| 错误与不支持 | 旧前端缺接口明确拒绝；原生限制D3D11/D3D12；编译、ABI、外部冲突和陈旧revision错误保留，不自动退到全局替换 |

实际fresh stdio对接构建目录中的新GUI：双架构双API四组合、中英浅深/缩放，以及
StarRail双架构和Control x64的双基线/事件编辑/FP32/A-B-A。机器证据位于主仓库
`docs/diagnostics/fork-sync-b3-stage1-20261116.json`，包含PID、GUI/实际DLL路径和SHA256。
运行时仍Qt5.9.4/Python3.6.4。真实外部反编译器、非PS阶段、远程和设备故障注入未在本批验收。
项目恢复、参数别名和3D/UV继续后续B3阶段；不能把当前save_draft当作完整项目恢复。
本轮不部署、不更新安装桥接、不重启已有host；现有五个egg-info修改未纳入提交。


## 2026-11-16 B3.2 参数别名（未部署）

新增 `shader_parameters`，旧73个工具输入schema逐项相同，总74个；122项本地MCP测试通过。
共享工作区原生身份、revision与UI/replay队列不变，无Python端别名或撤销副本。
参数整数用字符串传输，事件与共享范围明确分开；原生不支持布局/初值源时错误原样传回。
双架构参数GUI/MCP矩阵、四种语言主题组合与缩放，以及原工作区双架构回归通过；
主仓库 `fork-sync-b3-stage2-20261116.json` 记录实际PID/哈希/截图。未部署，未安装桥接。


### 2026-11-16 B3.3 project producer/consumer delta

- GUI owns portable project files, matching, compilation and grouped replay history. Python bridge
  forwards `shader_project` through the existing UI callback and native `ShaderWorkspaceCommand`;
  it owns no duplicate replacement/undo state. Apply requires both project and capture edit revisions.
- Controller adds `SetFrameEventForAnalysis`, mirrored in PythonInvoker/SWIG; unsupported remote
  replay/API paths return errors. Existing IReplayOutput/driver methods and wire protocol stay intact.
- GUI/CLI/DLL/Python module filenames, retained public identities, compatibility aliases, extension
  discovery, installed launchers and bridge directories are unchanged. No deployed runtime updated.
- Actual tools/list: 75, with all prior74 input schemas identical. New project errors preserve native
  diagnostics and returned revision/recovery state. Local MCP suite:125 passed.

### 2026-11-16 B3.4 mesh workspace producer/consumer delta

- Native frontend adds `IReplayOutput.SetMeshSelection/GetMeshPreviewTransform` and `ICamera.GetState/SetState`,
  with reflected CPU payloads and both Python builds. Mesh commands continue through the existing
  `ShaderWorkspaceCommand`, GUI identity and replay queue; no second MCP host or undo state.
- Adds `mesh_workspace(state/show/configure/select/focus/pick)` only: 76 actual tools, prior75 input schemas
  unchanged, schema SHA256 `814c1f4585e4bf5f8337309ce9d2d6c42dcc0c62f3f060a6f01165ba222664ce`.
  Session/revision and geometry/topology mismatch errors preserve native messages.
- Local D3D11/D3D12 triangles and native output verified with owned dual-architecture fixtures,
  Chinese/English and RDLight/RDDark, fractional scaling; selected StarRail/Control event project A/B/A
  uses actual built DLLs and fresh stdio. Does not claim GL/Vulkan/remote/Metal selection support.
- 127 local MCP tests passed. Full producer evidence, executable/DLL/RDC hashes and owned PIDs:
  main repository `docs/diagnostics/fork-sync-b3-stage4-20261116.md/json`.
- Source bridge only. No installed bridge or `C:/RenderDocCustom` deployment, no unrelated process closure.


## 2026-11-16 B4.3 捕获帧流程事实图

新增 `get_frame_graph(session_id, revision, window_id, after_eid=0, limit=64, rid=None)`，原77工具完整输入descriptor不变，现78工具。schema SHA256 bfecff4cf59e23f7bdd4daf66c6645f5ee12d3fdb1810d4c1710977a860fcd38。

FrameGraphService在原UI/Replay队列只读采集CurRootActions/GetResources/GetUsage，核对capture UUID/revision和selected/effective EID；不选择事件、不申请GPU输出、不另建undo。分页按EID，capture_order与父marker独立，避免D3D12合成marker大EID漏页。同事件用途不拆页，原枚举保留，不推断GPU依赖。

主GUI增加FrameGraph停靠面板，AIWorkspace::Analyse复用同Host任务回执；无CLI/DLL/helper/绑定/路径/安装布局改动。B3/B4 capability按实际ShaderWorkspaceCommand等接口报告；不支持前端明确报告unsupported。

本地164单测、双架构Development/GUI各32例2002断言/Python一致；四组D3D11/12 GUI PID67844/61360/61676/32696，通过新runtime/源bridge共470+4检查，另PID34236能力检查120+1。覆盖双基线、分页/用途、full/live编辑后分析、FP32与统一undo A/B/A、切换关闭陈旧拒绝。详细产物/RDC/bridge/SHA/截图见主仓docs/diagnostics/fork-sync-b4-stage3-frame-graph-20261116.json。

未部署安装bridge或C:/RenderDocCustom；保留既有egg-info修改。未验证其他GPU API/Mac/Linux，也不声称捕获usage反映修改Shader的动态访问。API/ACP、RT圈选与任务调查恢复继续。


## 2026-11-16 B4.4 RT 圈选数值证据

新增`get_texture_region`，显式window_id/capture UUID/revision/EID/rid、矩形与mip/slice/sample/type_cast。D3D11/12原生PickPixel至多9个去重网格点；typed整数、解码浮点值/FP32位与显示快照分开，不是整区统计或原始存储字节。保持当前selected/effective EID，不SetFrameEvent、不另建Replay/undo。其他API、过期捕获、无效范围/隐式MSAA resolve明确失败。

现79工具，原78完整输入descriptor保持一致；schema SHA256 08baa7a1f619c678a4c9a189300b701c6c420aa48cdf313155b7c6156500e730。GUI新增原生CPU标注入口，复用同Host/UI/Replay；CLI/DLL/helper/导出/Python类型别名、日志路径与安装布局不变，无controller/invoker/代理ABI变化。

170单测通过；新Development x64/x86 GUI各32例2002断言/Python一致。实际源桥接窗口PID58712/45588/12420/44352，四组698+4检查；x64真实MSAA sample2补验PID47412/59148共342+2；实际array/mip、full/live事件编辑后分析、浮点原值与撤销A/B/A、主题/关闭生命周期通过。主仓stage4-rt-annotation.md/json记录RDC、产物、loaded DLL、窗口、截图SHA和真实本机Codex图像问答。

本批不部署安装bridge，不动五个egg-info修改。真实3D纹理/整数RT、x86 MSAA、其他GPU API、远程GPU/Mac/Linux和游戏帧未覆盖；B4.5持久化恢复及API/ACP继续。
