# 场景重建、贴图、Shader 分析与转换

本分支沿用同一 qrenderdoc 会话。首次使用请先完成 [安装与后端配置](./setup.md)。以下 10 个工具注册在 `run-mcp` 的 FastMCP 服务中；不作为 `run-local-json` 的命令别名提供。

| 工具 | 用途 |
| --- | --- |
| `collect_reconstruction_evidence` | 汇总所选 draw 的几何、管线和 shader 常量证据 |
| `resolve_capture_camera` | 从已确认语义的 view/projection 推导相机位置 |
| `extract_capture_camera` | 从明确 buffer 偏移提取相机矩阵及原始字节 |
| `export_scene_bundle` | 几何、实例、相机、贴图和 DCC 交接包 |
| `export_texture_bundle` | 批量贴图与逐项状态 |
| `export_shader_analysis_bundle` | Shader 分析证据包 |
| `get_shader_conversion_capabilities` | 查询本机编译/反编译后端路径 |
| `convert_shader_language` | 带诊断的编译、反编译和跨语言转换 |
| `debug_shader_invocation` | PS/VS/CS 单次 invocation 完整调试轨迹 |
| `read_shader_debug_trace` | 分页读取轨迹、按变量名筛选变化 |

涉及实时捕获的新增工具要求显式 `window_id` 和 `expected_capture`。`dest` 为尚不存在的目录（语言转换工具为尚不存在的文件），以免覆盖先前结果。`manifest.json` 的 `complete` 表示导出操作完成情况；场景的 `reconstruction_complete` 与 `unresolved` 单独说明重建信息是否齐备，不证明与原画面一致。部分导出失败时保留已写出的证据与错误。

每项桥接调用前及结束时检查捕获路径。这是路径级检查，不是 RDC 内容指纹或原子快照；批量导出期间请勿切换/覆盖捕获。导出包可能包含本机路径、捕获内 shader 和资源，分享前应检查内容。

## 场景与 DCC 交接

1. 用 `list_live_windows` 确认 window_id 和 capture 路径。
2. 用 `find_events` 选择有意义的 draw；`collect_reconstruction_evidence` 保存几何、管线、VS/PS 绑定和常量证据。
3. 相机矩阵语义确认后，用 `extract_capture_camera` 从 buffer 的明确字节偏移读取两个 float32 4x4 矩阵；分别声明 row_major 存储与 row_vector 数学约定。它会导出原始 64 字节证据以及 camera.json。已有矩阵时使用 `resolve_capture_camera`。
4. `export_scene_bundle` 默认 delivery=data。每个 draw 包含 eid；可补充 instances，每个 instance 包含 matrix（16 个数学行序、列向量乘法元素）和 evidence。源坐标单位/轴转换由 source_to_gltf 显式声明。
5. DCC 直接读 DCC_HANDOFF.json 和 geometry.json 创建网格；无需经 OBJ/glTF。geometry 的 face 每个角为 [position_index,uv_index,normal_index]，零起点，缺失属性为 null。UV 的方向保持原始捕获数值，由目标材质采样约定决定是否翻转。
6. 对象变换、实例展开、材质语义和相机未确定时保留 unresolved。不要把默认原点位置当作原场景位置。原始绑定材质和 DCC PBR 材质不能自动等同。
7. delivery=fbx 会在交接文件中标记 `requires_downstream_DCC_export`，不会创建 FBX 文件或自动调用 DCC。由使用方通过目标 DCC 的 MCP 读取交接包、重建场景，再调用 DCC 的 FBX exporter 并验证文件。无需安装第二套 RenderDoc MCP。

示例 draws：
```json
[{"eid":133,"export_postvs":true,"instance_count":1,
  "instances":[{"matrix":[1,0,0,2,0,1,0,3,0,0,1,4,0,0,0,1],
                "evidence":{"stage":"vs","cb_slot":0,"byte_offset":64,"meaning":"verified object-to-world"}}]}]
```
示例矩阵只说明格式，不能用于未知截帧。Mesh 当前继承 TriangleList VS-input OBJ 解码限制；PostVS 原始缓冲可另行导出，但需要按 shader 输出语义还原。骨骼、动画、隐藏场景和 shader 变形不能由一帧通用恢复。

`delivery` 表达交付意图；当前所有模式都保留作为解码中间结果的 OBJ 与直接供 DCC 使用的 geometry JSON。只有提供 `source_to_gltf` 和带证据的实例变换，才会额外生成放置后的 `scene.gltf`。相机与材质信息保存在交接 JSON 中，当前 glTF 写出器只输出几何和实例节点。

例如调用 `export_scene_bundle`（将窗口、路径和事件替换为实际值）：

```json
{
  "dest": "C:/exports/frame-scene-001",
  "draws": [{"eid": 133, "export_postvs": true, "instance_count": 1}],
  "window_id": "WINDOW_ID_FROM_list_live_windows",
  "expected_capture": "C:/captures/frame.rdc",
  "delivery": "data"
}
```

这个示例导出未放置的基础网格并报告相机/变换未知。相机 buffer locator 格式为 `{"rid":"ResourceId::123","offset":64,"row_major":true,"row_vector":false}`；offset 是 buffer 的绝对字节偏移，两个布尔值必须分别声明。每个 locator 读取 64 字节 float32 数据，不自动识别矩阵变量。

## 贴图

`export_texture_bundle` 的 textures 参数为 `{rid,eid,format,type_cast?,role?}` 数组；每项使用指定事件状态，独立记录失败，附文件大小和 SHA256。支持 DDS/PNG/EXR/HDR 等后端格式。优先用 DDS 保存原始数值；typeless 资源按实际绑定视图指定 type_cast。role 是有证据的用户语义，不从名字猜测。

## Shader 分析与调试

`export_shader_analysis_bundle` 保存 draw、反射、实际常量、完整分页源码/反汇编、原始字节码、Ruri 反编译结果/诊断；可指定 pixels 数组（x,y，可加 rid 导出 pixel history）。缺失源码不会伪造成 HLSL；反编译失败记录为部分成功，原始字节码与反汇编仍保留。

`debug_shader_invocation` 对 PS 使用 {x,y}，VS 使用 {vertex,index,instance,view?}，CS 使用 {group:[x,y,z],thread:[x,y,z]}。dest 为新目录；导出完整状态变化、指令、调用栈和精确值位模式，达到 max_steps 则标记不完整。读取时用 `read_shader_debug_trace` 按步分页并按变量名过滤。每个捕获/API 的实际支持范围以 RenderDoc 后端返回为准。调试器结果是模拟，需与真实 GPU 回放输出比较。

已有 `apply_shader_edit`、`revert_shader_edit` 和 `save_event_output_texture` 用于明确授权的替换实验和前后图像比对。新分析/转换工具不会自动替换 shader。

## 着色器转换

- HLSL → DXBC：Windows SDK FXC。
- HLSL → DXIL/SPIR-V：独立 DXC（带 SPIR-V codegen）。
- GLSL → SPIR-V：glslang。
- SPIR-V → HLSL/GLSL/MSL：SPIRV-Cross。
- DXBC/DXIL → 重建 HLSL：Ruri；可再走上述编译/跨语言路径。

使用 `get_shader_conversion_capabilities` 检查后端，`convert_shader_language` 执行转换。输入 source_path/source_language/target_language/stage/entry/dest；可指定 profile。目标文件与 .conversion.json 均须不存在。返回编译诊断、输入输出哈希和 semantic_equivalence_verified=false。代码转换成功并不代表绑定、坐标、精度或画面等价。MSL 输出目前不包含目标平台编译验证。

第三方编译器按 [后端配置说明](./setup.md#可选-shader-后端) 单独安装，工具不会自动下载。环境变量 `RENDERDOC_MCP_DXC` / `RENDERDOC_MCP_FXC` / `RENDERDOC_MCP_SPIRV_CROSS` / `RENDERDOC_MCP_GLSLANG` 可指定路径；Ruri 支持 `RENDERDOC_MCP_RURI_DLL` 与 `DOTNET_ROOT`。

转换工具调用参数示例：

```json
{
  "source_path": "C:/shaders/example.hlsl",
  "source_language": "hlsl",
  "target_language": "spirv",
  "dest": "C:/exports/example.spv",
  "stage": "ps",
  "entry": "main",
  "profile": "ps_6_0"
}
```

编码名称使用 `hlsl/glsl/spirv/dxbc/dxil`；目标另支持 `msl`。GLSL/SPIR-V 转 DXBC/DXIL 需要先显式转成 HLSL 再编译。FXC 使用 stage 对应的 shader model 5 profile，DXC 使用 shader model 6；GLSL 输入按 Vulkan SPIR-V 编译，不保证任意 OpenGL shader 可直接接受。

## 生效与验证

网关 editable 安装会在 MCP 重连后加载新工具。debug_shader_invocation 增加了桥接方法，需重新加载 RenderDoc 扩展或重启窗口。不会强制关闭用户正在分析的窗口。

验证包括矩阵求逆、glTF 矩阵序列化、源代码分页、错误/截帧切换处理、调试分支与释放，以及真实编译后端和 stdio MCP 调用。2026-10-31 的 Windows/D3D11 本机验收已导出几何、DDS、VS/PS 证据；其中 PS 的 Ruri 反编译发生上游 overflow，已明确保留诊断，采用反汇编分析。新增 VS/CS 调试路由经模拟后端测试，尚未在重启后的真实桥接中验收。测试不包含完整场景视觉对齐、真实相机恢复或 DCC/FBX 端到端交付。
