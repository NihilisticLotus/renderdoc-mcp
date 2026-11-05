# Windows 安装与升级

这是源码安装说明，适用于本分支的 qrenderdoc 实时分析与导出功能。需要 Windows、已安装的 RenderDoc，以及外部 Python 3.11 或更高版本（本分支在 Python 3.12 上验证）。RenderDoc 内嵌 Python 运行桥接扩展，外部 Python 运行 MCP 网关，两者不必是同一版本。

## 安装网关与桥接

在 PowerShell 中执行；源码目录可以任意命名，不要求名为 `source`：

```powershell
git clone https://github.com/NihilisticLotus/renderdoc-mcp.git
Set-Location renderdoc-mcp
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\install_ext.py --incremental
```

默认 `renderdoc` 前端将扩展安装到当前用户的 `%APPDATA%/qrenderdoc/extensions/renderdoc_mcp_bridge`，并更新该前端的自动加载与 Ruri 菜单配置。`--frontend rendertest` 使用 `%APPDATA%/qrendertest/...`，`--frontend renderduck` 使用 `%APPDATA%/qriderduck/...`。`--incremental` 保留已安装目录中的其他文件；旧的废弃文件不会被清除。脚本不会安装 RenderDoc、.NET 或额外编译器。

在 MCP 客户端新增 stdio 服务：

- **command**：源码目录内 `.venv/Scripts/renderdoc-mcp.exe` 的绝对路径。
- **args**：`["run-mcp"]`。
- **env**：按需填写下面的编译器/.NET 环境变量；从客户端配置中设置，或确保客户端启动时继承了它们。

该客户端配置放在用户级或项目级由使用者选择；桥接安装位置是当前 Windows 用户级。离线 Python replay 的安装发现与实时 qrenderdoc 桥接是不同路径，单纯使用实时导出不需要在外部 Python 中导入 RenderDoc。旧安装继续使用 `RENDERDOC_PATH`；改名为 RenderTest 的并行构建使用 `RENDERTEST_PATH`，该路径优先且必须含 `rendertestcmd.exe`，避免旧安装掩盖新运行时缺件。详见[兼容性矩阵](./renderdoc-compatibility.md)。

重启 RenderDoc 或重新加载扩展，打开一个可回放的 RDC；重连 MCP 后调用 `list_live_windows` 和 `get_capture_status` 确认连接。这里安装的是完整源码 checkout：桥接脚本与捆绑 Ruri 在 Python 包目录外，单独复制 wheel 或 `site-packages` 不能替代完整安装。

## 可选 Shader 后端

模型/贴图导出不依赖下面的编译器。缺少某个后端只影响对应转换路线；Shader 分析仍会保留其他已取得的证据，但 Ruri 不可用或失败会使分析包标记为不完整。

| 后端 | 用途 | MCP 进程环境变量 | 安装来源 |
| --- | --- | --- | --- |
| FXC | HLSL → DXBC | `RENDERDOC_MCP_FXC`：`fxc.exe` 绝对路径 | [Windows SDK](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/) |
| DXC | HLSL → DXIL / SPIR-V | `RENDERDOC_MCP_DXC`：`dxc.exe` 绝对路径 | [Microsoft DXC releases](https://github.com/microsoft/DirectXShaderCompiler/releases) |
| SPIRV-Cross | SPIR-V → HLSL / GLSL / MSL | `RENDERDOC_MCP_SPIRV_CROSS`：`spirv-cross.exe` 绝对路径 | [Khronos SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross) |
| glslang | GLSL → SPIR-V | `RENDERDOC_MCP_GLSLANG`：`glslang.exe` 绝对路径 | [Khronos glslang](https://github.com/KhronosGroup/glslang) |
| Ruri | 字节码 → 重建 HLSL | 可选 `RENDERDOC_MCP_RURI_DLL` | 仓库 `tools/ruri_shader_decompiler`，见其 [说明](../tools/ruri_shader_decompiler/README.md) |
| .NET 10 | 运行捆绑 Ruri | `DOTNET_ROOT`：包含 `dotnet.exe` 的目录 | [.NET 10 runtime](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) |

保留编译器发布包中的配套 DLL，不能只移动 EXE。DXC 必须包含 SPIR-V codegen；部分 Windows SDK 自带 DXC 虽有 `-spirv` 帮助项，执行时仍可能报告没有该功能。无需改全局 PATH。

编译器优先使用有效的环境变量路径，再查找 PATH（DXC 另优先兼容已有隔离安装），FXC/DXC 还会查找 Windows SDK 的 x64 目录。为兼容已有本机安装，也会查找源码父目录下的 `implementation/shader-conversion/`：DXC 位于 `dxc/bin/x64/`，SPIRV-Cross 位于 `build/Release/`，glslang 位于 `glslang-build/StandAlone/Release/`。新安装建议显式指定环境变量。

Ruri DLL 默认来自当前 checkout 的 `tools/ruri_shader_decompiler/`；dotnet 依次查找 `DOTNET_ROOT`、源码父目录的 `dotnet/`、PATH。DLL/EXE 存在不代表运行时版本兼容，可用下面命令检查 .NET 10：

```powershell
& "$env:DOTNET_ROOT\dotnet.exe" --list-runtimes
```

MCP 的 `get_shader_conversion_capabilities` 返回检测到的路径；再用小 shader 调用 `convert_shader_language` 验证实际编译。该查询不会执行每种编译器来验证功能或版本。

## 升级现有安装

保留自己的未提交补丁，先检查 `git status`；已提交或妥善保存后再从本分支拉取。不要用强制重置覆盖本地增强。

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\install_ext.py --incremental --skip-decompiler
```

上例保留现有 Ruri 安装与菜单配置；需要同步仓库捆绑 Ruri 时省略 `--skip-decompiler`。更新桥接后重新加载扩展/重启 RenderDoc；更新网关后重连 MCP。已有窗口不会被自动关闭。RenderDuck 用户改用 `--frontend renderduck`，其自由相机能力还需要对应前端版本，详见 [README](../README.md#renderduck-free-camera)。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实编译器回归会在对应可选后端缺失时跳过，不意味着转换路线已经验收。真实桥接与 GPU 回放需要打开捕获后另行验证。已验证范围和已知限制见 [工作流文档](./asset-shader-workflows.md#生效与验证)。
