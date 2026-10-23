# 百炼 MCP 官方契约审计

审计日期：2026-10-10。范围为 `servers/ali-bailian` 全部 20 个工具（包含共享运行时自动注册的 `get_tool_help`）。验证方式为官方正文读取、实现逐项比对和不含付费请求的合同回归测试。模型存在、协议一致、账号有权限、真实生成成功是四个不同结论；本轮只确认前两项。

## 结论与已修正差异

核心 endpoint 和默认模型均有官方来源，未发现需要删除的默认模型。当前推荐目录已经出现 Qwen-Image 2.1、Qwen-Audio 3.x、HappyHorse 1.1 等新系列；这些不是现有接口的通用替换模型，不能只改 `model` 字符串就声称支持。保留当前默认 ID，公开可传模型需遵守对应协议。

本轮已修正：

1. `list_models` 改为官方 `GET /api/v1/models`，逐页读取 `output.models[].model`，保留模型能力、等价快照、上下文和定价原始字段；提供 `complete`，达到页数上限或重复页不再伪装完整。结果明确 `account_verified=false`。此前“当前 API Key 能调用、视频不在其中”的描述不成立。账号权限另有 [`/api/v1/models/permissions`](https://help.aliyun.com/zh/model-studio/list-model-permissions)，本轮没有调用。
2. `speech_to_text` 明确仅接入 `qwen3-asr-flash` 及其非实时快照，阻止 `filetrans`、`realtime`、Fun-ASR 被误送 OpenAI Chat 接口；原描述宣称支持 Fun-ASR，缺少对应协议实现。
3. Wan3 新增公开网页 `link` 参考；补齐首尾帧与参考素材互斥、`file/link` 二选一、文档/网页必须开启智能改写、素材数量及输出参数范围检查；音频/文件/网页单独输入可正常构建请求，不再误判必须有文字或图片。
4. 声音设计 `preview_text` 补齐 1024 字符上限。图像补齐 Qwen 3.0 的 3 张参考图、Qwen 2.1 的 10 张参考图、Z-Image/旧 Qwen 固定 1 张、Wan2.7 非组图 1–4 张和 4K 仅 Pro 无参考非组图限制。

## 2026-10-13 上游文档复核（PR #3）

自动检查报告 27/27 来源正文变化。逐个阅读 diff，并读取官方 `.md` 正文与 2026-10-10 下线公告（[118177](https://www.aliyun.com/notice/118177)、[118331](https://www.aliyun.com/notice/118331)、[118332](https://www.aliyun.com/notice/118332)、[118344](https://www.aliyun.com/notice/118344)、[118345](https://www.aliyun.com/notice/118345)、[118434](https://www.aliyun.com/notice/118434)）核对后，结论如下。全部来源新增 `og:title` 元数据行，这是抓取正文的模板变化，不属于契约变化。

实质变化，已改实现：

| 来源 | 变化 | 处理 |
| --- | --- | --- |
| `bailian-rerank` | 删除 `compatible-api/v1/reranks`，`qwen3-rerank` 改走原生接口、`input/parameters` 嵌套、返回 `output.results` | `rerank` 全部模型走原生接口，补回归测试 |
| `bailian-tts` / `bailian-tts-models` | 删除 `instructions/optimize_instructions`；Qwen3-TTS 只剩 `qwen3-tts-flash`（及 realtime）；instruct/VC/VD 按公告 118434 于 2026-10-10 下线 | 去掉 `instruct` 别名，传 `instructions` 本地拒绝；默认 `qwen3-tts-flash` 仍有效 |
| `bailian-voice-clone` / `bailian-voice-design` | 删除 `qwen-voice-enrollment`、`qwen-voice-design` 全部字段；`qwen-voice-design` 按公告 118331 下线；复刻 / 设计只剩 `voice-enrollment` + Qwen-Audio-TTS/CosyVoice | `clone_voice`、`design_voice` 本地直接返回下线错误，不发请求；替代协议待接入 |
| `bailian-qwen-image-legacy` | 正文只剩 Qwen-Image 2.0；`qwen-image`、`qwen-image-max/plus`、`qwen-image-edit*` 按公告 118434 下线 | 删除旧 max/plus 专属本地校验与说明；默认 `qwen-image-3.0-pro` 不受影响 |

无实质变化，仅记录：

| 来源 | 复核结论 |
| --- | --- |
| `bailian-upload` | 只把示例模型 `qwen-vl-plus` 换成 `qwen3-vl-plus`（前者按公告 118177 下线）；`upload()` 用调用方实际目标模型请求 getPolicy，未写死模型，不受影响 |
| `bailian-asr` | 仅 `og:title` |
| `bailian-asr-models` | 新增 Qwen-Audio-ASR 系列章节；`qwen3-asr-flash` 仍在模型表，HTTP 协议未变；其日期快照按公告 118434 下线（推荐 fun-asr）。说明已改，代码不变 |
| `bailian-chat` | 请求参数未变；仅从适用模型列表删除已下线模型（qwen-vl-max/plus、qwen3-max、qwen-turbo 等），新增 Qwen3.8 思考说明和 `n=0` 等价 `n=1`。默认 `qwen3.8-max/qwen3.7-plus/qwen3.8-flash` 仍列出 |
| `bailian-chat-models` | 删除已下线模型、新增 MiniMax-M2.5/M2.7/M3，只作记录；默认三个 ID 仍列出 |
| `bailian-vision-models` | 删除 qwen3-vl-flash、qwen-vl-max/plus 等已下线模型；`qwen3-vl-plus` 保留 |
| `bailian-catalog` / `bailian-permissions` | 只换示例模型（`qwen3-max→qwen3.8-max`、`qwen-image-max→qwen-image-3.0-pro`），查询参数和响应结构未变 |
| `bailian-model-directory` / `bailian-model-lifecycle` / `bailian-model-pricing` / `bailian-rate-limit` | 目录、价格和限流表随下线与新增（MiniMax、music、speech-2.8 等）改版；新增模型仅记录，未接入 |
| `bailian-qwen-image`、`bailian-wan-image`、`bailian-z-image`、`bailian-wan-video`、`bailian-wan-s2v`、`bailian-happyhorse-edit`、`bailian-embedding`、`bailian-multimodal-embedding`、`bailian-video-models` | 仅 `og:title`，参数、限制和 endpoint 未变 |

待人工决策：是否把 `clone_voice`、`design_voice`、`text_to_speech` 迁移到官方现行的 `voice-enrollment`（`action=create_voice`，复刻需公网 `url` + `prefix`）与 `/api/v1/services/audio/tts/SpeechSynthesizer`（Qwen-Audio-TTS / CosyVoice，支持 `instruction`）。这需要新增合成协议、默认模型和来源登记，本轮未实现。已在下一节「2026-10-13 语音迁移」完成。

## 2026-10-13 语音迁移

依据官方正文（`.md` 导出，2026-10-13 读取）：[声音复刻 HTTP API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[声音设计 API](https://help.aliyun.com/zh/model-studio/voice-design-api-references)、[Qwen-Audio-TTS HTTP API](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[CosyVoice HTTP API](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)、[非实时语音合成指南](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)、[声音复刻指南](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)、[声音设计指南](https://help.aliyun.com/zh/model-studio/voice-design-user-guide)、[语音合成模型表](https://help.aliyun.com/zh/model-studio/tts-model)、[ASR 模型表](https://help.aliyun.com/zh/model-studio/asr-model)、[临时文件上传](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)。新增 5 个来源已登记并单独写入基线。

**默认目标模型：`qwen-audio-3.0-tts-flash`**（复刻与设计共用）。理由：

- 模型表中它同时支持 HTTP、声音复刻、声音设计和指令控制，属于现行推荐模型；`tts-model` 的迁移表把它列为「自定义音色 / 声音复刻」推荐，复刻指南的 HTTP 示例也用它。
- 复刻指南「支持的模型与地域」中，它在北京和新加坡都可用；`cosyvoice-v3.5-*` 没有系统音色、v3-plus 自定义音色不支持指令，`qwen-audio-3.1-tts-flash` 不在新加坡列表。
- 计费按字符（3.1-flash 按 token），与原 `qwen3-tts-flash` 的分段/计量逻辑一致。

| 工具 | 新实现 | 官方依据与本地约束 |
| --- | --- | --- |
| `clone_voice` | POST customization，`model=voice-enrollment`，`input={action:create_voice,target_model,prefix,url}`，可选 `language_hints`、`enable_preprocess`、`max_prompt_audio_length` | `target_model` 限 HTTP 可合成的 Qwen-Audio-TTS 3 个 + CosyVoice 5 个；`prefix` 仅字母数字 ≤10；`language_hints` / 预处理 / 时长参数按正文列出的模型白名单校验，时长 3–30 秒。响应缺 `voice_id` 时返回失败，不自动重建 |
| `clone_voice` 本地文件 | **明确拒绝**，不上传 | 复刻正文要求 `url`「公网可访问」；临时上传正文说明 `oss://` 为私有文件，须同模型调用并带 `X-DashScope-OssResourceResolve`，示例只覆盖 VL/omni，未列 voice-enrollment。官方未允许即不复用 `upload()`；data URL、`oss://` 同样拒绝 |
| `design_voice` | 同一路径，`input={action:create_voice,target_model,voice_prompt,preview_text,prefix}`，`parameters={sample_rate,response_format}` | `voice_prompt` ≤500、`preview_text` 15–200、`language_hints` 仅 zh/en、采样率 16000/24000/48000、格式 pcm/wav/mp3；目标模型不含 cosyvoice-v2。沿用 `voice_preview` 任务：先落 `voice_id` 与响应，再交付 `preview_audio.data`（扩展名随 `response_format`），`recover_job` 只补交付不重建；明确 4xx/业务错误记 failed，其余记 unknown |
| `text_to_speech` | 模型属于 Qwen-Audio-TTS（`qwen-audio-3.0-tts-plus`、`qwen-audio-3.1-tts-flash`、`qwen-audio-3.0-tts-flash`）或 CosyVoice（`cosyvoice-v3.5-plus/-flash`、`v3-plus`、`v3-flash`、`v2`）时 POST `/api/v1/services/audio/tts/SpeechSynthesizer`，`input={text,voice,format:wav,sample_rate:24000,instruction?,language_hints?}`，读取 `output.audio.url` | 正文所有合成参数都在 `input` 内，故 `parameters` 合并进 `input`，禁止覆盖 text/voice/model，local 交付 format 只能 wav（需拼接）。`instructions` 映射官方 `instruction`：≤100 字符（汉字计 2），cosyvoice-v2 本地拒绝；v3-plus 自定义音色、v3 系统音色固定格式交服务端校验。未传 `model` 时按自定义音色 ID 前缀 `{target_model}-` 推断，否则仍是 `qwen3-tts-flash` + Cherry，原 multimodal-generation 路径与请求体不变。别名 `audio`、`audio-plus`、`cosyvoice`。分段、落盘、job 与恢复沿用 |
| `list_voices` / `get_voice` | 统一 `voice-enrollment` 的 `list_voice`（`page_index/page_size/prefix`）与 `query_voice`（`voice_id`），返回 `status`、`target_model` | **kind 旧值映射到新接口**（`clone/design/cosyvoice` 均等价 `enrollment`）：复刻与设计音色官方共用同一列表和详情接口，旧 `qwen-voice-enrollment/qwen-voice-design` 已下线，按旧模型分开查询已无意义；映射保留旧调用不报错，旧 Qwen 音色无法再合成在说明中写明。`get_voice` 的 `max_pages` 只为兼容保留 |
| `speech_to_text` | 只放行 `qwen3-asr-flash` | `asr-model` 现行表只列 `qwen3-asr-flash`（HTTP）及 filetrans/realtime；`qwen3-asr-flash-YYYY-MM-DD[-us]` 日期快照按公告 118434 下线，本地返回下线错误；其他变体（含 `qwen3-asr-flash-us`）因现行正文未列出也拒绝 |

未能用官方正文确认、需人工判断：

1. SpeechSynthesizer 正文未写单次文本上限，继续沿用 250 字本地分段（保守策略，不是官方保证）。
2. 公告 118434 正文为前端渲染，本次无法抓取原文，ASR 快照列表取自上一轮复核记录与 `newly-released-models` 中出现过的 ID（`qwen3-asr-flash-2025-09-08`、`-2025-09-08-us`、`-2026-02-10`）；`qwen3-asr-flash-us` 是否仍可用未确认，当前按现行正文未列出而拒绝。
3. voice-enrollment 是否实际接受 `oss://` 临时地址未实测；若官方后续明示支持，可改为复用 `upload(src, "voice-enrollment")`。
4. 正文与端点示例均为北京 workspace 域名；新加坡仅部分模型可用（见复刻指南），默认 `DASHSCOPE_BASE_URL` 下的实际可用性未做付费验证。
5. 本次抓取发现 `bailian-happyhorse-edit` 正文新增美国 workspace 端点、删除 `dashscope-us` 示例，与语音迁移无关，未写入基线，留给下一次上游检查 PR 处理。

## 2026-10-23 上游更新落实（PR #14，待人工复查）

本轮对照最新官方 `.md` 正文与 PR #14 原捕获基线，抓取 **36/36 成功、19 项来源变化、0 失败**。原有32个来源对照主分支10月13日基线时有16篇正文变化；PR原基线已包含HappyHorse域名变化，因此两份差异数量不同。新增4个监控来源：[地域与接入域名](https://help.aliyun.com/zh/model-studio/regions)、[Qwen-Audio-TTS接入方式](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-model-access)、[CosyVoice接入方式](https://help.aliyun.com/zh/model-studio/cosyvoice-model-access)、[MiniMax直供接入](https://help.aliyun.com/zh/model-studio/minimax-api-by-minimax)。保留既有review目录，本轮捕获通过平台独立 `upstream_pr.stage` 写入待审基线、完整diff及内容寻址快照；尚未合并或发布。

| 实质变化 | 实现及验证边界 | 官方依据 |
|---|---|---|
| 复刻创建/更新新增 `input.audio`，支持公网URL或Base64 Data URI，旧 `url` 逐步废弃但仍兼容 | `clone_voice` 的现有 `audio` 参数保留，增加互斥的旧 `url` 别名；所有请求统一发送 `input.audio`。本地WAV/MP3/M4A直接编码，不调用模型绑定的临时上传；校验格式、非空和10MB大小，Base64校验解码后大小。远程时长/采样率及声音质量仍由云端校验。`oss://`仍无官方支持证据；不增加云端重试 | [复刻HTTP API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[复刻指南](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide) |
| 新增 `qwen-audio-3.1-tts-plus` 的合成、复刻、设计支持；Qwen复刻各模型现明确相同的16种language_hints取值 | 加入TTS协议路由、指令支持、复刻/设计目标及自定义音色前缀识别；旧默认模型与别名保持不变。新plus按字符计费；官方API同时列出token计量字段，不把这些字段推定为计费单位 | [TTS模型表](https://help.aliyun.com/zh/model-studio/tts-model)、[Qwen-Audio-TTS HTTP](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[设计指南](https://help.aliyun.com/zh/model-studio/voice-design-user-guide) |
| Qwen-Audio-TTS HTTP新增新加坡workspace端点；CosyVoice HTTP与设计仍只列北京；HappyHorse美国示例改为workspace域名 | 原 `DASHSCOPE_BASE_URL` 已可配置根域名，无需改变路径。中英README与工具帮助改为按产品、协议及地域说明；音色复刻在新加坡可用不代表本MCP的HTTP合成可用。地域指南明确旧DashScope域名自2026-09-30起不再接收新特性；默认旧域名仅保留存量兼容 | [地域指南](https://help.aliyun.com/zh/model-studio/regions)、[Qwen-Audio-TTS HTTP](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[CosyVoice HTTP](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)、[HappyHorse](https://help.aliyun.com/zh/model-studio/happyhorse-video-edit-api-reference) |
| 非实时合成指南将100字符instruction限制明确归入CosyVoice，而非全部Qwen-Audio-TTS | 本地只对CosyVoice应用100字符加权限制（汉字计2），同样检查 `parameters.instruction`；Qwen-Audio-TTS未公布同一上限，交服务端校验，不宣称无限制 | [非实时合成指令控制](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide#nrt_instruct_h3) |
| 10月21日新增MiniMax/MiniMax-M3.1-Flash；新旧M3思考控制存在协议差异 | `thinking`便利布尔按MiniMax官方对象映射，禁止误发 `enable_thinking`。M3支持adaptive/disabled；M3.1始终adaptive、`reasoning_split=true`、`n=1`，禁用思考/非法深度本地拒绝。五档 `reasoning_effort` 仅M3.1支持；两者不支持 `thinking_budget`、JSON结构化输出和联网搜索，相关便利参数本地拒绝。temperature=1、top_p=0.95固定，由官方忽略其他值。M3.1不支持stop、不能保证parallel_tool_calls=false串行、tool_choice仅auto，文档明确；本工具仍只返回文本与reasoning，未实现完整Function Calling循环 | [MiniMax直供差异/迁移](https://help.aliyun.com/zh/model-studio/minimax-api-by-minimax)、[Chat参数](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions) |

以下变化已兼容或仅记录：

- Chat新增 `include_tool_usage` 和 `usage.x_tools.search.{count,strategy}`，现有parameters透传与usage原样保留已支持，新增SSE回归验证。官方明确count为搜索意图触发次数，不是实际完成量或计费对账依据。GLM输出默认65536、最大131072等参数说明变化不需要本地硬编码默认值；`max_completion_tokens`继续通过parameters透传。
- TTS逐段保留官方usage对象，同名数值字段分别累加，修正原先把total_tokens归到characters的错误。旧任务的标量已丢失单位，不能由模型名推回；恢复时保留为 `legacy_untyped`，不混入新characters或token合计。这只是使用量记录，不推算账单费用。
- 新模型 `deepseek-v4.1-flash-1017`（10月17日）、`xiaomi/mimo-v2.6-pro-ultraspeed`（10月19日）与MiniMax-M3.1的发布/价格/限流表变化已记录，不自动切换默认模型，不把目录列出当作账号开通。补充候选提取正则中的DeepSeek/Xiaomi前缀；首次提取出的旧模型字符串不表示它们都是本轮上新，详情仍以正文diff和模型页为准。
- 旧Qwen文生图页删除异步 `text2image/image-synthesis` 章节及3.0交叉介绍；当前实现已使用同步multimodal-generation，新版3.0API正文未变，不改路由，也不把目录移除推荐位当作下线公告。
- Wan3只补充生成格式为MP4/H.264；HappyHorse还有表格样式调整。Chat模型页删去qwen-long的超长文档推荐，目录/价格/限流的命名、展示调整不改变已接入默认模型。
- 两篇「模型接入方式」新监控页介绍AOQ/WebSocket实时协议，不能据此宣称当前HTTP工具接入实时能力；CosyVoice和Qwen-Audio-Realtime的其他协议不在本轮实现范围。

本轮验证使用官方响应结构的mock和真实本地MCP协议，不发送API Key或付费请求。新模型、新地域、音色实际审核/质量与费用均未做云端验收；2026-10-13北京小样本记录只证明当时版本，不作为本次新增能力已通过云端的证据。

## 完整工具到官方接口映射

下表路径均相对 `DASHSCOPE_BASE_URL`，远程 API 使用 `Authorization: Bearer DASHSCOPE_API_KEY`。本地任务接口不调用新生成 API，恢复未提交 TTS 分段除外。

| 工具 | 接口与模型 | 核实结果和官方来源 |
| --- | --- | --- |
| `generate_image` | POST `/api/v1/services/aigc/multimodal-generation/generation`；`qwen→qwen-image-3.0-pro`、`wan→wan2.7-image-pro`、`z→z-image-turbo` | 同步、`input.messages` 和 `parameters` 对应。Qwen 2.1 已在相同图像协议出现，可显式传 ID；`qwen-image`、`qwen-image-max/plus`、`qwen-image-edit*` 已于 2026-10-10 下线，本地不再保留其专属限制。[Qwen 新版](https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference)、[旧版](https://help.aliyun.com/zh/model-studio/qwen-image-api)、[Wan2.7](https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference)、[Z-Image](https://help.aliyun.com/zh/model-studio/z-image-api-reference) |
| `chat` | POST `/compatible-mode/v1/chat/completions`；`max→qwen3.8-max`、`plus→qwen3.7-plus`、`flash→qwen3.8-flash` | 三个 ID 和视觉输入均有官方确认；`stream`、思考、JSON、联网参数取决于选定模型，透传其他 ID 不等于所有参数均受支持。[Chat 契约](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[模型目录](https://help.aliyun.com/zh/model-studio/text-generation-model)、[视觉目录](https://help.aliyun.com/zh/model-studio/vision-model) |
| `text_to_speech` | `qwen3-tts-flash`：POST multimodal-generation；Qwen-Audio-TTS / CosyVoice：POST `/api/v1/services/audio/tts/SpeechSynthesizer`；按模型名（或自定义音色 ID 前缀）路由 | qwen3-tts-flash 的 `input.text/voice/language_type`、`output.audio.url` 不变，传 `instructions` 本地拒绝；SpeechSynthesizer 的 `input.text/voice/format/sample_rate/instruction/language_hints`、`output.audio.url` 对应。250 字分段是本地策略，不是官方保证。[TTS API](https://help.aliyun.com/zh/model-studio/qwen-tts-api)、[Qwen-Audio-TTS](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[CosyVoice](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)、[指令控制](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)、[模型表](https://help.aliyun.com/zh/model-studio/tts-model) |
| `speech_to_text` | POST `/compatible-mode/v1/chat/completions`；仅 `qwen3-asr-flash`（日期快照已于 2026-10-10 下线，本地拒绝） | `input_audio`、`asr_options`、返回 message/annotations 对应；本地 10MB 检查，官方还有 5 分钟限制。其他 ASR 产品协议未实现。[ASR API](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)、[ASR 目录](https://help.aliyun.com/zh/model-studio/asr-model) |
| `generate_video` | POST `/api/v1/services/aigc/video-generation/video-synthesis`；`wan→wan3.0-video`、`wan-fast→wan3.0-video-prime` | `X-DashScope-Async: enable`、`input.media`、task_id 对应；仅允许这两个已接入 ID。[Wan3 API](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference) |
| `get_job`（视频任务） | GET `/api/v1/tasks/{task_id}`；不重新选模型 | 六种官方状态及 `video_url` 对应；task_id 与结果 URL 有有效期，不承诺长期远程恢复。[异步协议](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `list_models` | GET `/api/v1/models?page_no=…&page_size=100` | 已迁移官方目录，包含各模态并分页；目录存在不证明授权。[模型目录 API](https://help.aliyun.com/zh/model-studio/list-models) |
| `clone_voice` | POST customization；`voice-enrollment` `action=create_voice`，默认 target `qwen-audio-3.0-tts-flash` | `input.audio` + `prefix`，支持公网URL、Base64 Data URI、本地WAV/MP3/M4A；旧 `url` 别名与audio互斥；`oss://`本地拒绝；缺 `voice_id` 不重建。[复刻 API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[复刻指南](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide) |
| `design_voice` | POST customization；`voice-enrollment` `action=create_voice`，默认 target `qwen-audio-3.0-tts-flash` | `voice_prompt/preview_text/prefix/language_hints` + `parameters.sample_rate/response_format`；试听沿用 `voice_preview` 任务与 `recover_job`。[设计 API](https://help.aliyun.com/zh/model-studio/voice-design-api-references)、[设计指南](https://help.aliyun.com/zh/model-studio/voice-design-user-guide) |
| `list_voices` | POST customization；`voice-enrollment` `action=list_voice` | `kind` 旧值 clone/design/cosyvoice 映射到同一接口；1–100 是本地保护范围。[复刻](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[设计](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| `get_voice` | POST customization；`voice-enrollment` `action=query_voice` | 返回 `status`（DEPLOYING/OK/UNDEPLOYED）与 `target_model`；`max_pages` 仅兼容保留。[复刻 API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api) |
| `edit_video` | POST video-generation；`happyhorse-1.0-video-edit` | 1 段视频、0–5 张图、resolution/audio_setting、异步路径对应；超过 15 秒视频截断是官方行为。[HappyHorse 编辑](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `animate_portrait` | POST `/api/v1/services/aigc/image2video/video-synthesis`；`wan2.2-s2v` | image_url/audio_url、480P/720P、异步对应；北京能力，音频 <15MB/<20 秒。图片分辨率与远程文件时长由云端校验。[数字人 API](https://help.aliyun.com/zh/model-studio/wan-s2v-api) |
| `embed` | 文本 POST `/compatible-mode/v1/embeddings`，默认 `text-embedding-v4`；多模态 POST `/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding`，显式选模型 | 文本 `dimensions` 与多模态 `dimension` 区分正确；`qwen3-vl-embedding` 支持的维度/融合字段以模型为准，多模态不默认猜模型。[文本向量](https://help.aliyun.com/zh/model-studio/embedding)、[多模态向量](https://help.aliyun.com/zh/model-studio/multimodal-embedding-api-reference) |
| `rerank` | 全部模型 POST `/api/v1/services/rerank/text-rerank/text-rerank`，默认 `qwen3.7-text-rerank` | 2026-10-13 官方正文删除 `compatible-api/v1/reranks`，`qwen3-rerank` 示例改为原生 `input/parameters` 嵌套并支持 `return_documents`；已统一路由。VL rerank 未接入；不能当作纯文本字符串接口的普遍能力。[Rerank API](https://help.aliyun.com/zh/model-studio/text-rerank-api) |
| `list_jobs` | 本地 Store.list | 无云 API、无模型；本地记录不是云端状态探针。 |
| `get_job` | 本地 Store.get | 无云 API、无模型；只读取已存回执。 |
| `recover_job` | 原 video task_id 查询；image/voice_preview 重新交付；TTS 仅续未提交分段 | 不创建替代 video/image/voice job；TTS 尚未提交分段会产生新的合成费用。远程恢复仍受临时 URL 有效期限制。 |
| `list_capabilities` | 本地工具目录与官方 URL | `account_verified=false/validation=cloud_sampled/validated_on=2026-10-13` 仅指历史北京小样本，不代表本轮新增模型和地域已验证。 |
| `get_tool_help` | 共享运行时本地文档 | 无云 API、无模型。 |

上传依赖也已核实：GET `/api/v1/uploads?action=getPolicy&model=…` → 凭证指定的 OSS multipart POST → `oss://…`；请求需 `X-DashScope-OssResourceResolve: enable`。官方限制为 1GB、48 小时、同账号和同模型绑定，不能跨模型复用上传 URL。[官方上传正文](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)。

## 域名迁移与未验证项

官方现推荐北京 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`、新加坡 `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com`；HappyHorse美国文档使用 `https://{WorkspaceId}.us-east-1.maas.aliyuncs.com`。旧DashScope域名保留存量兼容，但官方明确自2026-09-30起不再接收新特性。已有 `DASHSCOPE_BASE_URL` 支持自定义根域名，无须改变 endpoint 路径。**新原生模型目录 API 的北京示例只列 workspace 域名，旧北京域名对此 API 的支持尚未实测**。不能把 `/api/v1` 或 `/compatible-mode/v1` 后缀也塞入 BASE_URL。各产品/协议/模型的地域支持不同，不能把根域名存在当作产品可用。[地域与接入域名](https://help.aliyun.com/zh/model-studio/regions)、[目录地址](https://help.aliyun.com/zh/model-studio/list-models)。

未确认：当前账号授权、云端实际输出/费用、限流与性能；公开 URL 指向文件的时长/分辨率/大小；任意用户显式传入的未登记模型。HTTP VC/VD 产品详情的“实时”营销文案与 `tts-model` 中 HTTP 模式表不一致，应以具体 API/模式表为路由依据，不按名称或简介推断协议。没有发送任何付费生成或账号请求。

## 最新官方文档获取

`ali-bailian-sources.json` 当前登记36个官方来源（2026-10-13语音迁移新增5个，2026-10-23新增4个域名/模型接入页）。本轮36篇`.md`均成功返回机器可读完整正文，可无需登录、无需JS、无需生成API Key获取。例如：

```sh
curl --fail --location https://help.aliyun.com/zh/model-studio/list-models.md
```

优先监控 API 正文、`models` 导航目录、`newly-released-models` 上下架、`model-pricing`、`rate-limit`；目录新增模型用于发现新增产品，具体参数以对应 API 正文复核。HTML 回退已实测：`window.__ICE_PAGE_PROPS__` 的 JSON 中 `docDetailData.storeData.data.content` 是完整正文，同级 `lastModifiedTime/docTitle/nodeId` 可读，不需要执行页面脚本。

`.md` 是官方可访问导出，但不把未承诺版本稳定性的前端格式当成永远不变的公共 API。自动拉取应校验 Content-Type、正文最小长度、标题、关键 endpoint/model，解析失败单独报警。只比较正文规范化指纹，保留原始导出和更新时间；避免把导航/模板变化误判为契约变化。文档变化生成待审查 diff，模型默认值与请求结构须经合同测试和人工核实后更新。

## 验证

本轮百炼包全部 **32 项离线测试通过**，新增 7 项合同回归覆盖目录分页、重复页、元数据保留、非法视频组合不上传、网页/纯音频参考、ASR 协议隔离、试听文本上限及图像专属限制。测试使用官方响应结构的 mock，没有执行真实付费请求。文件语法编译由主流程统一完成。

2026-10-13 复核后，百炼包 **33 项离线测试通过**：新增 rerank 原生路由，以及已下线 Qwen 音色创建 / instruct TTS 不发送请求两项回归，替换原设计试听上限测试（该路径已停用）。

2026-10-13 语音迁移后，百炼包 **43 项离线测试通过**：新增复刻 / 设计请求体与本地校验、设计试听交付与恢复不重建、缺音色 ID 不重试、kind 旧值映射、SpeechSynthesizer 路由与请求体、指令长度及模型限制、ASR 下线快照拒绝等回归，全部 mock，无真实付费请求。

2026-10-23更新后，百炼包 **51项离线测试通过**，上游文档/PR流程 **19项测试通过**；来源覆盖检查通过（全库143来源，本平台36来源）。新增回归覆盖本地录音与Data URI、url冲突/大小/格式、3.1-plus设计恢复/TTS路由、产品指令长度差异、按单位累加usage及旧任务恢复（含已完整交付任务的提前返回路径）、MiniMax思考协议/本地拒绝、搜索统计保留、DeepSeek/Xiaomi候选提取。真实stdio发现19个工具，验证audio/url输入schema、互斥及非法Data URI拒绝和最新chat帮助；父/子进程均校验模块来自PR独占worktree，provider请求数为0。测试通过不表示新模型或地域云端验收。
