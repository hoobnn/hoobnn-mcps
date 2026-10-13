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

待人工决策：是否把 `clone_voice`、`design_voice`、`text_to_speech` 迁移到官方现行的 `voice-enrollment`（`action=create_voice`，复刻需公网 `url` + `prefix`）与 `/api/v1/services/audio/tts/SpeechSynthesizer`（Qwen-Audio-TTS / CosyVoice，支持 `instruction`）。这需要新增合成协议、默认模型和来源登记，本轮未实现。

## 完整工具到官方接口映射

下表路径均相对 `DASHSCOPE_BASE_URL`，远程 API 使用 `Authorization: Bearer DASHSCOPE_API_KEY`。本地任务接口不调用新生成 API，恢复未提交 TTS 分段除外。

| 工具 | 接口与模型 | 核实结果和官方来源 |
| --- | --- | --- |
| `generate_image` | POST `/api/v1/services/aigc/multimodal-generation/generation`；`qwen→qwen-image-3.0-pro`、`wan→wan2.7-image-pro`、`z→z-image-turbo` | 同步、`input.messages` 和 `parameters` 对应。Qwen 2.1 已在相同图像协议出现，可显式传 ID；`qwen-image`、`qwen-image-max/plus`、`qwen-image-edit*` 已于 2026-10-10 下线，本地不再保留其专属限制。[Qwen 新版](https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference)、[旧版](https://help.aliyun.com/zh/model-studio/qwen-image-api)、[Wan2.7](https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference)、[Z-Image](https://help.aliyun.com/zh/model-studio/z-image-api-reference) |
| `chat` | POST `/compatible-mode/v1/chat/completions`；`max→qwen3.8-max`、`plus→qwen3.7-plus`、`flash→qwen3.8-flash` | 三个 ID 和视觉输入均有官方确认；`stream`、思考、JSON、联网参数取决于选定模型，透传其他 ID 不等于所有参数均受支持。[Chat 契约](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[模型目录](https://help.aliyun.com/zh/model-studio/text-generation-model)、[视觉目录](https://help.aliyun.com/zh/model-studio/vision-model) |
| `text_to_speech` | POST multimodal-generation；`flash→qwen3-tts-flash` | `input.text/voice/language_type`、`output.audio.url` 对应。2026-10-13 起官方正文已删除 `instructions/optimize_instructions`，instruct/VC/VD 模型已下线，传 `instructions` 本地拒绝；250 字分段是本地策略，不是官方 token 保证。[TTS API](https://help.aliyun.com/zh/model-studio/qwen-tts-api)、[模型及模式表](https://help.aliyun.com/zh/model-studio/tts-model) |
| `speech_to_text` | POST `/compatible-mode/v1/chat/completions`；`qwen3-asr-flash`（日期快照已于 2026-10-10 下线） | `input_audio`、`asr_options`、返回 message/annotations 对应；本地 10MB 检查，官方还有 5 分钟限制。其他 ASR 产品协议未实现。[ASR API](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)、[ASR 目录](https://help.aliyun.com/zh/model-studio/asr-model) |
| `generate_video` | POST `/api/v1/services/aigc/video-generation/video-synthesis`；`wan→wan3.0-video`、`wan-fast→wan3.0-video-prime` | `X-DashScope-Async: enable`、`input.media`、task_id 对应；仅允许这两个已接入 ID。[Wan3 API](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference) |
| `get_job`（视频任务） | GET `/api/v1/tasks/{task_id}`；不重新选模型 | 六种官方状态及 `video_url` 对应；task_id 与结果 URL 有有效期，不承诺长期远程恢复。[异步协议](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `list_models` | GET `/api/v1/models?page_no=…&page_size=100` | 已迁移官方目录，包含各模态并分页；目录存在不证明授权。[模型目录 API](https://help.aliyun.com/zh/model-studio/list-models) |
| `clone_voice` | 暂停用：本地直接返回错误，不发请求 | 默认 target `qwen3-tts-vc-2026-01-22` 已于 2026-10-10 下线，官方正文删除 `qwen-voice-enrollment` 的全部字段，只保留 `voice-enrollment` + Qwen-Audio-TTS/CosyVoice。[复刻 API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[HTTP 模型表](https://help.aliyun.com/zh/model-studio/tts-model) |
| `design_voice` | 暂停用：本地直接返回错误，不发请求 | `qwen-voice-design` 与 target `qwen3-tts-vd-2026-01-26` 已于 2026-10-10 下线；官方现为 `voice-enrollment` `action=create_voice`。已有试听任务仍可 `recover_job`。[设计 API](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| `list_voices` | POST customization；clone `qwen-voice-enrollment/action=list`、design `qwen-voice-design/action=list`、cosyvoice `voice-enrollment/action=list_voice` | clone/design 两类对应已下线模型，仅供查历史音色，云端可能拒绝；cosyvoice（`voice-enrollment`）为官方现行接口，覆盖 Qwen-Audio 系列，未接入其合成协议。1–100 是本地保护范围。[复刻](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[设计](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| `get_voice` | CosyVoice POST customization `query_voice/voice_id`；Qwen 使用分页 list | Qwen 没有相同 query_voice 契约，现有分页查找实现保持区分；max_pages 截断明确“不确定”。[复刻 API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api) |
| `edit_video` | POST video-generation；`happyhorse-1.0-video-edit` | 1 段视频、0–5 张图、resolution/audio_setting、异步路径对应；超过 15 秒视频截断是官方行为。[HappyHorse 编辑](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `animate_portrait` | POST `/api/v1/services/aigc/image2video/video-synthesis`；`wan2.2-s2v` | image_url/audio_url、480P/720P、异步对应；北京能力，音频 <15MB/<20 秒。图片分辨率与远程文件时长由云端校验。[数字人 API](https://help.aliyun.com/zh/model-studio/wan-s2v-api) |
| `embed` | 文本 POST `/compatible-mode/v1/embeddings`，默认 `text-embedding-v4`；多模态 POST `/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding`，显式选模型 | 文本 `dimensions` 与多模态 `dimension` 区分正确；`qwen3-vl-embedding` 支持的维度/融合字段以模型为准，多模态不默认猜模型。[文本向量](https://help.aliyun.com/zh/model-studio/embedding)、[多模态向量](https://help.aliyun.com/zh/model-studio/multimodal-embedding-api-reference) |
| `rerank` | 全部模型 POST `/api/v1/services/rerank/text-rerank/text-rerank`，默认 `qwen3.7-text-rerank` | 2026-10-13 官方正文删除 `compatible-api/v1/reranks`，`qwen3-rerank` 示例改为原生 `input/parameters` 嵌套并支持 `return_documents`；已统一路由。VL rerank 未接入；不能当作纯文本字符串接口的普遍能力。[Rerank API](https://help.aliyun.com/zh/model-studio/text-rerank-api) |
| `list_jobs` | 本地 Store.list | 无云 API、无模型；本地记录不是云端状态探针。 |
| `get_job` | 本地 Store.get | 无云 API、无模型；只读取已存回执。 |
| `recover_job` | 原 video task_id 查询；image/voice_preview 重新交付；TTS 仅续未提交分段 | 不创建替代 video/image/voice job；TTS 尚未提交分段会产生新的合成费用。远程恢复仍受临时 URL 有效期限制。 |
| `list_capabilities` | 本地工具目录与官方 URL | `account_verified=false/validation=offline_only` 正确。 |
| `get_tool_help` | 共享运行时本地文档 | 无云 API、无模型。 |

上传依赖也已核实：GET `/api/v1/uploads?action=getPolicy&model=…` → 凭证指定的 OSS multipart POST → `oss://…`；请求需 `X-DashScope-OssResourceResolve: enable`。官方限制为 1GB、48 小时、同账号和同模型绑定，不能跨模型复用上传 URL。[官方上传正文](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)。

## 域名迁移与未验证项

官方现推荐北京 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`、新加坡 `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com`；旧 DashScope 推理域名仍能使用。已有 `DASHSCOPE_BASE_URL` 支持自定义根域名，无须改变 endpoint 路径。**新原生模型目录 API 的北京示例只列 workspace 域名，旧北京域名对此 API 的支持尚未实测**。建议设置真实 workspace 根域名，不能把 `/api/v1` 或 `/compatible-mode/v1` 后缀也塞入 BASE_URL。[域名说明](https://help.aliyun.com/zh/model-studio/qwen-image-api)、[目录地址](https://help.aliyun.com/zh/model-studio/list-models)。

未确认：当前账号授权、云端实际输出/费用、限流与性能；公开 URL 指向文件的时长/分辨率/大小；任意用户显式传入的未登记模型。HTTP VC/VD 产品详情的“实时”营销文案与 `tts-model` 中 HTTP 模式表不一致，应以具体 API/模式表为路由依据，不按名称或简介推断协议。没有发送任何付费生成或账号请求。

## 最新官方文档获取

`ali-bailian-sources.json` 登记 27 个官方来源。每篇 `.md` 地址本轮实际 HTTP GET 均为 200、`text/markdown`、完整正文（约 6KB–826KB），可无需登录、无需 JS、无需生成 API Key 获取。例如：

```sh
curl --fail --location https://help.aliyun.com/zh/model-studio/list-models.md
```

优先监控 API 正文、`models` 导航目录、`newly-released-models` 上下架、`model-pricing`、`rate-limit`；目录新增模型用于发现新增产品，具体参数以对应 API 正文复核。HTML 回退已实测：`window.__ICE_PAGE_PROPS__` 的 JSON 中 `docDetailData.storeData.data.content` 是完整正文，同级 `lastModifiedTime/docTitle/nodeId` 可读，不需要执行页面脚本。

`.md` 是官方可访问导出，但不把未承诺版本稳定性的前端格式当成永远不变的公共 API。自动拉取应校验 Content-Type、正文最小长度、标题、关键 endpoint/model，解析失败单独报警。只比较正文规范化指纹，保留原始导出和更新时间；避免把导航/模板变化误判为契约变化。文档变化生成待审查 diff，模型默认值与请求结构须经合同测试和人工核实后更新。

## 验证

本轮百炼包全部 **32 项离线测试通过**，新增 7 项合同回归覆盖目录分页、重复页、元数据保留、非法视频组合不上传、网页/纯音频参考、ASR 协议隔离、试听文本上限及图像专属限制。测试使用官方响应结构的 mock，没有执行真实付费请求。文件语法编译由主流程统一完成。

2026-10-13 复核后，百炼包 **33 项离线测试通过**：新增 rerank 原生路由，以及已下线 Qwen 音色创建 / instruct TTS 不发送请求两项回归，替换原设计试听上限测试（该路径已停用）。
