# Doubao Speech 官方接口与模型核实

核实日期：2026-10-10。范围：`servers/doubao-speech` 的官方接口契约。0.4.0 把 29 个工具重组为默认 18 个加按需启用的 6 个，底层请求体与本表逐路核实的端点不变；下表首列已改为新的调用入口。逐路核实兜底入口 `speech_raw_request` 的 3 个 HTTP product、历史接口的 11 个 operation、ASR 2 个 mode、WS TTS 2 个 mode、词表 13 个 Action，以及控制面 25 个默认 Action/Version。没有调用付费生成、识别、训练、下单或管理接口。

## 结论与修正

固定 endpoint、三类鉴权、默认资源 ID 和控制面 25 个默认版本，均有本轮实时读取的火山官方正文支持。发现并修正五处具体问题：

1. **实时 3.0 输入编码**：官方枚举为 `pcm` / `speech_opus`，原实现接受并透传 `opus`。现在接受 `speech_opus`，旧 `opus` 参数规范化为官方值，保留调用兼容。
2. **音频生成**：官方支持 `pcm`，便捷工具遗漏该格式；采样率必须按格式选择，原验证只有宽泛数值范围。现在补充 PCM，`wav/pcm` 支持 8000、16000、24000、32000、40000、44100、48000；`mp3` 不支持 40000；`ogg_opus` 仅 48000。工具默认 `mp3` 是本地产品选择，官方默认 `wav`，不等于请求错误。
3. **同传 protobuf 版本漂移**：当前官方 `protos.tar.gz` 的 `ReqParams` 有 `extra=80`；`TranslateResponse` 有 `speaker_id=9`、`detected_language=10`、`language_confidence=11`，本地旧 Python demo bindings 缺这些字段。使用官方 proto 和 protoc 6.31.0 重新生成 AST binding；另外三份依赖 descriptor 与当前 bundle 一致。source_segments 保留服务实际返回的语种、置信度与 speaker_id；同步删除能力目录中“官方 protobuf 尚未声明”的过时说明。
4. **异步长文本查询**：官方 `data.task_status` 为 1=running、2=success、3=failure。原实现只看顶层请求成功码，可能将查询到的失败任务报为成功。现在提供明确 status，任务失败返回 `ok=false`，不重新提交。
5. **声音复刻语种**（0.4.0 重组时发现）：官方 `language` 是整数枚举（cn=0、en=1、ja=2…），旧工具说明和示例写成 `'zh'` 字符串。`clone_voice` 现在接受语种代码并转换为官方整数，未知代码在本地拒绝。

新增回归测试覆盖上述官方契约，含独立手工编码 protobuf wire fixture。0.4.0 后豆包语音共 **132 项离线测试通过**。这证明本地实现与已取得文档/协议样本相符，不证明账号开通、生产可用、实际模型效果或每个音色授权。

## 2026-10-26 上游文档复核（PR #22）

重新抓取 **77/77** 个官方来源，0 失败，与 PR 捕获基线无新增差异；全部 77 个 gzip 快照解压后 SHA-256 核验通过。主分支到 PR 仅 1 篇变化，见 [报告](../upstream/doubao-speech/review/9bccbdcdda03b22a55f83d7865722525597be1c4a19efdac44574562e64eba3a/report.md) 及同目录 `diffs/`。

[接入必读](https://docs.volcengine.com/docs/doubao-voice/access-must-read?lang=zh) 将“音频格式约束”扩展为“音频约束”，新增人声与背景噪声质量要求，并替换 Seeduplex / Seed-Realtime 交互示意图。输入编码、16kHz 单声道 int16 小端序、Base64 字段、20ms / 640 字节节奏、静音/取消静音保活事件与输出配置均未改变。

纯人声 RMS 推荐 −31.7～−23.9 dBFS，中心约 −27.6；最低准入不低于 −37、不高于 −19.5 dBFS，峰值 ≤−1 dBFS。纯背景噪声 RMS 推荐 ≤−50 dBFS，中心约 −52.6；SNR 推荐 20～30 dB，最低准入为噪声 ≤−45 dBFS 且 SNR ≥15 dB。

中英文 README 补充质量要求与既有静音保活操作。`send_realtime_event` 已可透传 `input_audio_mute.commit` / `input_audio_unmute.commit`，现有音频分片节奏与编码保持一致，无需协议迁移。客户端承担设备采集、质量控制与播放，MCP 不自动增益或降噪；从混合流不能可靠计算官方定义的纯人声/纯背景噪声指标，因此不加入未经声源分离验证的本地硬拦截。

未连接真实语音服务。离线检查回执见 [review-notes.md](../upstream/doubao-speech/review/9bccbdcdda03b22a55f83d7865722525597be1c4a19efdac44574562e64eba3a/review-notes.md)。

## 2026-10-24 上游文档复核（PR #18）

重新抓取 **77/77** 个官方来源，失败 0，3 篇正文变化，完整差异见 [报告](../upstream/doubao-speech/review/c4991f0fa3afdc03212ccb85849dc112154057604ff1b0671935d6484e258fa5/report.md) 及同目录 `diffs/`。

- **Seeduplex 3.0 正文改为 Markdown 导出。** 全双工页 934 行 diff 主要是 `<span>` 锚点、`<Attachment>`、`data-api-tag`、提示框 `<div>` 转为纯 Markdown；去除标记后逐字比对，请求路径、`model=1.2.6.1`、鉴权头、事件类型、音频格式/采样率及分片节奏均未变。旧版控制台鉴权说明仍在，只是链接写法变化。
- **系统提示词上限放宽。** Seeduplex 3.0 的 `instructions` 与内部 SP 合计上限由 12K tokens 改为 64K tokens，并明确包含对话历史和 FC 结果；Seed-Realtime 1.0 同样补充 FC 结果。本实现不在本地限制 `instructions` 长度，交服务端校验，无需改代码。
- **新增音频质量提示。** 全双工页提示按接入必读的音频约束输入，人声过轻或背景噪声过大会降低效果；属于使用建议，不改变上行事件契约。
- **目录标题。** 文档目录把「端到端实时语音」改名为「端到端实时语音（Seeduplex）」，DocumentCode 不变。

本轮没有运行时代码变化，也没有发起真实实时会话或付费请求。

## 2026-10-23 接入更新（PR #15）

本节记录当前实现，覆盖下方 2026-10-13 保留 WebSocket 的历史结论。重新抓取 **77/77** 个官方来源，失败 0；相对本 PR 原待审基线新增 Seed-Realtime 文档，另有接入必读、播客、营销条款和目录变化。`podcast_mustread` 已在原来源清单内，继续保留；新加入 `seedrealtime`。旧 review 与正文快照不删除，新基线只更新本平台。

- **播客默认 HTTP SSE。** 最新目录把 `PodcastAPI-websocket-v3protocol` 移到 `history-podcast` → `HistoryDocs-9`，主产品下为 `podcast`。`generate_podcast(transport="sse")` 向 `/api/v3/podcast/sse` 一次 POST，使用 API Key 和 `volc.service_type.10050`；原 WS 入口保留为 `transport="websocket"`。播客正文已删除旧控制台鉴权兼容说明，本实现只使用当前明确列出的 API Key。
- **SSE 完成与续传。** 校验 HTTP 200 + `text/event-stream`，解析 `event:` / 多行 `data:`、CRLF、注释保活及 Base64。仅 152 且 `code=20000000` 成功；363、154 和 HTTP 200 不能证明成功，151 取消、153 失败、轮次错误及断流都保留未完成状态。`task_id` 来自首次 150 的真实 `session_id`，续传新 ID 单列 `session_id`，重复续传始终使用首次 ID。原请求、ID、完整轮次及 `retry_info` 保存为无鉴权头的 `progress_file`；150 与每个完整 362 即落盘，MCP 取消仍在 finally 保存 partial/diagnostic 并上抛取消，不自动重发付费 POST。
- **持久化边界。** 完整轮次音频先写不可变 `through-<round>.partial.*` 快照，再原子发布 receipt；只推进实际落盘的 `last_finished_round_id`。音频写失败时 receipt 仍指向旧文件及旧续传边界，`received_last_finished_round_id` 单列已接收但可能未落盘的边界。未完成轮次只进 `diagnostic_file`，不参加续传；续传片段不自动合并，需按已保留时长换算全局时间轴。SSE 使用 MCP 当前剩余预算，直接 Python 调用上限 3600 秒；提高客户端超时还需同步提高 `MCP_TOOL_TIMEOUT_SEC`。
- **Seed-Realtime 是独立模式。** `open_realtime_session(mode="seed")` 使用 `/api/v3/seedrealtime` + `session.model=1.3.0.0`；兼容默认 `mode="legacy"` 保留 `/api/v3/duplex/realtime/dialogue` + `1.2.6.1`。新旧模型及图像能力分开验证。Seed 禁止上行 `response.cancel`，只由 `response.created/canceled/done` 切换 `playback_state`；ASR 仅转写。取消时切断当前音频文件并清掉本地未交付音频事件，`receive` 顶层粘滞 `clear_playback_buffer=true` 不能因事件队列溢出丢失，客户端仍须停播并清空自己的缓冲。
- **图像字段层级的依据。** `seedrealtime` Markdown 字段表扁平化，无法单靠文字确定 `video` 层级。2026-10-23 只读检查同页 [官方 Python 示例附件](https://portal.volccdn.com/obj/volcfe/cloud-universal-doc/upload_7eea057b3ec4d62db61f1117ae8187e2.zip)，163752 bytes，SHA-256 `3b288147fd171ea9edd5e75c810bdb55b49df5d77d0a5736a5e8ad5dd7efc424`；其中 `realtime_client.py` 把 `frame_format` 与 `frame_rate` 放在**顶层 `extension.video`**，而 `audio/model/tools` 在 `session`。本实现按该结构独立编写，未运行或复制示例实现。图像事件为 `input_image_buffer.append`，Base64 `image`，可选 `frame_id`；便捷 `image_file` 支持 PNG/JPEG，校验内容格式并独立限速至至多 2 FPS，JSON 事件本地上限 2MB。[接入必读](https://docs.volcengine.com/docs/doubao-voice/access-must-read?lang=zh) 新增短边720p、JPEG质量70–80、单帧约100KB等采集建议，便捷工具不采集摄像头或调整图片。
- **文档冲突边界。** 通用 `access-mustread` 仍保留 legacy `model=1.2.6.1` 和 `response.cancel` 的说明；新 [Seed-Realtime 专页](https://docs.volcengine.com/docs/doubao-voice/seedrealtime?lang=zh) 明确 `1.3.0.0` 和不再支持客户端取消，事件表尾部仍残留把 `response.canceled` 解释为取消 ack 的旧行。Seed 按专页开头和状态机的明确说明处理，旧模式继续兼容。Seed Audio 1.5 营销条款调整消费周期、代金券期限等，但仍无可验证的 API model ID，保持 `seed-audio-1.0`。

新增离线回归覆盖 SSE 终止码、真实 ID、多行/保活/Base64、script_only、续传、超时/取消/磁盘写失败，以及 Seed 模型/入口配对、extension.video、2FPS、ASR 与播放状态解耦和队列丢失取消。本轮整包 **155 项测试通过**（含真实 stdio 初始化/工具发现/示例 schema 验证；新 SSE 13 项、实时会话共30项）、上游文档脚本 **18 项测试通过**。独占 worktree 的 `.venv` 已确认导入本 worktree 源码，wheel/sdist 构建成功且均包含 `podcast.py`；来源覆盖、共享运行时同步以及 77 份 gzip 快照的 SHA-256 校验通过。未执行付费生成、真实账号权限、摄像头/播放设备或生产验收。

## 2026-10-13 上游文档复核

每日检查（PR #4，review `faea4e3c…`）报告 74/74 抓取成功、3 项正文变化。逐条对照 diff、全文快照与实现后结论：

- **实时 3.0（endtoend-realtime-voice-full-duplex-version）：无实质契约变化。** 事件表删去 `response.output_audio.done` 的示例值 `status_code="20000002"`；`enable_user_query_exit` 字段说明仍写明退出意图信号随该事件下发。实现原样透传 session 字段和全部事件，从不依据该值判断，无需修改。具体信号取值以服务实际返回为准，不再在本地写死 20000002。
- **音色列表（Tonelist-1）：新增音色，无需改代码。** 2.0 外语音色新增 21 个印尼语、越南语、西班牙语、马来语、泰语、美式英语、日语、菲律宾语、墨西哥西语、意大利语、巴西葡萄牙语音色，ID 均为 `*_uranus_bigtts`，`text_to_speech` 的命名启发式会自动选 `seed-tts-2.0`。其中 12 个有声阅读音色「仅限单向流，双向流调用直接报错」，原文「16 个」改为「个别」。当时未在本地拦截；复核全文后实际有 27 个音色带该备注（12 个只是新增有声阅读块），已改为本地拒绝，见下节。
- **目录（DoubaoVoice 索引）：新增 `podcast`、`podcast_mustread`，有实质内容，已登记为 `generate_podcast` 的来源。** 两篇文档描述新的 HTTP SSE 接口 `POST /api/v3/podcast/sse`，资源同为 `volc.service_type.10050`。请求体（action 0/3/4、input_text/prompt_text/nlp_texts 限制、input_info、speaker_info 两位发音人、audio_config 的格式和采样率、retry_info）和事件 150/360/361/362/363/154/152 与现有 WebSocket 实现一致。原 [WebSocket 播客](https://docs.volcengine.com/docs/doubao-voice/podcast-api-websocket-v3protocol?lang=zh) 仍在目录中（索引 Status=2，新文档 Status=5），本次不切换传输。新文档在断点续传上写得更明确：只保留收到 362 且未标记 `is_error` 的完整轮次，未完成轮次的音频分片必须丢弃。原实现会把未完成轮次的分片也写进 `.partial.*`，续传后拼接会出现重复片段，**已修正**：失败时 partial 文件截到最后一个成功的 362，丢弃的字节数写入 `discarded_bytes`。已补回归测试。`return_audio_url` 链接有效期：WebSocket 文档写 1 小时，SSE 文档写 24 小时，按 1 小时保守提示。`:keep-alive` 注释行等 SSE 专属细节不适用于当前 WebSocket 路径；151 SessionCanceled 的处理见下节。

其余 71 个来源正文指纹未变，沿用 2026-10-10 的结论。新登记的两个来源已写入本 PR 的待审基线。

## 2026-10-13 遗留项修复

本节处理上一节留下的四个问题。官方正文于 2026-10-13 通过 `getDocDetail` / `getDocList` 重新读取，与基线快照的 `UpdatedTime` 一致（podcast 2026-10-12T07:34:57Z、podcast_mustread 2026-10-12T07:32:54Z、PodcastAPI-websocket-v3protocol 2026-09-29T08:52:01Z、Tonelist-1 2026-10-13T08:17:11Z），未新增来源，基线不变。

1. **未完成轮次的诊断音频。** 续传输入 `.partial.*` 仍只含最后一个成功 362 之前的完整轮次；截掉的分片另存为 `podcast-<task_id>.unfinished-round.diagnostic-not-for-resume.<fmt>`，路径在 `diagnostic_file`，不进入 `files`，`discarded_bytes` 保留。一轮都没完成时同样保存。诊断文件保存失败只追加错误，不影响 `.partial.*`。
2. **151 SessionCanceled。** [WebSocket 播客](https://docs.volcengine.com/docs/doubao-voice/podcast-api-websocket-v3protocol?lang=zh)事件表未列 151；依据是 [SSE 接入必读](https://docs.volcengine.com/docs/doubao-voice/podcast-mustread?lang=zh)「151：SessionCanceled｜结束读取，保留已接收的数据，并将请求标记为取消」，[双向 TTS](https://docs.volcengine.com/docs/doubao-voice/bidirectional-streaming-text-to-speech-websocket?lang=zh) 也列有 `SessionCanceled`。原实现收到 151 会一直等到 300 秒超时。现在播客收到 151 立即失败，错误带服务端 payload，返回 `canceled: true`，partial 和诊断文件逻辑不变；`tts_websocket` 同样立即失败。WebSocket 从不发 151 时此分支不触发，对现有流程无影响。
3. **WebSocket 与 SSE：保留 WebSocket。** 证据：
   - [SSE 接口](https://docs.volcengine.com/docs/doubao-voice/podcast?lang=zh)与[接入必读](https://docs.volcengine.com/docs/doubao-voice/podcast-mustread?lang=zh)全文没有「推荐」「替代」「迁移」类表述，只写「本文介绍 HTTP SSE 接口的接入方式」；文中「建议」只涉及输入长度和音色配对。
   - [WebSocket 文档](https://docs.volcengine.com/docs/doubao-voice/podcast-api-websocket-v3protocol?lang=zh)没有弃用、下线或不推荐声明，仍挂在「语音播客大模型」目录下，且 2026-09-29 仍在更新；未被移到「历史文档」（HistoryDocs-9）或「归档」（Archive）目录。
   - `Status` 字段官方无公开定义。目录 251 项中，Status=1 的 55 项全是目录节点；Status=2 的 143 项全是文档，既有当前主文档[音色列表](https://docs.volcengine.com/docs/doubao-voice/tone-list-3?lang=zh)，也有「历史文档」下的旧版 V3；Status=5 的 53 项既有新文档 podcast，也有 2025 年的[播客产品简介](https://docs.volcengine.com/docs/doubao-voice/ProductOverview-4?lang=zh)，还有「归档」目录本身。它与新旧、推荐或弃用都不对应，和 `ContentType`（md/json）也不对应，不能作为弃用依据。
   结论：没有官方证据表明 SSE 是推荐方式或 WebSocket 将弃用，`generate_podcast` 继续使用 WSS `/api/v3/sami/podcasttts`。回归测试断言连接地址仍是该 WebSocket 端点。若官方日后声明弃用或推荐 SSE，再按请求体同构迁移。
4. **仅限单向流的音色。** [音色列表](https://docs.volcengine.com/docs/doubao-voice/tone-list-3?lang=zh)「豆包语音合成模型2.0 外语音色列表」中备注「仅限单向流使用，不支持双向流，双向流调用会直接报错」的音色共 27 个（上节统计的 12 个只是连续新增的有声阅读块，另有 15 个分布在美式英语、德语、法语、日语、韩语、墨西哥西语、巴西葡萄牙语、意大利语中）。名单写在 `ws_products.UNIDIRECTIONAL_ONLY_SPEAKERS`，注释写明来源 URL 和日期。唯一走双向流 TTS 的路径是 `speech_raw_request(product='tts_websocket')`（默认 `mode='bidirectional'`），用这些音色时在本地拒绝并提示改用 `mode='unidirectional'` 或 `text_to_speech`。`text_to_speech` 走单向流 HTTP `/api/v3/tts/unidirectional`，不受限制，无需拦截；实时 3.0 和同传不使用 TTS 双向流接口，不在本次范围。播客发音人能否使用这些音色，官方未写明，本地不拦截。

## 本轮实际获取方式

普通文档网页在 HTTP 抓取及 web.open 中是 JavaScript 空壳；追加 `.md` 和 `https://docs.volcengine.com/llms.txt` 同样返回 HTTP 200 HTML，不能算正文获取成功。

从官方公开前端 `main.3613eab6.js` 读取其真实 API 路由后，实测：

- 索引：`GET https://docs.volcengine.com/api/doc/getDocList?LibraryCode=DoubaoVoice`。返回 DocumentID、DocumentCode、父级关系、标题，覆盖当前/历史产品及管理文档。
- 正文：`GET https://docs.volcengine.com/api/doc/getDocDetail?LibraryCode=DoubaoVoice&DocumentCode=audio-generation-http`。无需账号/API Key，返回 `Result.MDContent`、`ContentType`、`UpdatedTime`、`CanonicalURL` 等。
- `Content` 可能是 JSON 编辑器数据；**必须优先 `MDContent`**，不能把编辑器 JSON 或 HTTP 200 HTML 当成 Markdown。
- 本轮成功取得 **73 篇非空 MDContent**，包含 JSON 编辑器类和旧 Markdown 类文档；完整来源及 1 个文档目录源在 `doubao-speech-sources.json`，正文更新时间、字符数与 SHA256 在 `doubao-speech-evidence.json`。这属于官网当前使用的公开读取 API，未发现公开稳定性 SLA，因此脚本应失败报告而非默默采用空内容。
- 一个目录节点 `Consolerelatedinterfaces` 在 detail API 无正文；通过官方索引找到其子 Action 文档逐个核实，没有把目录空壳列为成功正文来源。
- MDContent 覆盖该文档转换正文，但不包含需另取的 SDK zip、proto 包、图片内容以及所有动态代码 tab；协议附件应独立核实。本轮实际下载并检查同传 proto 包，未执行官方 demo。

## 全部工具映射

下表 endpoint 主机默认 `openspeech.bytedance.com`；HTTP 为 POST，特别标注的历史查询为 GET。资源列省略资源 ID 时表示该官方接口使用 API Key 和请求体选择，不擅自加 TTS/ASR 资源。

| MCP 工具 | endpoint / 模式 | 鉴权、模型或资源 | 官方正文 / 核实结论 |
|---|---|---|---|
| `text_to_speech` | `/api/v3/tts/unidirectional` | API Key；`seed-tts-2.0` / `seed-icl-2.0`；1.0 兼容资源见历史协议 | [HTTP](https://docs.volcengine.com/docs/doubao-voice/unidirectional-streaming-text-to-speech-http?lang=zh)、[二进制/Chunked细节](https://docs.volcengine.com/docs/doubao-voice/http-chunked-sse-unidirectional-streaming-v3?lang=zh)。已确认；本地按字符分段是交付策略，非官方硬限制 |
| `speech_to_text` | `/api/v3/auc/bigmodel/recognize/flash` | API Key；`volc.bigasr.auc_turbo`；`request.model_name=bigmodel` | [极速版](https://docs.volcengine.com/docs/doubao-voice/recording-file-recognition-lite-http?lang=zh)。已确认；wav/mp3/ogg/spx/amr/aac/m4a 明确列出 |
| `generate_audio` | `/api/v3/tts/create` | API Key；body.model=`seed-audio-1.0` | [音频生成](https://docs.volcengine.com/docs/doubao-voice/audio-generation-http?lang=zh)。已确认；3000字符、最多3条音频参考、1张图片、最长120秒、PCM与各格式采样率已核实 |
| `text_to_speech`（异步长文本提交） | `/api/v3/tts/submit` | API Key；`seed-tts-2.0` / `seed-icl-2.0` | [提交](https://docs.volcengine.com/docs/doubao-voice/task-sub-mission?lang=zh)。已确认；100000字符、unique_id 20–64字符 |
| `get_job`（长文本查询） | `/api/v3/tts/query` | API Key；提交时资源、task_id | [查询](https://docs.volcengine.com/docs/doubao-voice/result-query?lang=zh)。已确认；task_status失败语义已修正 |
| `clone_voice` | `/api/v3/tts/voice_clone` | API Key；speaker_id；自定义槽使用 `custom_speaker_id` | [注册](https://docs.volcengine.com/docs/doubao-voice/tone-training-http?lang=zh)。已确认；10MB、PCM仅24k单声道；注册是付费训练，本轮未调用 |
| `get_voice` | `/api/v3/tts/get_voice` | API Key；speaker_id/custom_speaker_id | [查询](https://docs.volcengine.com/docs/doubao-voice/tone-query-http?lang=zh)。已确认；status=0/1/2/3/4 是音色状态，HTTP查询成功不等于训练成功 |
| `upgrade_voice` | `/api/v3/tts/upgrade_voice` | API Key；speaker_id/custom_speaker_id | [升级](https://docs.volcengine.com/docs/doubao-voice/tone-upgrade-http?lang=zh)。已确认；不假定已有音色权限 |
| `design_voice` | `/api/v3/tts/voice_design` | API Key；speaker_id；prompt | [设计](https://docs.volcengine.com/docs/doubao-voice/sound-design-api?lang=zh)。已确认；试听text≤300、text_prompt≤200、图片≤10MB |
| `speech_to_text`（mode=standard/idle 提交） | standard `/api/v3/auc/bigmodel/submit`；idle `/api/v3/auc/bigmodel/idle/submit` | API Key；standard=`volc.seedasr.auc`，兼容1.0=`volc.bigasr.auc`；idle=`volc.bigasr.auc_idle` | [标准提交](https://docs.volcengine.com/docs/doubao-voice/task-submission-http-1?lang=zh)、[闲时提交](https://docs.volcengine.com/docs/doubao-voice/task-submission-http?lang=zh)。两路均已确认；URL输入、bigmodel、同一任务UUID |
| `get_job`（标准/闲时识别查询） | standard `/api/v3/auc/bigmodel/query`；idle `/api/v3/auc/bigmodel/idle/query` | API Key；原任务UUID和原资源 | [标准查询](https://docs.volcengine.com/docs/doubao-voice/result-query-http-1?lang=zh)、[闲时查询](https://docs.volcengine.com/docs/doubao-voice/result-query-http?lang=zh)。两路均已确认；待处理/排队状态保留 |
| `translate_text` | `/api/v3/machine_translation/matx_translate` | API Key；`volc.speech.mt`；Seed-X产品线 | [机器翻译](https://docs.volcengine.com/docs/doubao-voice/machine-translation-large-model-api-access-documentation?lang=zh)。已确认；text_list≤16，单条≤1024 Tokens，corpus术语透传；本地不猜token精确计数 |
| `summarize_meeting`（提交） | `/api/v3/auc/lark/submit` | API Key；`volc.lark.minutes` | [妙记](https://docs.volcengine.com/docs/doubao-voice/doubao-voice-minutes-api-access-documentation?lang=zh)。已确认；Input.Offline/Params、AllActivate计费选择 |
| `get_job`（妙记查询） | `/api/v3/auc/lark/query` | API Key；`volc.lark.minutes`，TaskID | [妙记](https://docs.volcengine.com/docs/doubao-voice/doubao-voice-minutes-api-access-documentation?lang=zh)。已确认；任务状态独立于请求成功 |
| `manage_word_table` | 热词API Key proxy `/api/proxy/invoke?Action=...`；或OpenAPI AK/SK | 热词version=2022-08-30；替换词version=2023-10-30；region=cn-north-1 | [热词](https://docs.volcengine.com/docs/doubao-voice/hot-word-management-api-v10?lang=zh)、[替换词](https://docs.volcengine.com/docs/doubao-voice/replacement-word-api-v11?lang=zh)。13个Action逐项在正文确认；替换词未假定支持API Key proxy |
| `speech_console` | `https://open.volcengineapi.com/?Action=...&Version=...` | IAM AK/SK、HMAC-SHA256、service=`speech_saas_prod`；默认region=cn-beijing | 默认25个Action逐文档确认，见后表；旧监控版本及ListApplications用cn-north-1/GET |
| `speech_raw_request`（product=tts_websocket） | WSS `/api/v3/tts/bidirection` 或 `/api/v3/tts/unidirectional/stream` | API Key + TTS/ICL resource | [双向](https://docs.volcengine.com/docs/doubao-voice/bidirectional-streaming-text-to-speech-websocket?lang=zh)、[单向](https://docs.volcengine.com/docs/doubao-voice/unidirectional-streaming-text-to-speech-websocket?lang=zh)。两路已确认；具体二进制框架依据同endpoint的历史V3协议。音色列表标注仅限单向流的27个音色在bidirectional下本地拒绝 |
| `generate_podcast` | 默认 HTTP SSE `/api/v3/podcast/sse`；可选历史 WSS `/api/v3/sami/podcasttts` | API Key；`volc.service_type.10050` | [播客](https://docs.volcengine.com/docs/doubao-voice/podcast?lang=zh)、[接入必读](https://docs.volcengine.com/docs/doubao-voice/podcast-mustread?lang=zh)。已实现SSE解析、严格152成功码、真实ID、完整轮次持久化与显式续传 |
| `speech_raw_request`（product=asr_stream） | realtime WSS `/api/v3/sauc/bigmodel_async`；sentence `/api/v3/sauc/bigmodel_nostream` | API Key；2.0小时版=`volc.seedasr.sauc.duration`；可显式选择concurrent或1.0资源 | [实时识别](https://docs.volcengine.com/docs/doubao-voice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)、[一句话](https://docs.volcengine.com/docs/doubao-voice/unidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)。两路已确认；本地只封装PCM/WAV，官方还支持更多格式 |
| `interpret_audio` | WSS `/api/v4/ast/v2/translate` | API Key；`volc.service_type.10053`；官方protobuf | [同传](https://docs.volcengine.com/docs/doubao-voice/simultaneous-interpretation2-0-api-access-documentation?lang=zh)。已确认；源16k/16bit/mono；目标pcm16k/pcm24k float32/ogg_opus48k；proto漂移已修复 |
| `open_realtime_session` | mode=legacy WSS `/api/v3/duplex/realtime/dialogue`；mode=seed WSS `/api/v3/seedrealtime` | API Key；legacy=`1.2.6.1` / seed=`1.3.0.0` | [实时3.0](https://docs.volcengine.com/docs/doubao-voice/end-to-end-real-time-voice-full-duplex-version?lang=zh)、[Seed-Realtime](https://docs.volcengine.com/docs/doubao-voice/seedrealtime?lang=zh)。独立endpoint/model校验，seed视频配置为extension.video |
| `send_realtime_event` | 同一持久socket；audio/image/context/tool/update | 本地session_id映射原socket | seed支持input_image_buffer.append和PNG/JPEG便捷输入、至多2FPS；禁止response.cancel；legacy保持原取消语义 |
| `receive_realtime_events` | 同一socket；JSON事件/音频delta/response状态 | 同一会话 | seed只按response.created/canceled/done驱动playback_state，clear_playback_buffer清缓冲信号不因队列溢出丢失 |
| `close_realtime_session` | `session.close` → `session.closed` | 同一会话 | [实时3.0](https://docs.volcengine.com/docs/doubao-voice/end-to-end-real-time-voice-full-duplex-version?lang=zh)。已确认；传输断开不当成官方ack |
| `speech_raw_request`（product=tts/asr_flash/audio） | product=tts/asr_flash/audio，分别对应上表3个HTTP路径 | 与对应产品一致 | **三个枚举分支都已核实**；完整请求透传不等于自动支持未知endpoint或每个账号/模型 |
| `speech_raw_request`（product=legacy） | operation白名单11条，见后表 | 旧AppID/Access Token，Bearer分号语法 | **11个operation都已核实**；不是V3 API Key鉴权 |
| `get_speech_usage_examples` | 本地usage.GUIDES | 无鉴权/无网络 | 示例是官方材料的本地归纳与改写，不是已经产生的云端作品 |
| `list_speech_capabilities` | 本地能力目录 | 无鉴权/无网络 | 静态目录不是账号权限发现；模型/音色实际来源见后节 |

## 模型、资源与结束协议

- TTS/ICL：新版同步与长文本默认2.0资源；模型版本是独立的 `req_params.model`（复刻场景默认 `seed-tts-2.0-standard`；旧V3详细文档还列 `seed-tts-2.0-expressive`）。`S_`等音色命名判断是便利启发式，不足以替代[音色表](https://docs.volcengine.com/docs/doubao-voice/tone-list-3?lang=zh)或 `ListSpeakers(ResourceIDs=...)`。自定义/非典型ID应明确传resource_id。
- HTTP TTS：最新精简正文说code=0成功；同endpoint的[详细Chunked协议](https://docs.volcengine.com/docs/doubao-voice/http-chunked-sse-unidirectional-streaming-v3?lang=zh)明确音频过程包code=0、结束包code=20000000。保留完成标记验证，依据详细wire契约，而非本地样例自行假设。
- WS TTS：旧V3明确二进制header、带event/session_id，ConnectionStarted=50、SessionStarted=150、TTSResponse=352、SessionFinished=152、ConnectionFinished=52。双向生命周期为1→50、100→150、200文本、102结束session、152确认、2→52；单向入口一次发完整请求。新精简文档以EventType字符串描述语义，不足以单独证明wire已切换为JSON；实际同endpoint的详细V3协议仍需保留来源。
- ASR：固定request.model_name=`bigmodel`不表示模型1.0/2.0，真正版本/计费由X-Api-Resource-Id区分。标准2.0=`volc.seedasr.auc`，极速=`volc.bigasr.auc_turbo`，闲时=`volc.bigasr.auc_idle`；流式2.0=`volc.seedasr.sauc.duration`/`concurrent`，旧1.0为`volc.bigasr.sauc.*`。负序号音频包表示上行结束，下行最后包flag/负sequence之后才算完成。
- 播客：固定资源10050。默认SSE一次POST后接收150、360/361/362轮次、可选363、154，只有152且code=20000000成功；可选历史WS仍走100→150及2→52。收到轮次失败、disconnect或151 SessionCanceled（依据SSE文档）时保存partial，只含最后一个成功362之前的完整轮次（[接入必读](https://docs.volcengine.com/docs/doubao-voice/podcast-mustread?lang=zh)续传要求），未完成轮次另存诊断文件且不参与续传，不将部分音频等同完整成功。
- 同传：AST的model不是请求中可随意更换的LLM ID，而是专属资源10053。100→150、200携PCM、102→152；服务器失败立即取消sender。官方 source_audio.format 字段为 wav；Python demo 按原始文件字节分块直接发送。正文 TaskRequest 与使用步骤明确要求 16kHz/16bit/单声道 wav/pcm，本地按 PCM 路径剥离 WAV 容器符合其中 PCM 描述；未做实际账号验证，不能声称与 demo 字节交付完全一致。protobuf source精确字段编号优先于旧demo生成文件。
- 实时：mode=legacy的Seeduplex 3.0为model=1.2.6.1；mode=seed的Seed-Realtime 1.0为独立入口和model=1.3.0.0（图像/状态/取消见2026-10-23节）；输入pcm/speech_opus16k，输出pcm/pcm_s16le/ogg_opus24k。JSON type为官方契约；不能复用旧端到端V2二进制协议。`response.done`含一轮usage；`session.closed`是关闭ack。
- Seed Audio：当前[接口](https://docs.volcengine.com/docs/doubao-voice/audio-generation-http?lang=zh)仍只列 `seed-audio-1.0`。官网已有[1.5营销合作计划](https://docs.volcengine.com/docs/doubao-voice/audio1-5marketingplan?lang=zh)，但它不提供API model ID或账号开放契约，**无法据此核实1.5可调用**，本次不擅自改默认模型。

## 历史白名单逐路核实

旧接口鉴权为 `Authorization: Bearer; <Access Token>`（包含分号），AppID在query、app对象或flat body中的位置按官方旧产品不同；cluster由账号开通服务决定。没有把Access Token当作API Key。老TTS仅返回一次完整base64音频，老ASR/subtitle采用提交/查询；pending与task_status单独解读。

| operation | method + endpoint | 官方来源 |
|---|---|---|
| subtitle_submit | POST `/api/v1/vc/submit`，query.appid | [字幕](https://docs.volcengine.com/docs/doubao-voice/audio-video-sub-title-gene-ration?lang=zh) |
| subtitle_query | GET `/api/v1/vc/query`，query.appid/id | 同上 |
| alignment_submit | POST `/api/v1/vc/ata/submit`，query.appid/caption_type，body.url/audio_text | [打轴](https://docs.volcengine.com/docs/doubao-voice/automatic-sub-title-typing?lang=zh) |
| alignment_query | GET `/api/v1/vc/ata/query` | 同上 |
| tts | POST `/api/v1/tts`，body.app.appid/token/cluster | [小模型](https://docs.volcengine.com/docs/doubao-voice/http-interface-one-time-composition-non-streaming?lang=zh)、[大模型V1](https://docs.volcengine.com/docs/doubao-voice/http-one-timecompositenon-streaming-interface-v1-not-recommended?lang=zh) |
| tts_async_submit | POST `/api/v1/tts_async/submit` | [旧长文本](https://docs.volcengine.com/docs/doubao-voice/api-interface-documentation-2?lang=zh) |
| tts_async_query | GET `/api/v1/tts_async/query`，query.appid/task_id | 同上 |
| tts_emotion_submit | POST `/api/v1/tts_async_with_emotion/submit` | 同上 |
| tts_emotion_query | GET `/api/v1/tts_async_with_emotion/query` | 同上 |
| asr_submit | POST `/api/v1/auc/submit`，body.app | [旧录音识别](https://docs.volcengine.com/docs/doubao-voice/AudioFileRecognitionStandardEdition?lang=zh) |
| asr_query | POST `/api/v1/auc/query`，body.appid/token/cluster/id | 同上 |

## 控制面与词表

OpenAPI主机、签名service、region、Action和Version逐项依据正文请求示例核实。默认25个Action使用POST、cn-beijing、speech_saas_prod，下面每行链接均是本轮成功取得的官方正文。

| Action | Version | 官方正文 |
|---|---|---|
| `ActivateService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/activate-service-activate-service?lang=zh) |
| `AliasResourcePack` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/alias-resource-pack-update-sound-resource-aliases?lang=zh) |
| `BatchListMegaTTSTrainStatus` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/batch-list-mega-tts-train-status-page-query-speaker-id-status?lang=zh) |
| `CreateAPIKey` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/create-api-key-create-api-key?lang=zh) |
| `DeleteAPIKey` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/delete-api-key-delete-api-key?lang=zh) |
| `FormalizeResourcePacks` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/formalize-resource-packs-conversion-effect-package?lang=zh) |
| `ListAPIKeys` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/list-api-keys-pull-api-key-list?lang=zh) |
| `ListBigModelTTSTimbres` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/list-big-model-tts-timbres-large-model-sound-list?lang=zh) |
| `ListMegaTTSByOrderID` | `2023-11-07` | [文档](https://docs.volcengine.com/docs/doubao-voice/list-mega-tts-by-order-id-query-purchased-sounds-by-order-id?lang=zh) |
| `ListMegaTTSTrainStatus` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/list-mega-tts-train-status-query-speaker-id-status-information?lang=zh) |
| `ListSpeakers` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/list-speakers-large-model-sound-list-new-interface?lang=zh) |
| `ListTagsForResources` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/list-tags-for-resources-query-all-labels-attached-to-are-source?lang=zh) |
| `OrderAccessResourcePacks` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/order-access-resource-packs-sound-order?lang=zh) |
| `OrderResourcePacks` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/order-resource-packs-buyeffectspackage?lang=zh) |
| `PauseService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/pause-service-suspend-service?lang=zh) |
| `QuotaMonitoring` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/quota-monitoring-quota-query-interface?lang=zh) |
| `RenewAccessResourcePacks` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/renew-access-resource-packs-tone-renewal?lang=zh) |
| `ResourcePacksStatus` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/resource-packs-status-effect-package-status-information?lang=zh) |
| `ResumeService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/resume-service-re-enable-the-service?lang=zh) |
| `ServiceStatus` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/service-status-service-status?lang=zh) |
| `TagResources` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/tag-resources-attach-tags-to-resources?lang=zh) |
| `TerminateService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/terminate-service-deactivate-service?lang=zh) |
| `UntagResources` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/untag-resources-remove-tags-from-resources?lang=zh) |
| `UpdateAPIKey` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/doubao-voice/update-api-key-update-api-key?lang=zh) |
| `UsageMonitoring` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/doubao-voice/usage-monitoring-call-query-interface?lang=zh) |

旧监控接口 `QuotaMonitoring` / `UsageMonitoring` 的 `2021-08-30` 版本走GET、cn-north-1，[旧并发](https://docs.volcengine.com/docs/doubao-voice/qps-concurrent-query-interface-description?lang=zh)、[旧用量](https://docs.volcengine.com/docs/doubao-voice/call-volume-query-interface-description?lang=zh)均有示例。`ListApplications` 的 `2021-11-22` 版本GET/cn-north-1依据词表正文；它不在默认版本表中，调用时明确version。任意自行输入的Action/Version不可能仅凭“支持透传”就视为已核实。

热词Action：ListBoostingTableLimits、CreateBoostingTable、CheckBoostingTableName、UpdateBoostingTable、DeleteBoostingTable、ListBoostingTable、GetBoostingTable。替换词Action：CreateCorrectTable、CheckCorrectTableName、UpdateCorrectTable、DeleteCorrectTable、ListCorrectTable、GetCorrectTable。两组13个名字均在各自正文找到；Create/Update为multipart File，UTF-8文件小于8MB。API-Key热词代理路由官方明确支持；替换词仅确认AK/SK路线。术语词表正文只提供控制台创建，并通过corpus.glossary_list/table_id/table_name使用，不将其推断为未公开CRUD API。

## 官方材料之间的差异与无法核实项

1. [模型总表](https://docs.volcengine.com/docs/doubao-voice/model-list?lang=zh)对Seed Audio 1.0只概括中英文、若干采样率；更具体的当前音频API正文列更多语种以及40000/44100等采样率。具体请求验证按接口正文，不能用总表粗略行覆盖接口枚举；语种和声音表现仍需真实样本验收。
2. 同传本轮从正文附带的[protos.tar.gz](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/6493ecf3887246e3a99968961f716499~tplv-goo7wpa0wc-image.image)看到新字段，但同页[Python demo zip](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f5a5a20f3ae441a49195c2b192c2cf93~tplv-goo7wpa0wc-image.image)的ast_service_pb2仍无detected_language。已按原始proto重新生成，没有依据文档文字手写猜测字段编号。
3. 新版部分ASR字段表将result写成list，旧详细协议样例展示object；本次保留旧样例支持的既有object解析与高级raw完整响应，不把表格标题单独解释为线上schema迁移。未进行账号请求，无法断定全部响应场景形态。
4. 声音复刻自定义speaker命名规则、可用训练次数和后付费转正依赖控制台/具体账号。便捷工具的音色启发式不能证明音色资源授权；预付费槽、后付费custom_speaker_id、跨语种能力不通过真实付费调用猜测。
5. 没有查询IAM账户、API Key、音色库、QPS配额，也没有发真实data/admin请求。因此确认的是**官方公开契约与本地路径映射**，不是所有模型、所有资源、所有账号或历史接口当前权限均已通过线上验证。
6. 公开正文API没有正式稳定性保证；MDContent空、目录节点、错误JSON、HTML空壳必须作为获取失败处理；不存在“任意网页追加.md就能取最新文档”的通用规则。

本轮下载的网页/正文和proto均为官方公开资源；临时分析文件在结束时清理。持久证据保存为正文指纹与来源列表，不把完整官方文章或凭据复制进仓库。
