<div align="center">

# ali-bailian-mcp

调用阿里云百炼（DashScope）的 MCP server，结果直接存到本地。

[![PyPI](https://img.shields.io/pypi/v/ali-bailian-mcp?style=flat-square)](https://pypi.org/project/ali-bailian-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE)

**简体中文** · [English](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/ali-bailian/README.en.md)

</div>

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
| `DASHSCOPE_API_KEY` | 必需，百炼控制台 › API Key（北京地域） |
| `BAILIAN_OUT_DIR` | 图片、音频、视频的输出目录，默认 `~/Downloads/ali-bailian` |
| `BAILIAN_RESOURCE_MODE` | 交付方式：`local`（默认）下载到本地，`url` 只返回 24 小时内有效的链接 |
| `BAILIAN_JOB_DIR` | 任务记录目录，默认 `~/.local/share/ali-bailian-mcp/jobs` |
| `DASHSCOPE_BASE_URL` | 默认 `https://dashscope.aliyuncs.com`；新加坡地域用 `https://dashscope-intl.aliyuncs.com`，key 不能跨地域混用 |

参数说明见工具描述（`src/ali_bailian_mcp/server.py`），接口细节以百炼的[文生图](https://help.aliyun.com/zh/model-studio/text-to-image)、[OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[千问 TTS](https://help.aliyun.com/zh/model-studio/qwen-tts-api)、[Qwen-Audio-TTS](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[CosyVoice](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)、[千问 ASR](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference) 和[万相 3.0 视频](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference)文档为准。

## 0.3 新增接入（待云端验证）

| 工具 | 能力 | 官方契约 |
|---|---|---|
| `clone_voice` | 从公网录音 URL 复刻音色（voice-enrollment） | [复刻 HTTP API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api) |
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

复刻只接受公网 http/https 音频 URL：官方要求「公网可访问」，且未说明 voice-enrollment 接受百炼临时上传的 `oss://` 地址（临时文件私有、与调用模型绑定），所以本地文件、data URL、`oss://` 一律本地拒绝，不自动上传。响应缺少音色 ID 时不会自动重建，用 `list_voices(prefix=…)` 核对。

`list_voices` / `get_voice` 统一走 voice-enrollment 的 `list_voice` / `query_voice`；复刻和设计音色在同一列表，`kind` 旧值 `clone` / `design` / `cosyvoice` 仍可传，均等价于 `enrollment`。已下线的 Qwen 复刻 / 设计音色不能再用于合成。Qwen-Audio-TTS / CosyVoice 与 voice-enrollment 的完整能力仅在北京地域。

### 视频编辑和数字人

新增视频工具默认 `wait=0`，只提交并立刻留档；之后用 `get_job(job_id=...)` 查进度，下载失败用 `recover_job(job_id=...)`。

HappyHorse 编辑输入视频 3–60 秒，输出最多 15 秒。数字人音频须小于 20 秒、小于 15MB，分辨率 480P / 720P，北京地域。本地视频素材会上传百炼临时存储；参考图片在编辑接口中使用 data URL。模型和地域权限需后续真实调用确认。

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
- 音色设计先留档音色 ID 再交付试听；恢复只补试听交付，不再次创建音色。
- 工具调用超时且没有拿到 ID，可通过 `list_jobs` 按时间、模型和摘要查找记录。

新增返回 `job_id`、`job_state`、`artifacts`、`request_id`。`job_state` 区分 `unknown` / `running` / `generated` / `partial` / `download_failed` / `failed` / `delivered`。

`ok` 表示本次调用成功；已提交或运行中返回 `ok=true, completed=false`，全部交付返回 `completed=true`。组图部分失败使用 MCP `isError=true`，并保留成功产物。`get_job.ok` 仅表示记录读取成功。`artifacts` 含文件、来源 URL、逐项错误、字节数与 SHA-256；合成 WAV 另含实际时长和采样率。

下载先写临时文件，检查非空和 HTTP 长度后原子替换；恢复用 SHA-256 跳过完整文件。校验下载完整性不等于检查视觉 / 听觉质量。临时 URL 过期、没有拿到完整同步响应、存储故障造成的响应丢失，都可能无法恢复。

任务记录保留签名 URL、生成响应及 TTS 文本；不保存 API Key。`url` 模式也写任务记录，音色试听若只有内联数据会保存本地文件。分段文件和响应缓存是恢复所需资产，不自动清理。恢复锁使用 POSIX `flock`，面向 macOS / Linux。

已通过离线故障测试与真实 stdio 检查；未发起云端付费生成，新增产品仍待云端验证。历史接入范围见 [接入记录](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-expansion.md)，本轮验证见 [稳定性记录](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md)。

产物的 `media_info` 读取 PNG 头中的实际宽高；若系统已有 `ffprobe`，可读取其他媒体的实际尺寸、时长和音轨信息。不可读取时显式返回 `available=false`，不把请求参数当作实际输出规格。无需新增 Python 依赖。

## 运行时与稳定性

共享连接池、总超时、工具分组、错误语义和迁移说明见 [MCP 构建与稳定性](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md)。完整工具说明可调用 `get_tool_help(tool="工具名")`。

## 官方契约与最新文档

2026-10-10 完成全部工具和默认模型的官方对照；详见 [百炼审计](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/audits/ali-bailian.md)。`list_models` 现在查询原生 `/api/v1/models` 全模态分页目录，返回 `complete` 与官方元数据；目录存在不等于账号授权。北京建议将 `DASHSCOPE_BASE_URL` 设置为真实 workspace 根域名。Wan3 支持 `link` 网页参考，不能与 `file` 同用，也不能与首尾帧混用。ASR 工具只放行 `qwen3-asr-flash`（日期快照已于 2026-10-10 下线，本地拒绝），Fun-ASR、filetrans 和 realtime 需要独立协议。2026-10-13 完成语音迁移，见审计报告「2026-10-13 语音迁移」。

## 许可证

[MIT](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE) © 2026 hoobnn。可自由使用、修改和分发，需保留版权声明。
