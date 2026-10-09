# ali-bailian-mcp

调用阿里云百炼（DashScope）的 MCP server，结果直接存到本地：

| 工具 | 作用 | 默认模型 |
|---|---|---|
| `generate_image` | 生图和图片编辑 | `qwen-image-3.0-pro` |
| `chat` | 调用百炼上的语言模型（千问，以及托管的 DeepSeek、Kimi、GLM、MiniMax 等） | `qwen3.8-max` |
| `text_to_speech` | 语音合成，20 个系统音色，可用自然语言控制语气，长文本自动分段拼接 | `qwen3-tts-flash` / `qwen3-tts-instruct-flash` |
| `speech_to_text` | 语音识别（5 分钟 / 10MB 以内），返回文本、语种、情绪 | `qwen3-asr-flash` |
| `generate_video` / `query_video` | 视频生成：文生、首帧、首尾帧、多主体参考、续写，最长 30 秒，带音频 | `wan3.0-video` |
| `list_models` | 列出当前 API Key 能调用的模型 ID | — |

生图模型（`model` 写别名或完整 ID）：

| 别名 | 模型 | 特点 |
|---|---|---|
| `qwen`（默认） | `qwen-image-3.0-pro` | 文字渲染最强，文生图和编辑二合一 |
| `wan` | `wan2.7-image-pro` | 0–9 张参考图、1K / 2K / 4K、组图、thinking |
| `z` | `z-image-turbo` | 最快最便宜，写实人像和产品图，只支持文生图 |

也可以直接写 `qwen-image-2.0-pro`、`qwen-image-max`、`qwen-image-edit-max`、`wan2.7-image` 等其他 ID。

语言模型别名：`max` → `qwen3.8-max`（默认，能看图）、`plus` → `qwen3.7-plus`、`flash` → `qwen3.8-flash`；其他模型直接写 ID，如 `deepseek-v4-pro`、`kimi-k3`、`glm-5.3`。`chat` 统一走流式接口，支持多轮历史、看图、深度思考开关、JSON 输出和联网搜索。

视频是异步任务：`generate_video` 默认最多等 90 秒，没完成就返回 `task_id`，再用 `query_video` 继续等，避免撞上客户端的工具调用超时。视频的参考素材和本地文件会自动上传到百炼临时存储（48 小时有效）。

模型不支持的明显参数组合在本地直接报错，其余交给服务端校验。

## 环境变量

| 变量 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 必需，百炼控制台 → API Key（北京地域） |
| `BAILIAN_OUT_DIR` | 图片、音频、视频的输出目录，默认 `~/Downloads/ali-bailian` |
| `BAILIAN_RESOURCE_MODE` | 交付方式：`local`（默认）下载到本地，`url` 只返回 24 小时内有效的链接 |
| `DASHSCOPE_BASE_URL` | 默认 `https://dashscope.aliyuncs.com`；新加坡地域用 `https://dashscope-intl.aliyuncs.com`，key 不能跨地域混用 |

参数说明见工具描述（`src/ali_bailian_mcp/server.py`），接口细节以百炼的[文生图](https://help.aliyun.com/zh/model-studio/text-to-image)、[OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[千问 TTS](https://help.aliyun.com/zh/model-studio/qwen-tts-api)、[千问 ASR](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference) 和[万相 3.0 视频](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference)文档为准。

## 0.3 新增接入（未测试）

| 工具 | 能力 | 官方契约 |
|---|---|---|
| `clone_voice` | Qwen声音复刻，本地音频/URL → 固定音色 | [复刻HTTP API](https://help.aliyun.com/en/model-studio/voice-clone-design-http-api) |
| `design_voice` | 自然语言设计音色，返回音色和试听WAV | [设计API](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| `list_voices` / `get_voice` | 分页查询和查找自定义音色 | 同上；Qwen详情从分页列表中查找 |
| `edit_video` | HappyHorse指令编辑、风格和元素替换 | [视频编辑API](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `animate_portrait` | 人物图片 + 人声 → 数字人对口型 | [wan2.2-s2v](https://help.aliyun.com/zh/model-studio/wan-s2v-api) |
| `embed` | 文本、图像、视频向量化 | [向量化](https://help.aliyun.com/zh/model-studio/embedding)、[多模态API](https://help.aliyun.com/en/model-studio/multimodal-embedding-api-reference) |
| `rerank` | 候选文本相关性排序，保留原始索引 | [重排序API](https://help.aliyun.com/zh/model-studio/text-rerank-api) |
| `list_capabilities` | 本MCP支持工具、来源与接入边界 | 静态目录，不代表账号已开通 |
| `list_jobs` / `get_job` / `recover_job` | 本地任务记录、分段接续与补下载 | 本地机制，不依赖新的云服务 |

### 音色创建与使用

`clone_voice` 默认目标模型 `qwen3-tts-vc-2026-01-22`；`design_voice` 默认 `qwen3-tts-vd-2026-01-26`。

创建返回 `voice` 和 `target_model`，后续必须调用 `text_to_speech(text=..., voice=返回音色, model=返回目标模型)`。
默认flash系统音色模型不能用于这些定制音色。当前创建工具支持Qwen非实时VC/VD，音色列表也可查询CosyVoice/Qwen-Audio；后两者的合成接口不在此轮范围内。

Qwen没有独立的详情接口，`get_voice` 会从列表分页查找；达到 `max_pages` 只表示查找未完成，不表示音色不存在。

### 视频编辑和数字人

新增视频工具默认 `wait=0`，只提交并立刻留档；之后调用 `query_video(task_id=..., job_id=...)` 或 `recover_job(job_id=...)`。

HappyHorse编辑输入视频3–60秒，输出最多15秒。数字人音频须小于20秒、小于15MB，分辨率480P/720P，北京地域。
本地视频素材会上传百炼临时存储；参考图片在编辑接口中使用data URL。模型和地域权限需后续真实调用确认。

### 向量与重排序

- 文本：`embed(texts=[...], model="text-embedding-v4")`。
- 多模态：`embed(contents=[{"text":"猫"},{"image":"/absolute/cat.png"}], model="qwen3-vl-embedding")`。
- 向量不自动创建索引、数据库或知识库。
- `rerank` 默认 `qwen3.7-text-rerank`，走原生接口；`qwen3-rerank` 走 `/compatible-api/v1/reranks`。完整请求与响应保留接口差异。

### 任务恢复

`BAILIAN_JOB_DIR` 默认 `~/.local/share/ali-bailian-mcp/jobs`。任务记录使用独立UUID，生成请求前写入；默认产物目录也增加随机后缀，避免同秒调用碰撞。

- 图片：保存完整响应和逐项URL，再逐张交付；恢复只补下载。
- 视频：保存云端 `task_id`，重启后查询原任务，刷新结果URL；不重新提交生成。
- TTS：逐段保存文本、生成URL和文件；恢复跳过已合成段，只继续尚未提交的段，再拼接WAV。状态未知的段禁止自动重复合成。明确被拒绝的段可由显式恢复调用再次提交。
- 音色设计：先留档音色ID再交付试听；恢复只补试听交付，不再次创建音色。
- 工具调用超时且没有拿到ID，可通过 `list_jobs` 按时间、模型和摘要查找记录。

新增返回 `job_id`、`job_state`、`artifacts`、`request_id`。`job_state` 区分 `unknown` / `running` / `generated` / `partial` / `download_failed` / `failed` / `delivered`。
生成工具的 `ok=true` 表示全部交付；组图部分成功不再只因有一张图就返回成功。`get_job.ok` 仅表示记录读取成功。
`artifacts` 含文件、来源URL、逐项错误、字节数与SHA-256；合成WAV另含实际时长和采样率。

下载先写临时文件，检查非空和HTTP长度后原子替换；恢复用SHA-256跳过完整文件。校验下载完整性不等于检查视觉/听觉质量。
临时URL过期、没有拿到完整同步响应、存储故障造成的响应丢失，都可能无法恢复。
任务记录保留签名URL、生成响应及TTS文本；不保存API Key。`url`模式也写任务记录，音色试听若只有内联数据会保存本地文件。
分段文件和响应缓存是恢复所需资产，不自动清理。恢复锁使用POSIX `flock`，面向macOS/Linux。

本轮遵照用户要求未运行测试、未发起真实API请求、未更新本机已安装MCP；开发状态见 [接入记录](../../docs/mcp-expansion.md)。

产物的 `media_info` 读取PNG头中的实际宽高；若系统已有 `ffprobe`，可读取其他媒体的实际尺寸、时长和音轨信息。不可读取时显式返回 `available=false`，不把请求参数当作实际输出规格。无需新增Python依赖。
