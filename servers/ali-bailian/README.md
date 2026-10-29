<div align="center">

# ali-bailian-mcp

调用阿里云百炼（DashScope）的 MCP server，结果直接存到本地。

[![PyPI](https://img.shields.io/pypi/v/ali-bailian-mcp?style=flat-square)](https://pypi.org/project/ali-bailian-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE)

**简体中文** · [English](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/ali-bailian/README.en.md)

</div>

`0.7.2` 同步声音复刻地域范围：新加坡新增 `qwen-audio-3.1-tts-flash` 复刻目标模型；复核至 2026-10-29 的官方文档。

`0.7.1` 补充 Qwen-Audio-TTS 方言用法：支持方言指令的系统音色及复刻音色使用 `instructions="请讲上海话。"`（映射到官方 `input.instruction`）；设计音色暂不支持方言。复核至 2026-10-28 的官方文档；SDK 2.0 示例迁移不影响本 MCP 的 HTTP 请求。

`0.7.0` 新增复刻本地录音 / Base64 Data URI、`qwen-audio-3.1-tts-plus` 和百炼托管 MiniMax 的思考协议支持，更新 workspace 地域接入说明。TTS 用量保留原始单位，旧任务丢失单位的计量返回 `legacy_untyped`，不再猜测字符或 token。

`0.6.0` 适配官方 2026-10-10 模型下线：`clone_voice` / `design_voice` 改用 `voice-enrollment`，默认目标模型 `qwen-audio-3.0-tts-flash`；`text_to_speech` 新增 Qwen-Audio-TTS / CosyVoice 与 `instructions` 语气控制；`rerank` 统一走原生接口；`speech_to_text` 拒绝已下线的日期快照。旧的 qwen3-tts-vc/vd 音色已随模型下线，不能继续使用。

`0.5.0` 去掉 `query_video`：视频进度统一用 `get_job` 查询，完成时自动下载；生成类工具和 `chat`、`text_to_speech`、`speech_to_text` 新增 `parameters`。这是不兼容变更。

| 工具 | 作用 | 默认模型 |
|---|---|---|
| `generate_image` | 生图和图片编辑 | `qwen-image-3.0-pro` |
| `chat` | 调用百炼上的语言模型（千问，以及托管的 DeepSeek、Kimi、GLM、MiniMax 等） | `qwen3.8-max` |
| `text_to_speech` | 语音合成，长文本自动分段拼接；按模型名路由：`qwen3-tts-flash` 系统音色，Qwen-Audio-TTS / CosyVoice 支持自定义音色和 `instructions` 语气控制 | `qwen3-tts-flash` |
| `speech_to_text` | 语音识别（5 分钟 / 10MB 以内），返回文本、语种、情绪；已下线的日期快照本地拒绝 | `qwen3-asr-flash` |
| `generate_video` | 视频生成：文生、首帧、首尾帧、多主体参考、续写，最长 30 秒，带音频 | `wan3.0-video` |
| `list_models` | 列出百炼官方模型目录里的模型 ID，可按名称过滤 | — |
| `list_jobs` / `get_job` / `recover_job` | 查任务进度（视频生成中会查询百炼并在完成时下载）、补交付、TTS 续做 | 本地任务记录 |

生图模型（`model` 写别名或完整 ID）：

| 别名 | 模型 | 特点 |
|---|---|---|
| `qwen`（默认） | `qwen-image-3.0-pro` | 文字渲染最强，文生图和编辑二合一 |
| `wan` | `wan2.7-image-pro` | 0–9 张参考图、1K / 2K / 4K、组图、thinking |
| `z` | `z-image-turbo` | 最快最便宜，写实人像和产品图，只支持文生图 |

也可以直接写 `qwen-image-2.1`、`qwen-image-2.0-pro`、`wan2.7-image` 等其他 ID。`qwen-image`、`qwen-image-max`、`qwen-image-plus`、`qwen-image-edit` 系列已于 2026-10-10 下线。

语言模型别名：`max` → `qwen3.8-max`（默认，能看图）、`plus` → `qwen3.7-plus`、`flash` → `qwen3.8-flash`；其他模型直接写 ID，如 `deepseek-v4-pro`、`kimi-k3`、`glm-5.3`。`chat` 统一走流式接口，支持多轮历史、看图、深度思考开关、JSON 输出和联网搜索。

`kimi/kimi-k3.1-pro`、`kimi/kimi-k3.1-pro-highspeed` 为月之暗面直供模型，可直接传完整 ID。两者的 `reasoning_effort` 默认且仅支持 `max`，不支持 `n`、`parallel_tool_calls` 参数，应省略这些字段；`parameters={"reasoning_effort":"max","enable_thinking_history":true}` 可开启历史思考回传（默认关闭），并在 `history` 的 assistant 消息中保留 `reasoning_content`。`kimi/kimi-k3` 的思考深度同样默认且仅支持 `max`，不要与阿里云直供 `kimi-k3` 混用。工具不自动填入上述可选参数，扩展参数由服务端校验。参见 [Chat参数](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)。

`MiniMax/MiniMax-M3.1-Flash` 已于2026-10-21加入百炼：`thinking=true` 映射为官方 `thinking={"type":"adaptive"}`，`false` 本地拒绝；`reasoning_split` 固定为 `true`，仅支持 `n=1`。思考深度通过 `parameters={"reasoning_effort":"high"}` 设置（low/medium/high/xhigh/max，默认max）；`MiniMax/MiniMax-M3` 可关闭思考但不支持此深度参数。两者的 `temperature=1`、`top_p=0.95` 固定，其他值不会生效，不支持 `json_mode` 或 `web_search`。M3.1不支持 `stop`，`parallel_tool_calls=false` 不能保证串行，`tool_choice` 仅支持auto；本 `chat` 返回文本和思考，未实现完整 Function Calling 循环。思考与回答共同占用输出 token 上限。参见 [MiniMax直供接入](https://help.aliyun.com/zh/model-studio/minimax-api-by-minimax)。

千问联网搜索可通过 `parameters={"include_tool_usage":true}` 获取 `usage.x_tools.search.count/strategy`，返回统计原样保留；count 为搜索意图触发次数，不能用于费用对账。`deepseek-v4.1-flash-1017`、`xiaomi/mimo-v2.6-pro-ultraspeed` 等新增 ID 可显式传入，具体能力以官方模型页与账号权限为准。

视频是异步任务：`generate_video` 默认 `wait=0`，提交后返回 `task_id`、`job_id`；之后 `get_job(job_id=...)` 查进度，默认单次查询，需要短轮询可指定 `wait`，最多 90 秒。视频模型默认 `wan`（`wan3.0-video`），`wan-fast` 对应 `wan3.0-video-prime`，能力相同、速度更快。视频的参考素材和本地文件会自动上传到百炼临时存储（48 小时有效）。

模型不支持的明显参数组合在本地直接报错，其余交给服务端校验。

`parameters` 放工具没单独列出的官方字段，深度合并：原生接口（生图、视频、`qwen3-tts-flash`）合并进官方请求的 `parameters` 对象，Qwen-Audio-TTS / CosyVoice 合并进官方 `input` 对象，OpenAI 兼容接口（`chat`、`speech_to_text`）合并进请求体顶层。

## 安装

```bash
uv tool install ali-bailian-mcp
```

命令装在 `~/.local/bin/ali-bailian-mcp`。各客户端的配置方法见 [仓库 README](https://github.com/hoobnn/hoobnn-mcps#配置客户端)。

## 环境变量

| 变量 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 必需，百炼控制台对应地域的 API Key，与业务空间地域一致 |
| `BAILIAN_OUT_DIR` | 图片、音频、视频的输出目录，默认 `~/Downloads/ali-bailian` |
| `BAILIAN_RESOURCE_MODE` | 交付方式：`local`（默认）下载到本地，`url` 只返回 24 小时内有效的链接 |
| `BAILIAN_JOB_DIR` | 任务记录目录，默认 `~/.local/share/ali-bailian-mcp/jobs` |
| `DASHSCOPE_BASE_URL` | 默认 `https://dashscope.aliyuncs.com`（存量兼容）；推荐设置下表对应地域的 workspace 根域名，不能带 `/api/v1` 等路径 |

参数说明见工具描述（`src/ali_bailian_mcp/server.py`），接口细节以百炼的[文生图](https://help.aliyun.com/zh/model-studio/text-to-image)、[OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[千问 TTS](https://help.aliyun.com/zh/model-studio/qwen-tts-api)、[Qwen-Audio-TTS](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[CosyVoice](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)、[千问 ASR](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference) 和[万相 3.0 视频](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference)文档为准。

## 接入域名与地域

设置 `DASHSCOPE_BASE_URL` 为真实业务空间的**根域名**：北京 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`；新加坡 `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com`；HappyHorse 美国示例使用 `https://{WorkspaceId}.us-east-1.maas.aliyuncs.com`。将占位符替换为对应地域的业务空间 ID，并使用同地域 API Key。不要附加 `/api/v1` 或 `/compatible-mode/v1`，MCP 会按工具追加路径。

| 产品 / 当前协议 | 北京 | 新加坡 | 其他地域与边界 |
|---|---|---|---|
| Qwen-Audio-TTS，HTTP SpeechSynthesizer | 3.1-plus/flash、3.0-plus/flash | 3.1-plus/flash、3.0-plus/flash | 模型名均带 `qwen-audio-…-tts-…`；目录存在不等于账号授权 |
| CosyVoice，HTTP SpeechSynthesizer | 已接入的 v3.5 / v3 / v2 | 官方 HTTP 页未列出 | 新加坡的实时合成支持不代表 HTTP 合成支持 |
| voice-enrollment 声音复刻 | 当前白名单全部模型 | Qwen-Audio 3.1-plus、3.0-plus/flash；CosyVoice v3-plus/flash | 复刻接口可用不代表该地域可用本 MCP 的 HTTP 合成 |
| voice-enrollment 声音设计 | 当前白名单全部模型 | 未列出 | 设计音色绑定创建时的模型 |
| HappyHorse 视频编辑 | 以产品 API 为准 | 以产品 API 为准 | 美国文档已改为 workspace 域名；地域、部署范围与账号权限仍需匹配 |

Qwen-Audio-TTS / CosyVoice 的「模型接入方式」页介绍 **AOQ / WebSocket 实时协议**，本 MCP 当前实现上述 **HTTP 非实时协议**，不能只替换模型名就调用实时产品。参见 [地域与接入域名](https://help.aliyun.com/zh/model-studio/regions)、[Qwen-Audio-TTS HTTP](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[CosyVoice HTTP](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)、[实时接入方式](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-model-access)。官方说明旧 DashScope 域名自2026-09-30起不再支持新特性，因此新增功能建议使用 workspace 域名。

## 0.3 新增接入

| 工具 | 能力 | 官方契约 |
|---|---|---|
| `clone_voice` | 从本地录音、公开 URL 或 Base64 Data URI 复刻音色（voice-enrollment） | [复刻 HTTP API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api) |
| `design_voice` | 按文字描述设计音色并保存试听（voice-enrollment） | [设计 API](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| `list_voices` / `get_voice` | 分页列出 / 查询 voice-enrollment 自定义音色及审核状态 | 同上 |
| `edit_video` | HappyHorse 指令编辑、风格和元素替换 | [视频编辑 API](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `animate_portrait` | 人物图片 + 人声 → 数字人对口型 | [wan2.2-s2v](https://help.aliyun.com/zh/model-studio/wan-s2v-api) |
| `embed` | 文本、图像、视频向量化 | [向量化](https://help.aliyun.com/zh/model-studio/embedding)、[多模态 API](https://help.aliyun.com/en/model-studio/multimodal-embedding-api-reference) |
| `rerank` | 候选文本相关性排序，保留原始索引 | [重排序 API](https://help.aliyun.com/zh/model-studio/text-rerank-api) |
| `list_capabilities` | 本 MCP 支持工具、来源与接入边界 | 静态目录，不代表账号已开通 |
| `list_jobs` / `get_job` / `recover_job` | 本地任务记录、分段接续与补下载 | 本地机制，不依赖新的云服务 |

### 音色创建与使用

百炼已于 2026-10-10 下线 `qwen-voice-design`、`qwen3-tts-vc-*`、`qwen3-tts-vd-*` 和 `qwen3-tts-instruct-flash`。现在 `clone_voice`、`design_voice` 改走官方现行的 `voice-enrollment`（`action=create_voice`），创建音色免费：

1. 创建：`clone_voice(audio="https://…/sample.wav", prefix="me")` 或 `design_voice(voice_prompt=…, preview_text=…, prefix="me")`。默认 `target_model=qwen-audio-3.0-tts-flash`，也可选其他 Qwen-Audio-TTS / CosyVoice 模型；音色只能用于创建时的模型。
2. 等审核：`get_voice(voice=…)` 的 `status` 为 `OK` 后可用（`DEPLOYING` 审核中，`UNDEPLOYED` 未通过）。
3. 合成：`text_to_speech(text=…, voice=音色ID, instructions="用温柔的语气")`。不传 `model` 时按音色 ID 前缀自动选回 target_model，走 SpeechSynthesizer 协议。

复刻的 `audio` 接受本地 WAV/MP3/M4A（≤10MB）、公网 http/https URL 或 Base64 Data URI；本地文件直接编码为 Data URI，统一发送官方 `input.audio`，不经过临时上传。旧 `url` 别名只接受公网 URL，不能与 `audio` 同时传入；官方 `input.url` 仍兼容但将逐步废弃。本 MCP 仍拒绝未经官方确认的 `oss://`。音频应满足 ≥16kHz、推荐10–20秒、最长60秒及至少5秒清晰朗读；远程文件规格和音色效果由服务端校验。响应缺少音色 ID 时不会自动重建，用 `list_voices(prefix=…)` 核对。

`list_voices` / `get_voice` 统一走 voice-enrollment 的 `list_voice` / `query_voice`；复刻和设计音色在同一列表，`kind` 旧值 `clone` / `design` / `cosyvoice` 仍可传，均等价于 `enrollment`。已下线的 Qwen 复刻 / 设计音色不能再用于合成。合成、复刻与设计的地域范围不同，见下方接入表。`qwen-audio-3.1-tts-plus` 已支持这三类工具，显式传 ID 即可；原 `audio` / `audio-plus` 别名及默认模型保持不变。


`instructions` 发送为官方 `instruction`：仅 CosyVoice 应用100字符上限（汉字计2），Qwen-Audio-TTS 当前官方未公布同一上限，交服务端校验；CosyVoice v2 不支持指令，v3系统音色须使用官方固定指令，v3-plus自定义音色不支持指令。

### 视频编辑和数字人

新增视频工具默认 `wait=0`，只提交并立刻留档；之后用 `get_job(job_id=...)` 查进度，下载失败用 `recover_job(job_id=...)`。

HappyHorse 编辑输入视频 3–60 秒，输出最多 15 秒。数字人音频须小于 20 秒、小于 15MB，分辨率 480P / 720P，北京地域。本地视频素材会上传百炼临时存储（官方临时上传仅支持北京、新加坡地域，美国 workspace 请改用公网 URL）；参考图片在编辑接口中使用 data URL。模型和地域权限需后续真实调用确认。

### 向量与重排序

- 文本向量化：`embed(texts=[...], model="text-embedding-v4")`。
- 多模态向量化：`embed(contents=[{"text":"猫"},{"image":"/absolute/cat.png"}], model="qwen3-vl-embedding")`。
- 向量不自动创建索引、数据库或知识库。
- `rerank` 默认 `qwen3.7-text-rerank`；所有模型（含 `qwen3-rerank`）统一走原生 `/api/v1/services/rerank/text-rerank/text-rerank`。

### 任务恢复

`BAILIAN_JOB_DIR` 默认 `~/.local/share/ali-bailian-mcp/jobs`。任务记录使用独立 UUID，生成请求前写入；默认产物目录也增加随机后缀，避免同秒调用碰撞。

- 图片保存完整响应和逐项 URL，再有限并发交付；恢复只补下载。
- 视频保存云端 `task_id`，重启后查询原任务，刷新结果 URL；不重新提交生成。
- TTS 逐段保存文本、生成 URL 和文件；恢复跳过已合成段，只继续尚未提交的段，再拼接 WAV。状态未知的段禁止自动重复合成。明确被拒绝的段可由显式恢复调用再次提交。
- TTS用量保留官方characters、input_tokens、output_tokens、total_tokens等字段，按同名单位累加；旧任务已丢单位的标量保存为legacy_untyped，不混入新计量，也不据此估算账单。
- 音色设计先留档音色 ID 再交付试听；恢复只补试听交付，不再次创建音色。
- 工具调用超时且没有拿到 ID，可通过 `list_jobs` 按时间、模型和摘要查找记录。

新增返回 `job_id`、`job_state`、`artifacts`、`request_id`。`job_state` 区分 `unknown` / `running` / `generated` / `partial` / `download_failed` / `failed` / `delivered`。

`ok` 表示本次调用成功；已提交或运行中返回 `ok=true, completed=false`，全部交付返回 `completed=true`。组图部分失败使用 MCP `isError=true`，并保留成功产物。`get_job.ok` 仅表示记录读取成功。`artifacts` 含文件、来源 URL、逐项错误、字节数与 SHA-256；合成 WAV 另含实际时长和采样率。

下载先写临时文件，检查非空和 HTTP 长度后原子替换；恢复用 SHA-256 跳过完整文件。校验下载完整性不等于检查视觉 / 听觉质量。临时 URL 过期、没有拿到完整同步响应、存储故障造成的响应丢失，都可能无法恢复。

任务记录保留签名 URL、生成响应及 TTS 文本；不保存 API Key。`url` 模式也写任务记录，音色试听若只有内联数据会保存本地文件。分段文件和响应缓存是恢复所需资产，不自动清理。恢复锁使用 POSIX `flock`，面向 macOS / Linux。

已通过离线故障测试与真实 stdio 检查；2026-10-13 用北京地域账号对全部工具做了小样本云端验证（结果见稳定性记录）。历史接入范围见 [接入记录](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-expansion.md)，本轮验证见 [稳定性记录](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md)。

产物的 `media_info` 读取 PNG 头中的实际宽高；若系统已有 `ffprobe`，可读取其他媒体的实际尺寸、时长和音轨信息。不可读取时显式返回 `available=false`，不把请求参数当作实际输出规格。无需新增 Python 依赖。

## 运行时与稳定性

共享连接池、总超时、工具分组、错误语义和迁移说明见 [MCP 构建与稳定性](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md)。完整工具说明可调用 `get_tool_help(tool="工具名")`。

## 官方契约与最新文档

2026-10-10 完成全部工具和默认模型的官方对照；详见 [百炼审计](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/audits/ali-bailian.md)。`list_models` 现在查询原生 `/api/v1/models` 全模态分页目录，返回 `complete` 与官方元数据；目录存在不等于账号授权。北京建议将 `DASHSCOPE_BASE_URL` 设置为真实 workspace 根域名。Wan3 支持 `link` 网页参考，不能与 `file` 同用，也不能与首尾帧混用。ASR 工具只放行 `qwen3-asr-flash`（日期快照已于 2026-10-10 下线，本地拒绝），Fun-ASR、filetrans 和 realtime 需要独立协议。2026-10-13 完成语音迁移，见审计报告「2026-10-13 语音迁移」。

## 许可证

[MIT](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE) © 2026 hoobnn。可自由使用、修改和分发，需保留版权声明。
