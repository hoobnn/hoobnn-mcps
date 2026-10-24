# MiniMax 契约与迁移

首次接入核对：2026-10-11；最近契约复核：**2026-10-24**。依据用户指定的 [中国站接口概览](https://platform.minimax.cn/docs/api-reference/api-overview) 及其链接的 OpenAPI Markdown 正文；14 个接口来源纳入 `docs/audits/minimax-sources.json`、SHA-256 基线和 gzip 正文快照。

## 2026-10-24 文档更新审查

公开正文抓取 **14/14 成功，0 错误**，相对 2026-10-23 基线有 4 篇正文变化。完整差异见 [报告](upstream/minimax/review/15a7ef27daec7bbfe3b76e32b9cb69275265c05559c8fdf370672b40c4f93ebe/report.md) 及同目录 `diffs/`。

| 文档 | 实质变化 | 处理结论 |
|---|---|---|
| [创建视频任务](https://platform.minimax.cn/docs/api-reference/video-generation-v2-create) | `model` 枚举新增 `MiniMax-H3-Highspeed`（仅 768P、4–15 秒）与 `MiniMax-H3-Lite`（480P/768P、默认 768P、4–15 秒）；`MiniMax-H3-Lite` 多模态参考暂不支持 `adaptive`，需显式指定比例；`extra` 仍仅属于 H3-Max | `generate_video` 接入两个新模型及档位校验；Lite 参考模式未给或给 `adaptive` 的 `ratio` 时本地拒绝，不替用户猜比例；`extra` 继续只对 H3-Max 放行 |
| [同步语音](https://platform.minimax.cn/docs/api-reference/speech-t2a-http)、[Context-IR](https://platform.minimax.cn/docs/api-reference/video-generation-v2-h3-context-ir)、[再生成](https://platform.minimax.cn/docs/api-reference/video-generation-v2-regeneration) | 站内相对链接改为 `platform.minimaxi.com` 绝对地址 | 展示性变化；Context-IR 与再生成仍只接受 `MiniMax-H3`，请求不变 |

新模型仅按官方枚举做离线契约接入，未发送付费请求，不代表当前账号已开通。

## 2026-10-23 文档更新审查

公开正文抓取 **14/14 成功，0 错误**，相对本 PR 2026-10-14 待审基线有 5 篇正文变化。逐份提取、比较 14 个 `openapi: 3.1.0` 代码块，仅音乐模型的 `description` 文字发生变化；请求字段、枚举、参数限制、endpoint 均未改变。完整差异见 [最新报告](upstream/minimax/review/3f7f13d1f61bfdc795ca83686657953e43e9e7aaad03a5306e659e9489fc57af/report.md) 及同目录 `diffs/`，保留 10 月 14 日原始 review。

| 文档 | 实质变化 | 处理结论 |
|---|---|---|
| [音乐生成](https://platform.minimax.cn/docs/api-reference/music-generation) | 模型说明删除“仅限 M Plan 用户和付费用户使用”及免费版本“所有用户可通过 API Key 使用”等资格短语 | 页首 2026-08-20 停止新用户付费接口和免费接口的公告仍在，不能据此认定恢复开放；保留现有 `music-3.0` / `music-2.6` 支持及账号权限说明 |
| [同步语音](https://platform.minimax.cn/docs/api-reference/speech-t2a-http) | 内部文档链接改为 `.md` 导出地址 | 无需修改请求或恢复链路 |
| [Context-IR](https://platform.minimax.cn/docs/api-reference/video-generation-v2-h3-context-ir)、[再生成](https://platform.minimax.cn/docs/api-reference/video-generation-v2-regeneration)、[音色列表](https://platform.minimax.cn/docs/api-reference/voice-management-get) | 提示框改为 Markdown 引用，原参数正文保持一致 | 保留现有实现及模型校验 |

`create_h3_context_ir_task` 已是当前工具名；来源映射和新基线使用该名称，文件上传映射不再指向旧 `enhance_video_prompt`。这来自本地工具重命名，不是官方 API 改名。H3 创建页在旧 review 中的购买链接调整也无需运行时适配。

本轮只更新本平台文档快照、映射基线、审查说明；没有为展示性变化修改运行时代码，也不扩大音乐模型可用范围。验收覆盖现有 H3/H3-Max、Context-IR、再生成、任务故障恢复及实际 stdio；下方保留首次接入的历史验收记录。

本轮 Python 3.13 独立锁定环境验收：MiniMax **15 项测试通过**（含从当前 PR checkout 导入的真实 stdio 子进程），文档检测/分平台 PR **18 项测试通过**；`sync_shared.py --check`、`upstream_docs.py --check-coverage`（139 个登记来源）及 `git diff --check` 通过。未发送付费请求，未核实账号音乐权限。

## 官方 MCP 与新实现（2026-10-11 记录）

2026-10-11 首次接入时，本机 Codex 配置通过 `uvx minimax-mcp -y` 启动官方包，发现的本机缓存为 `0.0.19`。当时读取的 [官方 main 分支 server.py](https://github.com/MiniMax-AI/MiniMax-MCP/blob/main/minimax_mcp/server.py) 采用 V1 视频创建、查询和文件下载链路。这是历史记录，不代表官方包当前版本；缓存版本也不能证明每次 uvx 最终选择的版本。

| 项目 | 官方 MCP 读取到的实现 | 本次独立实现 |
|---|---|---|
| 包名 / 命令 | minimax-mcp | hoobnn-minimax-mcp |
| 视频提交 | POST /v1/video_generation，prompt + first_frame_image | POST /v2/video_generation，多模态 content[] |
| 任务查询 | GET /v1/query/video_generation?task_id=... | GET /v2/query/video_generation/{task_id} |
| 视频结果 | file_id → /v1/files/retrieve | task.content.url |
| 完成状态 | Success / Fail | succeeded / failed / cancelled |
| 未完成 | Preparing / Processing 等 | queued / running，ok=true、completed=false |
| 默认行为 | 长时间轮询 | 只提交，持久保存task_id，后续get_job查询 |
| 结果交付 | 一次下载 | 原子文件、完整性指纹、只补下载、刷新H3临时URL |

实现不复制官方项目代码，使用本仓库共享运行时；旧四个环境变量可继续使用。工具名保留常用媒体名称，但视频参数和任务不做 V1 兼容。`play_audio`、语言/ASR/流式与长文本异步语音不在此次范围。具体迁移见 [MiniMax README](../servers/minimax/README.md)。

## H3、H3-Highspeed、H3-Lite 与 H3-Max

以 [创建任务](https://platform.minimax.cn/docs/api-reference/video-generation-v2-create) 的正文和枚举为准：H3 为 768P/2K、4–15 秒；H3-Highspeed 仅 768P、4–15 秒；H3-Lite 为 480P/768P、4–15 秒，多模态参考须显式指定具体比例；H3-Max 为 480P/768P、5–15 秒。只有 H3 支持 2K。四者共用 content[]；H3-Max 的 extra.prompt_expansion_mode 支持 disabled/balanced/quality。

本地验证提示词、输入类型、文件大小、引用数量、互斥关系和模型档位；素材真实尺寸、编码、参考视频/音频时长由平台上传和生成校验。所有本地素材在生成前上传为 mm_file://，上传回执保存在任务记录中。

文档对尾帧存在表述差异：输入组合和模型介绍明确支持仅尾帧，role 字段注释却说需与首帧成对。本实现按明确列出的尾帧输入模式支持单独 last_frame，尚未以付费云端请求验证。

[H3-Context-IR](https://platform.minimax.cn/docs/api-reference/video-generation-v2-h3-context-ir)（工具 `create_h3_context_ir_task`，原名 `enhance_video_prompt`）使用 /v2/h3_context_ir，只返回增强提示词；请求不带 resolution。[再生成](https://platform.minimax.cn/docs/api-reference/video-generation-v2-regeneration)（工具 `regenerate_video`）使用 /v2/video_regeneration，不带 duration/ratio。允许 source_task_id 或含一个 base_video 的原始生成输入，二者互斥；前者需要白名单。接口概览只提 base_video，本实现以具体接口新增的两种输入规范为准。

## 故障与恢复

- 生成前持久保存任务并持有跨进程锁，付费 POST 不自动重试。
- 明确业务拒绝记录为 failed；网络异常、5xx 或缺 task_id 的提交结果记为 unknown。
- 有 task_id 的查询失败保留原ID，可继续查询；queued/running 不作为 MCP 错误。
- H3 下载失败通过原任务刷新 URL，再补下载；已完整落地的文件复用指纹验证。
- 无 task_id 的 unknown 不自动恢复生成。可核对云端任务列表，按找到的 task_id 接续。
- 云端查询窗口、视频输入文件有效期均为7天；同步媒体临时URL过期不保证可恢复。
- 运行域名变化时拒绝继续查询已有任务，避免把国内任务发给国际区；同域名切换账号仍由平台鉴权判断。

## 验证证据

Python 3.13：新增 15 项测试通过，包括真实 stdio 初始化、工具发现、参数错误、模拟提交/查询和 MCP is_error；共享契约/文档/stdio 的 38 项测试通过。模拟供应商响应不产生付费请求。wheel 与 sdist 独立构建成功。

官方来源映射、共享源码同步检查通过。CI 已加入独立依赖锁安装、MiniMax 测试和构建，Python 3.10/3.13 由已有矩阵运行；本次未触发远端 CI、未执行付费云端生成、未发布或替换用户当前 MCP 配置。
