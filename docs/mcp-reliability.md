# MCP 构建与稳定性调整

检查日期：2026-10-10。版本：`volcengine-ark-mcp 0.5.1`、`ali-bailian-mcp 0.4.1`、`doubao-speech-mcp 0.3.2`。

## 结论

主要瓶颈是 HTTP 连接无法复用、超时不覆盖完整调用、失败结果没有正确设置 MCP `isError`、恢复记录的并发覆盖，以及音频/任务在断流后丢失。已针对这些路径调整实现并增加故障测试。同步业务函数由 worker 执行，不能把 `def` 本身等同于阻塞 MCP 事件循环；本次保留业务适配器，通过共享异步 HTTP 运行时实现可取消网络 I/O。

当前采用本地 stdio、三个可独立安装的包和本地持久任务，符合现有部署方式。没有为了使用新名词改成远程 HTTP 服务。最新规范中的新增能力也不等于当前所有客户端都已支持；协议版本继续由 Python SDK 与客户端协商。

## 规范与实现对照

| 来源 | 对本项目有用的要求/实践 | 本轮调整 |
|---|---|---|
| [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | 稳定工具顺序、合法 schema、结构化结果、工具执行失败与协议错误区分 | 按名排序，参数边界，`outputSchema`，`structuredContent`；业务 `ok=false` 映射 `isError=true`；协议解析仍交给 SDK |
| [MCP Cancellation](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/cancellation) | 协作取消，进度不能无限延长执行 | 工具绝对 deadline；取消在途 HTTP、轮询和 queued worker；已运行 worker 保留真实并发名额 |
| [MCP Progress](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/progress) | 使用客户端 progress token、单调进度、结束后停止 | 可选 heartbeat，无虚构完成百分比；报告失败不影响业务；完成时取消 heartbeat |
| [Python SDK lifespan](https://py.sdk.modelcontextprotocol.io/handlers/lifespan/) | 共享资源在启动初始化、关闭时释放 | 一个 AsyncClient/进程；退出清理连接、执行器和实时会话 |
| [HTTPX Clients](https://www.python-httpx.org/advanced/clients/)、[Timeouts](https://www.python-httpx.org/advanced/timeouts/)、[Limits](https://www.python-httpx.org/advanced/resource-limits/) | 连接复用、分阶段超时、资源上限 | HTTP pool16、keepalive8、worker8；请求 deadline 覆盖响应体，流式上传/下载 |
| [MCP Tasks Extension](https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks) | 长任务通过协商后的任务能力获取结果 | 继续保留 `job_id/task_id + query/recover`；未宣称原生 Tasks 支持，后续需 SDK/客户端兼容测试 |

Annotations 是行为提示，不能代替执行控制。付费生成不标为 read-only 或幂等；本地状态/说明读取明确标为只读。工具分组在进程启动时确定，避免同一连接的工具列表随调用变化。

## 同类源码再分析

| 实现 | 源码观察 | 对本项目的判断 |
|---|---|---|
| [火山官方 Ark MCP 示例](https://github.com/volcengine/ai-app-lab/blob/main/mcp/server/mcp_server_ark/src/mcp_server_ark/server.py) | 有 AsyncArk 接入，但逐调用创建客户端；部分 `requests.post` 未设置 timeout | 产品接入可参考，连接与超时处理不能直接照搬 |
| [qwen-omni-mcp server](https://github.com/sommio/qwen-omni-mcp/blob/develop/src/server.ts)、[Bailian adapter](https://github.com/sommio/qwen-omni-mcp/blob/develop/src/bailian.ts) | 有 MCP 错误结果和 AbortController；计时器在 fetch 返回 headers 后清理 | 错误语义值得借鉴，但仍要验证慢响应体、断流与总预算 |
| [mcp-server-replicate](https://github.com/tzafrir/mcp-server-replicate/blob/main/server.py) | 同步客户端和直接下载的简洁适配 | 适合看接口组织，不能据此证明重启恢复、交付幂等或连接效率 |

上述对照是所检索源码的静态观察，没有运行它们做性能排行榜。上游文件可能继续变化。这里的工程判断是：本项目的多媒体任务、付费副作用与恢复需求，比简单 API 包装器更需要持久记录和故障契约。

## 已完成的实现

- `shared/transport.py` 为 HTTP 唯一共享来源：AsyncClient lifespan 连接池、同步 worker 桥接、总预算、取消、流式响应和流式 multipart。保留 urllib Request 兼容业务层，避免一次性重写所有提供商适配器。
- `shared/mcp_runtime.py` 统一工具边界：独立的业务 worker 和本地状态 worker、参数校验、错误语义、结构化输出、工具分组、完整说明按需读取、可选进度。日志只输出工具名、结果和耗时；HTTPX/httpcore 的 URL 日志关闭，避免签名 URL 进入普通日志。
- GET 仅在 `429/502/503/504` 下有限重试，最多两次，尊重 `Retry-After` 与总预算。POST 不自动重放；网络失败不擅自重新提交生成。下载依赖显式 `recover_job`。
- 两个 Job Store 用原子替换、fsync、跨进程 `flock` 和 revision 检查防止旧记录覆盖新状态。首次生成持有处理租约；下载最多四路并行，协调者单写记录。SHA-256 验证通过的文件不重复下载/探测，保留 mtime。
- 百炼 SSE 正确处理多行事件、心跳、完成标记、异常 JSON 与断流；失败保留已收到文本、reasoning 和 usage。视频默认只提交/单次查询，缩短同步等待。
- 豆包 TTS 每段提交前记下“结果未知”凭据，完成后立刻保存音频和 manifest；后续失败保留前面已付费段，截断音频明确标为 incomplete，不自动重试。音频、字幕和 manifest 原子发布并使用唯一文件名。
- 实时语音有空闲回收、关闭会话保留期限、有限事件队列和 `dropped_events`；复用音频文件句柄，超时/取消/退出关闭连接。其他 async 语音接口将文件读取、协议解码和最终落盘移出事件循环。
- 三个包仍可分别安装，运行时复制由 `scripts/sync_shared.py --check` 防漂移。依赖锁文件齐全，新增 Python 3.10/3.13 CI，执行故障测试、真实 stdio 和独立打包。

## 调用体积

本地 `tools/list` 测量，不调用云服务。口径为 tool 模型 `model_dump(mode="json", by_alias=True, exclude_none=True)` 后 `json.dumps(..., ensure_ascii=False)` 的 UTF-8 大小；不是实际 token 数，也不含 JSON-RPC 外层。

| Server | 调整前工具/字节 | 调整后完整工具/字节 | 分组示例 | 分组工具/字节 | 相对完整配置减少 |
|---|---:|---:|---|---:|---:|
| Ark | 9 / 11,981 | 10 / 13,228 | `image,jobs,help` | 6 / 5,256 | 60.3% |
| Bailian | 19 / 25,060 | 20 / 26,301 | `language,help` | 4 / 3,856 | 85.3% |
| Speech | 28 / 32,059 | 29 / 33,323 | `realtime,help` | 7 / 6,476 | 80.6% |

完整工具描述由 19,890 字符降到 12,944，减少 34.9%。完整 schema 从 69,100 增至 72,852 字节，增加 5.4%，原因包括新增帮助工具、输入边界、annotations 和输出契约。因此本轮没有把“描述变短”包装成“总 schema 变小”。实际上下文优化主要来自按用途分组和默认不重复返回 raw response。

复现：

```bash
servers/doubao-speech/.venv/bin/python scripts/measure_tools.py volcengine-ark
servers/doubao-speech/.venv/bin/python scripts/measure_tools.py volcengine-ark --groups image,jobs,help
servers/doubao-speech/.venv/bin/python scripts/measure_tools.py ali-bailian --groups language,help
servers/doubao-speech/.venv/bin/python scripts/measure_tools.py doubao-speech --groups realtime,help
```

调整前数字是本轮开始时的工作树基线。分组只改变暴露范围，不改变产品权限或云账户授权。

## 配置与兼容性

| 环境变量 | 默认 | 作用 |
|---|---:|---|
| `MCP_TOOL_TIMEOUT_SEC` | 300 | 完整调用预算，最大 3600 秒；客户端预算应至少覆盖服务端预算及清理余量 |
| `MCP_WORKERS` | 8 | 同步业务 worker / async 调用上限；本地说明与状态另有 2 个 worker |
| `MCP_HTTP_CONNECTIONS` | 16 | HTTP 连接上限；keepalive 最大 8 |
| `MCP_MAX_RESPONSE_MB` | 512 | 完整响应读取和单个流式行的上限；流式文件下载不整体缓冲 |
| `MCP_TOOL_GROUPS` | 全部 | 逗号分隔分组；未知分组启动时报错；修改后重启 |

可选分组：Ark `image,video,language,embedding,jobs,help`；Bailian `image,language,speech,video,embedding,jobs,help`；Speech `speech,realtime,management,help`。`get_tool_help` 始终可用；能力工具返回 `enabled_tools/selected_groups`，区分产品总目录与当前暴露工具。

兼容性变化：

1. `ok` 表示本次调用成功；任务仍运行时为 `ok=true, completed=false`。全部交付 `completed=true`；失败/部分失败设置 MCP `isError=true`，保留成功产物。`get_job.ok` 是记录读取结果，不能据此认定任务已完成。
2. `chat/query_video/embed/rerank/get_job/recover_job` 默认移除重复的 `response`；需要原始响应时传 `include_response=true`。原始语音透传与管理接口保留它们的主要响应。
3. 百炼 `generate_video/query_video` 默认 `wait=0`，需要等待时显式传入，最大 90 秒。
4. Ark/Bailian 的显式 `out_dir` 作为父目录，每次调用创建带随机后缀的子目录；Speech 保持显式目录，但音频/字幕文件名唯一。依赖固定文件名的脚本应改用返回的 `files`。
5. 任务恢复锁使用 POSIX `flock`，当前支持范围为 macOS/Linux。旧无 revision 的任务记录仍可读取；状态未知的付费请求不自动再次生成。

线程中的文件 I/O 无法被 Python 强制终止。超时后真实 worker 名额不会提前释放；正在进行的原子落盘可能继续完成。取消不是撤销云端任务或退款。已有任务通过本地记录及提供商 task_id 查找，不能把未知提交结果当作未付费。

## 验证与剩余工作

本轮本地 183 项测试通过：Ark 18、Bailian 25、Speech 120、跨包运行时/提供商契约/stdio 20。独立复查另跑运行时与 TTS 故障测试 29 项，通过。

覆盖 TCP 连接复用、GET 重试与 POST 不重放、慢流总超时、在途取消、gzip/重定向、multipart、真实 worker 上限、错误/schema/progress、任务并发恢复/损坏/SHA、SSE 断流、已付费音频保留和实时会话资源回收。三个实际安装入口完成初始化、发现、调用和正常退出。

这些证据确认本地契约和故障处理，不证明新增云产品已经可用。尚未验证真实账户权限、提供商限流/计费、长任务端到端恢复和云端 p50/p95 延迟。远端检查状态见 [MCP offline contracts](https://github.com/hoobnn/hoobnn-mcps/actions/workflows/test.yml)。下一轮云端验证应按产品选小样本，记录提交/查询/下载耗时与 task_id，在断网和进程重启后检查恢复，并以实际账单确认没有重复生成。
