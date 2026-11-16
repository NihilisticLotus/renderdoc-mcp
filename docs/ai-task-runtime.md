# B4.1 持久化任务 Host

本阶段在原有 bridge 上新增默认关闭的 `host_tasks`，没有新增 ReplayController、替换表或撤销栈。已有 76 个工具的输入 schema 不变；新增后共 77 个工具。

## 使用与恢复

1. `host_tasks(operation="capabilities", window_id=...)` 获取协议、支持的方法及限制。此操作不创建日志。
2. `enable` 创建 Host，保存返回的 `host_id`。用既有 `get_event_edit_state` 取得当前 `session_id` 和 `revision`。
3. 客户端先生成并保存规范 UUID `task_id`，再 `submit(host_id, task_id, session_id, revision, method, arguments)`。`method` 必须出现在能力列表；捕获打开/关闭等生命周期方法不允许包装为任务。`arguments` 是该 bridge 方法的参数；Host 身份字段不代替原方法要求的身份字段。
4. 使用 `get` / `list` 查看记录。同一 ID、同一请求的重复提交只返回原记录，永不再次执行；不同请求重用 ID 明确报错。断线后使用新 MCP stdio 连接及原窗口/Host/任务 ID 查询。
5. `cancel` 只能保证尚未开始的工作不会执行；运行中的请求只记录 `cancel_requested`。`queue_timeout` 对排队任务执行取消；对已经开始的任务记录 `wait_timeout`，继续等待真实结果。
6. `disable` 要求没有活动任务。随后 `enable(host_id=...)` 打开原日志；另一个 GUI 进程不能同时拥有该 Host。GUI 重启需重新发现窗口，再显式打开日志，不自动开始回放。

状态：`queued`、`running`、`succeeded`、`failed`、`cancelled`、`interrupted`、`unknown`。`failed` 保存原生返回的错误，不能当作通用的回滚承诺。已进入处理函数却未能取得 JSON 结果的异常为 `unknown`。GUI/进程意外退出后，旧 queued 变为 interrupted，旧 running 变为 unknown；终态不变。任何旧任务都不自动重试。要开始新工作，先检查当前捕获及原生编辑状态，再使用新 ID 提交用户意图。查询旧结果不会恢复旧撤销栈。

## 执行及存储约束

- 先落盘请求指纹和 queued，再调用 MiniQtHelper 原 UI dispatcher；UI 执行前落盘 running，核对捕获 UUID/revision，再进入现有 handler / CaptureContext / Replay 队列。
- Control 轮询与普通 bridge handler 分离，查询和取消不访问 capture/Qt/GPU。心跳继续独立；并发轮询在一个锁内领取请求，避免重复处理。
- 单写者 OS 文件锁；每任务原子 JSON 文件，版本和 SHA256 校验；写临时文件、flush/fsync 后 replace。新文件写入失败保留旧完整文件。恢复前先校验全部文件，不静默忽略坏数据。
- 默认目录 `%LOCALAPPDATA%/RenderTest/mcp-tasks/<host_id>`；`RENDERTEST_MCP_TASK_STORE` 只覆写目录，不启用 Host。目录属于当前用户本机存储；不是远程认证接口。
- 32 活动任务、256 记录、每记录 8 MiB、每 Host 64 MiB。列表只复制摘要。容量耗尽明确报错，不静默截断结果。
- 原生操作结束但结果落盘失败时，当前进程提供 `persisted=false` 的 unknown 记录，并停止接收新任务。重开后以旧 durable 状态恢复，不伪称写入成功。
- 日志保存请求、结果、原始诊断及事件序号，可能包含 Shader 源码和本地路径；不读取认证配置，结果中的旧 ResourceId 仅供诊断，不恢复 GPU 句柄或 runtime undo 栈。旧 session 仅作为拒绝重用的身份凭据保存，不是新捕获可用的令牌。请求指纹覆盖 JSON 参数，不承诺冻结外部路径所指文件；源码快照仍由原 Shader 工作区负责。
- bundled Python 3.6 可加载；不依赖 sqlite、PySide 或升级 Qt。主仓库原生接口、invoker、绑定、代理均不改 ABI。

## 验收与阶段边界

156 项本地单测覆盖任务状态竞争、普通 handler 阻塞时的控制响应、文件损坏、落盘失败、跨进程单写者锁、异常进程退出、重复提交、捕获/revision 陈旧保护及执行后异常。具体最终数量和真实 GUI/MCP PID、产物/RDC 哈希以 Dev-RenderDoc 的 `fork-sync-b4-stage1-20261116.md/.json` 为准。

真实自有 D3D11/D3D12 RDC 通过新 stdio 客户端验证 Shader/CBuffer 编辑、FP32 原值、邻居不污染、GUI/Host 统一撤销、断线重连、取消/超时及关闭重开。新增工具是机器接口，没有新产品文案；沿用原 GUI 中英和浅深主题。

本阶段未部署、未更新安装 bridge。内嵌 Codex app-server、流式 AI、帧图、RT 圈选和可停靠监视器继续 B4.2–B4.5，未冒充完成。
