# B2 RT 历史与共享 Buffer（2026-11-14，未部署）

使用配套 B2 RenderTest GUI/DLL 和 source bridge。所有工具沿用 B1 `window_id`、捕获
`session_id` 和 `revision`，由同一 CaptureContext / replay queue 执行，不建立第二套撤销。
原有67个工具的输入schema不变；新增5项，共72项；schema SHA256为
`c94954dc1eb407b3f28e8fd285d027e01483057e632bf2ecaeebb97735cae0a2`。

1. `get_event_edit_state` 取得当前捕获UUID、revision、事件与绑定。
2. `get_rt_history(session_id, revision, texture)` 枚举捕获RT用途/EID及mip/slice/sample信息。
3. `get_rt_snapshot(..., eid, texture, mip=0, slice=0)` 原子读取该事件的历史快照并恢复当前
   有效回放事件及UI选择。返回原生字节长度/SHA256/前256字节hex与独立RGB8 preview；
   `raw_path` 可导出全部原始字节，原子替换。`range_min/max`只影响显示，不改变原始精度。
4. `set_shared_buffer_editing_enabled(..., enabled=true)` 显式启用本进程默认关闭的实验能力。
5. `apply_shared_buffer_edit(..., buffer, offset, length, data_hex=...)` 提交绝对范围；也可
   使用精确长度`data_path`。`reset=true`且没有字节源时恢复范围捕获行为。返回新revision。
6. `get_shared_buffer_state` 返回有效范围及SHA256；`undo_event_edit`与GUI按钮统一撤销，
   局部reset亦可撤销。每次操作使用最新接受的revision，陈旧UUID/revision明确失败。

共享修改作用于所有事件/阶段消费者；B1事件CBuffer影子仅在对应draw上优先。
GUI共享范围是当前完整CBuffer窗口，MCP可提交更小范围。有效编辑与全局Shader/资源替换
互斥；清除共享范围后允许全局替换，但撤销不能在全局替换存在时重新引入共享覆盖。

当前支持本地D3D11/12单采样2D/数组RT。MSAA、3D、远程和其它API明确拒绝，不静默resolve。
共享范围最多64条/16MiB，原生要求可恢复初值；拒绝UAV/间接参数/稀疏、D3D12重叠placed
allocation与增强Barrier等未完整覆盖的依赖。具体原生错误透传，失败不递增接受revision。
缺少新CaptureContext API的旧GUI明确返回不支持，不能fallback到旧安装版。

桥接心跳现在由独立纯文件线程更新，不读取UI；`heartbeat_status`记录文件写入耗时/错误。
配套SWIG长事务在拥有输入副本后释放GIL，防止GPU等待使心跳线程饥饿。客户端2秒阈值和
请求超时不变，写请求不自动重试。停止先结束心跳线程，再清理实例目录。

本地验收：113项MCP测试；主仓库双架构构建、核心/GUI绑定、13个隔离GUI+fresh stdio会话，
含双API/加速交叉/双语浅深、mip1/slice1与MSAA拒绝、导出失败恢复、真实StarRail/Control
双基线与A/B/A、GUI/MCP交叉撤销与捕获关闭重开。原始证据：
`E:/RenderDocProject/work/fork-sync-b2-20261114`；主仓库记录
`docs/diagnostics/fork-sync-b2-20261114.md/json`含实际PID/窗口/运行文件与RDC哈希。
不是上游测试或旧安装GUI验收。x86 Control FL12_2、GPU故障注入、Mac/Linux/新远程会话未验收。

用户要求暂不部署：未更新C:/RenderDocCustom或AppData安装bridge，未重启旧host。
只向自有`fork/master`正常推送；原有5个egg-info文件修改保持原样、不夹带提交。
