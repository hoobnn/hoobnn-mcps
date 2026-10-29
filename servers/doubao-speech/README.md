<div align="center">

# doubao-speech-mcp

豆包语音的 MCP server。

[![PyPI](https://img.shields.io/pypi/v/doubao-speech-mcp?style=flat-square)](https://pypi.org/project/doubao-speech-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE)

**简体中文** · [English](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/doubao-speech/README.en.md)

</div>

豆包语音云 API 的 stdio MCP server。接口依据[官方目录](https://docs.volcengine.com/docs/doubao-voice)于 2026-10-10 核对。

`0.5.2` 对齐 2026-10-29 官方文档：Seed-Realtime 现文档化客户端 `response.cancel` 打断，放开此前的本地拦截；流式识别不再发送官方已移除说明的 `audio.codec`，并补齐剩余旧文档链接。

`0.5.1` 更新火山文档迁移后的官方链接，工具帮助和使用示例同步使用当前文档库名与 slug；语音请求协议保持不变。

`0.5.0` 将播客默认通道改为 HTTP SSE，持久保存真实会话 ID、完整轮次与续传回执；需要历史通道时显式传 `transport="websocket"`。实时会话新增 `mode="seed"` 的图像 / 视频帧输入及取消播放状态，原 `legacy` 模式仍为默认。

`0.4.0` 按用途重组工具：一件事只有一个入口，常用能力全部是具名参数，只剩 `speech_raw_request` 需要手写官方 JSON。默认暴露 18 个工具（原 29 个）；实时会话和管理接口改为按需启用。这是不兼容变更，旧工具名不保留别名，对照见下方[迁移](#从-03x-迁移)。

| 工具 | 作用 | 接口 / 模型 |
|---|---|---|
| `text_to_speech` | 语音合成：2.0 音色、语音指令、8 种方言、30+ 语种、读音修正、SRT 字幕；超过 5000 字自动改走异步长文本（最多 10 万字） | 同步单向流式 HTTP / 异步长文本，`seed-tts-2.0`（复刻音色自动用 `seed-icl-2.0`） |
| `generate_audio` | 音频生成：按描述生成音效、配乐、多角色对白混合的音频，最长 120 秒，可参考音色、音频或图片 | `seed-audio-1.0` |
| `generate_podcast` | 双人播客：`text` 文章 / `url` 链接 / `topic` 联网话题 / `dialogue` 逐轮脚本；可只出脚本 | HTTP SSE（默认）/ 历史 WebSocket 可选 |
| `speech_to_text` | 录音识别：`flash` 同步（100MB / 2 小时）；`standard` / `idle` 异步（URL，512MB / 5 小时，支持说话人分离） | 极速版 / 标准版 / 闲时版 |
| `summarize_meeting` | 妙记：转写加全文总结、章节、待办、问答、翻译，开关式参数；结果 JSON 自动下载 | 异步 HTTP |
| `translate_text` | Seed-X 机器翻译，`glossary` 指定术语，自动检测语种 | 一次 1–16 条文本 |
| `interpret_audio` | 同传 2.0：S2T 字幕 / S2S 语音，热词、术语、目标音色 | WebSocket + 官方 Protobuf |
| `clone_voice` / `design_voice` / `get_voice` / `upgrade_voice` | 声音复刻、音色设计、训练状态查询、升级 | 新版 V3 HTTP |
| `list_jobs` / `get_job` / `recover_job` | 异步任务（长文本、标准识别、妙记）查进度、自动保存结果、修复交付 | 本地任务记录 |
| `speech_raw_request` | 兜底：HTTP 合成 / 极速识别 / 音频生成、WebSocket 合成、流式识别、历史接口，按官方请求体原样调用 | 固定端点 |
| `list_speech_capabilities` / `get_speech_usage_examples` | 产品目录、未启用的工具组及启用方法、官方模板归纳和调用示例 | 本地查询，不计费 |

按需启用（设 `MCP_TOOL_GROUPS` 后重启，如 `speech,voice,jobs,help,realtime`）：

| 工具组 | 工具 | 默认不开的原因 |
|---|---|---|
| `realtime` | `open_realtime_session` / `send_realtime_event` / `receive_realtime_events` / `close_realtime_session` | 持久会话要逐轮发送和接收，适合专门的语音应用 |
| `admin` | `manage_word_table`（热词 / 替换词表）、`speech_console`（控制台 OpenAPI） | 需要 IAM AK/SK，可创建、删除和下单 |

所有具名参数工具都有 `parameters`：官方请求体里工具没单独列出的字段（SSML、水印、bit_rate、`ssd_version` 等）深度合并进去，同名以 `parameters` 为准；TTS 的 `req_params.additions` 可直接写成对象。提交类调用只提交一次，查询不会重新提交或购买资源。

## 安装

```bash
uv tool install doubao-speech-mcp
```

命令装在 `~/.local/bin/doubao-speech-mcp`。各客户端的配置方法见 [仓库 README](https://github.com/hoobnn/hoobnn-mcps#配置客户端)。

## 环境变量

| 变量 | 说明 |
|---|---|
| `VOLC_SPEECH_API_KEY` | 必需，豆包语音控制台 › API Key 管理（新版控制台单 key 鉴权），并开通对应服务 |
| `VOLC_ACCESS_KEY_ID` / `VOLC_SECRET_ACCESS_KEY` | IAM AK/SK，控制台 API 与替换词管理需要；区别于语音 API Key |
| `VOLC_SPEECH_APP_ID` / `VOLC_SPEECH_ACCESS_TOKEN` | 历史产品（如字幕）的旧版凭据，不自动拿新版 Key 替代 |
| `DOUBAO_SPEECH_OUT_DIR` | 音频输出目录，默认 `~/Downloads/doubao-speech` |
| `DOUBAO_SPEECH_JOB_DIR` | 异步任务记录，默认 `~/.local/share/doubao-speech-mcp/jobs` |
| `VOLC_SPEECH_BASE_URL` | 默认 `https://openspeech.bytedance.com` |

音频生成和播客可能超过 300 秒，需同时提高客户端超时和服务端 `MCP_TOOL_TIMEOUT_SEC`（最高 3600）；SSE 按该总预算读取，不再固定截断于 300 秒。异步任务提交前先写本地记录，`get_job` 完成时自动把官方临时 URL 的结果下载到输出目录。

本地运行与验证：

```bash
uv sync --project servers/doubao-speech
uv run --project servers/doubao-speech doubao-speech-mcp
servers/doubao-speech/.venv/bin/python -m unittest discover -s servers/doubao-speech/tests -v
```

MCP 客户端本地启动命令可指定本项目 `.venv/bin/doubao-speech-mcp` 的绝对路径。已安装的 GitHub 版本需在发布后升级并重启客户端，源码修改不会自动替换已经运行的 server。

## 调用示例

完整示例与技巧见 [使用指南](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/doubao-speech/docs/usage-examples.md)。MCP 内可直接调用 `get_speech_usage_examples`，返回官方模板分析、工具参数、技巧和来源链接：

```json
{"product": "audio", "category": "timing"}
```

`product` 支持 `audio`、`tts`、`voice`、`podcast`、`asr`、`translation`、`minutes`、`realtime`；仅 `audio` 支持 `category=text/reference/timing/multilingual`。省略分类返回该产品全部示例。示例为根据官方用法改写，文件路径、URL、分配音色 ID、会话 ID 需替换；查询示例不会上传或生成音频。

### 音频生成 1.0：官方四类用法

2026-10-09 核对[官方体验中心的模板分类](https://console.volcengine.com/speech/new/experience/audio?projectName=default)：文本生成、参考生成、时间控制、多语种。四类均使用 `generate_audio`，可以组合使用；以下 JSON 是 MCP 工具参数，示例提示词为根据官方用法改写，未做真实云端生成验证。

| 官方分类 | 写法与 MCP 参数 | 官方模板举例 |
|---|---|---|
| 文本生成 | `prompt` 按顺序描述角色、台词、环境声、配乐与音效 | 悬疑刑侦片、宫廷试药、双人播客对谈 |
| 参考生成 | `reference_audios` 提供样音，`prompt` 用 `@音频1`、`@音频2` 引用；说明参考音色、情感、风格、节奏 | 带货双人、警局对峙、多角演绎 |
| 时间控制 | `prompt` 写总时长及 `[开始秒s:结束秒s]`，支持小数秒 | 控制音效卡点、控制情绪递进、控制叙事转场、控制旁白推进 |
| 多语种 | `prompt` 直接使用目标语言台词，说明语言、口音、角色与表演方式 | 英语、日语、韩语、法语等模板 |

文本生成：先定义角色和场景，再按发生顺序编排声音；台词用引号，区分台词与表演指令。

```json
{
  "prompt": "雨声持续。青年女子嗓音清亮，紧张地说：‘有人来了。’随后响起三声敲门声，低音弦乐渐强。",
  "model": "seed-audio-1.0",
  "format": "mp3"
}
```

参考生成：样音列表的第一条对应 `@音频1`，第二条对应 `@音频2`。多人对白要明确每个角色的引用关系；下列绝对路径需替换为真实文件，也可以传可访问的音频 URL。最多 3 段，每段不超过 30 秒、10MB。

```json
{
  "prompt": "主持人甲参考@音频1的音色，热情地说：‘欢迎。’主持人乙参考@音频2的音色，轻笑着说：‘你好。’随后两人自然地笑起来。",
  "reference_audios": ["/absolute/path/host_a.wav", "/absolute/path/host_b.wav"],
  "format": "mp3"
}
```

需要指定现有音色时可用 `speaker`；图片参考用 `reference_image`（本地绝对路径或 URL），不能与 `speaker` 或 `reference_audios` 混用。图片参考是 API 支持的另一种输入方式，不是体验中心第五个模板分类。

时间控制：官方输入提示使用 `[2s:5s]`，音效卡点模板使用 `[2.7s:5.7s]` 等小数秒区间。将标记写在对应台词或声音事件前，同时描述停顿、情绪递进、转场和声音强弱。

```json
{
  "prompt": "总长10秒，雨声持续。女子轻声说道：[2.7s:5.7s]‘你终于回来了。’[6s:7s]响起敲门声，最后雨声渐弱。",
  "subtitles": true,
  "format": "mp3"
}
```

区间标记随 `prompt` 原样传给官方 `text_prompt`；没有独立的 `timeline` 参数，也不在 MCP 内做音频裁切或强制对齐。`subtitles=true` 返回的是生成后的人声字幕，`subtitle.sentences` 及其 `words` 的 `start_time` / `end_time` 单位为毫秒，不标注所有音效。实际时间落点需核对音频与字幕；不要把提示词控制理解为每次严格命中指定时间。单次最长 120 秒，台词过长或区间过短可能影响节奏。

多语种：目标语言台词配合角色、口音和表演说明；不需要额外的 `language` 参数。官方英语模板用英文描述人物声线、标准美式英语、情绪、环境音和配乐。

```json
{
  "prompt": "A young woman speaks warm, clear American English: ‘Welcome home.’ Soft piano continues underneath. A young man replies quietly: ‘It is good to be back.’",
  "format": "mp3",
  "subtitles": true
}
```

语言支持清单以[官方音频生成 API](https://docs.volcengine.com/docs/doubao-voice/audio-generation-http?lang=zh)为准，控制台模板展示与 API 列举可能不同。四类用法及参数示例也已写入 `generate_audio` 的工具描述，客户端发现工具时即可读取。

### 长文本、识别与妙记

长文本合成（超过 5000 字自动异步，`long_text=true` 强制）：

```json
{"text": "长文本……", "voice": "zh_female_vv_uranus_bigtts", "long_text": true}
```

立即返回 `job_id`；`get_job(job_id=..., wait=30)` 查询，完成后 `speech.mp3` 保存到输出目录。异步模式 `format` 只能是 mp3 / pcm / ogg_opus，`subtitles` 输出 `sentences.json`。

会议录音区分说话人（自动用标准版，音频须是可下载 URL）：

```json
{"audio": "https://example.com/meeting.wav", "speakers": true, "parameters": {"request": {"ssd_version": "300"}}}
```

妙记：

```json
{"file_url": "https://example.com/meeting.wav", "summary": true, "chapters": true, "todos": true}
```

`bundle_billing`（官方 `AllActivate`）只选择打包计费，不会开启功能。复刻先用 `clone_voice` 注册已分配的 `S_` 音色，`get_voice` 查训练结果，再 `text_to_speech(voice="S_...")` 合成。

### 实时会话（需启用 `realtime` 组）

最简配置：

```json
{"session":{"audio":{"output":{"voice":"zh_female_vv_jupiter_bigtts"}}}}
```

1. 使用返回的客户端 `session_id`，通过 `send_realtime_event` 发送 `input_audio_buffer.append` 与 `audio_file`（16kHz / mono / int16 裸 PCM），或事件里的 Base64 `audio`。
2. 发送 `input_audio_buffer.commit` 强制判停，或由服务端判断停顿。
3. `receive_realtime_events` 接收转写、回复、音频路径、工具调用和用量。音频 delta 自动落盘，附格式和采样率，不返回巨大 Base64。
4. 调用者执行 Function Calling，再通过 `conversation.item.create` 回传 `role=tool` 和对应 `call_id`。`response.cancel` 可主动打断进行中的回复（两种模式均可）；上下文增删查和 `session.update` 两种模式均可用。
5. `close_realtime_session` 等待关闭确认并释放连接；MCP 退出也会清理全部会话。

实时上传 20ms 一包。MCP 不直接采集麦克风、播放声音或驱动声卡，客户端负责设备输入输出。同传需 16kHz / mono / 16bit WAV 或 PCM；WAV 自动去容器。目标 PCM16k 保存有效 WAV，PCM24k 保留 float32 原始 PCM 并返回格式信息。

官方[接入必读](https://docs.volcengine.com/docs/doubao-voice/access-must-read?lang=zh) 现已补充输入质量要求（2026-10-26 复核）：纯人声 RMS 推荐 −31.7～−23.9 dBFS（目标约 −27.6），准入范围 −37～−19.5 dBFS，峰值 ≤−1 dBFS；纯背景噪声 RMS 推荐 ≤−50 dBFS（目标约 −52.6），SNR 推荐 20～30 dB，最低要求为噪声 ≤−45 dBFS 且 SNR ≥15 dB。客户端负责采集与质量控制；MCP 不自动增益、降噪或从混合音频估算纯人声/纯噪声 RMS。麦克风停采且不再发音频帧时发送 `input_audio_mute.commit`，恢复时发送 `input_audio_unmute.commit`，避免保活超时。

`mode=legacy` 为兼容默认值：`/api/v3/duplex/realtime/dialogue` + `model=1.2.6.1`。新模式 `mode=seed` 使用 `/api/v3/seedrealtime` + `model=1.3.0.0`，不能仅在旧模式换 model。图像配置在 **`extension.video`**：

```json
{"mode":"seed","session":{"audio":{"output":{"voice":"zh_female_vv_jupiter_bigtts"}}},"extension":{"video":{"frame_format":"JPEG","frame_rate":"2"}}}
```

用 `send_realtime_event` 发送 `{"type":"input_image_buffer.append","frame_id":"frame_1"}`，并传 `image_file` 本地 PNG/JPEG，或在事件中传 Base64 `image`；编码必须匹配 `extension.video.frame_format`。图像至多 2 FPS，工具独立节流，不阻塞音频 20ms 节奏；单个 JSON 事件本地上限 2MB。Seed 模式同样可发送 `response.cancel`，服务端也会经 VAD 通过 `response.canceled` 打断。播放状态只看 `response.created/canceled/done`；ASR 事件只用于转写。`receive_realtime_events` 的 `clear_playback_buffer=true`（即使取消事件因队列拥塞被丢弃也会保留）要求客户端立即停播并清空已缓冲音频。

`generate_podcast` 默认 `transport="sse"`，向 `/api/v3/podcast/sse` 一次 POST；`transport="websocket"` 保留历史接口。SSE 只有收到 **152 且 `code=20000000`** 才成功，HTTP 200、363 和 usage 均不能提前结束。`task_id` 是首次 150 返回的真实 `session_id`；续传返回新的 `session_id`，`task_id` 始终保留首次值。

SSE 在提交前、150 和每个完整 362 时保存 `progress_file`（原请求、真实任务 ID、完整轮次和续传信息，无凭据）。断线、超时、轮次失败、151 取消或 MCP 取消时，`.partial.*` 只含已写成的完整轮次；未完成分片另存 `diagnostic_file`，不可拼入续传结果。音频保存失败不会把 `retry_info` 推进到未落盘轮次。按原请求加 `parameters.retry_info={"retry_task_id":"首次task_id","last_finished_round_id":最后完整轮次}` 显式续传；不自动重新提交或合并文件，需按完整片段时长调整续传时间轴。

音色列表中备注「仅限单向流」的 27 个外语音色，`speech_raw_request(product='tts_websocket')` 默认的双向流会在本地直接拒绝，需传 `mode='unidirectional'`；`text_to_speech` 走单向流 HTTP，不受影响。

### 从 0.3.x 迁移

| 旧工具 | 现在 |
|---|---|
| `submit_long_text_speech` / `query_long_text_speech` | `text_to_speech(long_text=true)` + `get_job` |
| `websocket_text_to_speech` | `speech_raw_request(product="tts_websocket")` |
| `speech_http_request` | `speech_raw_request(product="tts" / "asr_flash" / "audio")` |
| `submit_transcription` / `query_transcription` | `speech_to_text(mode="standard" / "idle")` + `get_job` |
| `streaming_speech_to_text` | `speech_raw_request(product="asr_stream")` |
| `submit_minutes` / `query_minutes` | `summarize_meeting` + `get_job` |
| `query_voice` | `get_voice` |
| `legacy_speech_request` | `speech_raw_request(product="legacy", operation=...)` |
| `clone_voice` / `design_voice` / `upgrade_voice` / `generate_podcast` / `translate_text` / `interpret_audio` 的 `request` 参数 | 具名参数，其余字段放 `parameters` |
| 实时会话、`manage_word_table`、`speech_console` | 同名，需在 `MCP_TOOL_GROUPS` 启用 `realtime` / `admin` |

`clone_voice.language` 现在接受 `zh`、`en` 等代码并转换为官方整数枚举；旧版示例里的字符串写法不符合官方契约。

## 官方来源与覆盖边界

新增接口来源包括[长文本提交](https://docs.volcengine.com/docs/doubao-voice/task-sub-mission?lang=zh)、[音色注册](https://docs.volcengine.com/docs/doubao-voice/tone-training-http?lang=zh)、[音色设计](https://docs.volcengine.com/docs/doubao-voice/sound-design-api?lang=zh)、[实时识别](https://docs.volcengine.com/docs/doubao-voice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)、[播客 SSE](https://docs.volcengine.com/docs/doubao-voice/podcast?lang=zh)、[实时 3.0](https://docs.volcengine.com/docs/doubao-voice/end-to-end-real-time-voice-full-duplex-version?lang=zh)、[同传](https://docs.volcengine.com/docs/doubao-voice/simultaneous-interpretation2-0-api-access-documentation?lang=zh)、[机器翻译](https://docs.volcengine.com/docs/doubao-voice/machine-translation-large-model-api-access-documentation?lang=zh)、[妙记](https://docs.volcengine.com/docs/doubao-voice/doubao-voice-minutes-api-access-documentation?lang=zh)、[热词](https://docs.volcengine.com/docs/doubao-voice/hot-word-management-api-v10?lang=zh)、[替换词](https://docs.volcengine.com/docs/doubao-voice/replacement-word-api-v11?lang=zh)及[控制台 OpenAPI](https://api.volcengine.com/api-docs/view?action=ActivateService&serviceCode=speech_saas_prod&version=2025-05-20)。

Speech SDK 的离线模型、端侧 VAD / 音频处理和 Android / iOS 接入需原生应用，不能等同于云 MCP。术语词表 CRUD 官方仅公开控制台流程；翻译 / 同传通过 `glossary`、`glossary_table_id`（或 `parameters` 里的 `glossary_table_name`）使用术语。同传官方附件的 Protobuf 尚未声明文档新增的 `detected_language`，本版不猜字段编号。

历史产品使用独立工具与旧版凭据，返回各操作的精确官方 `source` 链接。传统 `/api/v2/asr` 旧 WebSocket 协议未重复实现；一句话和流式识别功能通过现行大模型接口提供。实时对话提供 Seed-Realtime 1.0 与兼容 Seeduplex 3.0，未复制旧 1.0 / 2.0 二进制会话协议。所有产品覆盖不等于每个历史 SDK / 协议版本都已适配。

`_ast/` 的 Protobuf bindings 来自同传官方 Python 示例，生成日期 2026-06-12，调整为包内相对 import；运行依赖 `mcp`、`websockets`、`protobuf`。

离线测试覆盖 HTTP 合同、任务状态、签名、Protobuf、二进制帧、模拟 WebSocket 收发、音频文件、超时 / 取消清理，以及实际 stdio MCP 初始化、工具发现与调用。未调用付费云接口，因此不能证明账号开通、配额可用或实际生成质量。

参数说明见工具描述（`src/doubao_speech_mcp/server.py`）。接口细节以官方文档为准：[单向流式语音合成](https://docs.volcengine.com/docs/doubao-voice/unidirectional-streaming-text-to-speech-http)、[录音文件识别极速版](https://docs.volcengine.com/docs/doubao-voice/recording-file-recognition-lite-http)、[音频生成](https://docs.volcengine.com/docs/doubao-voice/audio-generation-http)、[音色列表](https://docs.volcengine.com/docs/6561/1257544)。

## 运行时与稳定性

共享连接池、总超时、工具分组、错误语义和迁移说明见 [MCP 构建与稳定性](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md)。完整工具说明可调用 `get_tool_help(tool="工具名")`。

## 许可证

[MIT](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE) © 2026 hoobnn。可自由使用、修改和分发，需保留版权声明。
