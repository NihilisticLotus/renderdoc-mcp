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
