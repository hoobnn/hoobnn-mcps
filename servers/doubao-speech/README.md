# doubao-speech-mcp

豆包语音云 API 的 stdio MCP server。接口依据[官方目录](https://docs.volcengine.com/docs/DoubaoVoice/list?lang=zh)于 **2026-10-09** 核对。原有工具保持兼容，新增 HTTP 异步任务、WebSocket 流式接口、实时持久会话与管理 API。

`0.3.1` 修复 Python 3.10 下流式识别和同传的异步超时处理；本地 Python 3.10 与当前环境的 125 项语音测试均通过。

| 工具 | 作用 | 接口 / 模型 |
|---|---|---|
| `text_to_speech` | 语音合成：2.0 音色、自然语言语音指令、8 种方言、30+ 语种、读音修正、SRT 字幕，长文本自动分段拼接 | 单向流式 HTTP，`seed-tts-2.0`（复刻音色自动用 `seed-icl-2.0`） |
| `speech_to_text` | 录音文件识别：同步返回，100MB / 2 小时以内，热词、上下文、分句和说话人 | 录音文件识别极速版，`volc.bigasr.auc_turbo` |
| `generate_audio` | 音频生成：按描述生成音效、配乐、多角色对白混合的音频，最长 120 秒，可参考音色、音频或图片 | `seed-audio-1.0` |
| `speech_http_request` | 合成、极速识别、音频生成的完整官方请求透传；支持 SSML、水印、bit_rate、视觉上下文等高级参数；音频落盘 | `product=tts/asr_flash/audio`，固定端点 |
| `websocket_text_to_speech` | 单向 / 双向 WebSocket 合成，双向支持 `text_chunks` 顺序输入；返回字幕、usage及本地音频 | `mode=unidirectional/bidirectional` |
| `submit_long_text_speech` / `query_long_text_speech` | 异步长文本提交、单次查询；最多100000字符 | TTS / ICL 2.0 |
| `clone_voice` / `query_voice` / `upgrade_voice` | 声音复刻音色注册、查询、升级；支持本地训练音频 | 新版 V3 HTTP |
| `design_voice` | 文本 / 图片设计音色，支持本地图片 | 新版 V3 HTTP |
| `submit_transcription` / `query_transcription` | 标准 / 闲时录音识别，返回任务ID及完整状态、分句、说话人 | `mode=standard/idle` |
| `streaming_speech_to_text` | 一句话 / 实时流式识别，WAV / PCM 分包并发收发 | `mode=sentence/realtime` |
| `generate_podcast` | 双人播客：文章 / URL / 对话脚本 / 联网话题；字幕轮次、用量、断点信息 | `action=0/3/4` |
| `translate_text` | Seed-X 机器翻译，支持术语词表、自动检测语种、token用量 | 一次1–16条文本 |
| `interpret_audio` | 同传 2.0：S2T / S2S、原声复刻，字幕和目标音频 | WebSocket + 官方 Protobuf |
| `open_realtime_session` / `send_realtime_event` / `receive_realtime_events` / `close_realtime_session` | 实时 3.0：持久会话、Function Calling、打断、上下文、唱歌及联网等官方事件 | Seeduplex JSON 协议 |
| `submit_minutes` / `query_minutes` | 妙记：转写、翻译、提取、摘要和章节；显式选择计费功能 | 异步 HTTP |
| `manage_word_table` | 热词 / 替换词词表 CRUD | API Key 代理 / IAM 签名 |
| `speech_console` | 音色、API Key、服务、资源包、复刻订单、用量、配额及标签 | 官方 AK/SK OpenAPI |
| `legacy_speech_request` | 历史字幕生成 / 字幕打轴、传统 TTS / ASR、普通 / 情感长文本 | 11 个旧版 HTTP 操作，AppID / Access Token |
| `list_speech_capabilities` | 产品工具、管理 Action、官方链接、接入边界 | 本地查询，不计费 |
| `get_speech_usage_examples` | 官方模板归纳、可改写调用示例和技巧，覆盖8类产品；音频生成可按4类筛选 | 本地查询，不计费 |

常用参数有简洁工具，高级参数通过 `request` / `event` / `parameters` 完整透传，不丢弃官方可选字段。查询工具每次查询一次，不自动重投或购买资源。`speech_console` 会执行指定 Action，包括创建、删除、停用和下单，调用者需明确选择。

## 环境变量

| 变量 | 说明 |
|---|---|
| `VOLC_SPEECH_API_KEY` | 必需，豆包语音控制台 → API Key 管理（新版控制台单 key 鉴权），并开通对应服务 |
| `VOLC_ACCESS_KEY_ID` / `VOLC_SECRET_ACCESS_KEY` | IAM AK/SK，控制台 API 与替换词管理需要；区别于语音 API Key |
| `VOLC_SPEECH_APP_ID` / `VOLC_SPEECH_ACCESS_TOKEN` | 历史产品（如字幕）的旧版凭据，不自动拿新版 Key 替代 |
| `DOUBAO_SPEECH_OUT_DIR` | 音频输出目录，默认 `~/Downloads/doubao-speech` |
| `VOLC_SPEECH_BASE_URL` | 默认 `https://openspeech.bytedance.com` |

音频生成和播客可能超过300秒，客户端需设置相应超时。长实时会话用多次发送 / 接收工具调用维持。输出音频保存在本地；异步结果保留官方临时URL，应及时下载。

本地运行与验证：

```bash
uv sync --project servers/doubao-speech
uv run --project servers/doubao-speech doubao-speech-mcp
servers/doubao-speech/.venv/bin/python -m unittest discover -s servers/doubao-speech/tests -v
```

MCP 客户端本地启动命令可指定本项目 `.venv/bin/doubao-speech-mcp` 的绝对路径。已安装的 GitHub 版本需在发布后升级并重启客户端，本次源码修改不会自动替换已经运行的 server。

## 调用示例

完整示例与技巧见 [使用指南](docs/usage-examples.md)。MCP 内可直接调用 `get_speech_usage_examples`，返回官方模板分析、工具参数、技巧和来源链接：

```json
{"product": "audio", "category": "timing"}
```

`product` 支持 `audio`、`tts`、`voice`、`podcast`、`asr`、`translation`、`minutes`、`realtime`；仅 `audio` 支持 `category=text/reference/timing/multilingual`。省略分类返回该产品全部示例。示例为根据官方用法改写，文件路径、URL、分配音色 ID、会话 ID 需替换；查询示例不会上传或生成音频。

### 音频生成 1.0：官方四类用法

2026-10-09 核对[官方体验中心的模板分类](https://console.volcengine.com/speech/new/experience/audio?projectName=default)：**文本生成、参考生成、时间控制、多语种**。四类均使用 `generate_audio`，可以组合使用；以下 JSON 是 MCP 工具参数，示例提示词为根据官方用法改写，未做真实云端生成验证。

| 官方分类 | 写法与 MCP 参数 | 官方模板举例 |
|---|---|---|
| 文本生成 | `prompt` 按顺序描述角色、台词、环境声、配乐与音效 | 悬疑刑侦片、宫廷试药、双人播客对谈 |
| 参考生成 | `reference_audios` 提供样音，`prompt` 用 `@音频1`、`@音频2` 引用；说明参考音色、情感、风格、节奏 | 带货双人、警局对峙、多角演绎 |
| 时间控制 | `prompt` 写总时长及 `[开始秒s:结束秒s]`，支持小数秒 | 控制音效卡点、控制情绪递进、控制叙事转场、控制旁白推进 |
| 多语种 | `prompt` 直接使用目标语言台词，说明语言、口音、角色与表演方式 | 英语、日语、韩语、法语等模板 |

**文本生成**：先定义角色和场景，再按发生顺序编排声音；台词用引号，区分台词与表演指令。

```json
{
  "prompt": "雨声持续。青年女子嗓音清亮，紧张地说：‘有人来了。’随后响起三声敲门声，低音弦乐渐强。",
  "model": "seed-audio-1.0",
  "format": "mp3"
}
```

**参考生成**：样音列表的第一条对应 `@音频1`，第二条对应 `@音频2`。多人对白要明确每个角色的引用关系；下列绝对路径需替换为真实文件，也可以传可访问的音频 URL。最多3段，每段不超过30秒、10MB。

```json
{
  "prompt": "主持人甲参考@音频1的音色，热情地说：‘欢迎。’主持人乙参考@音频2的音色，轻笑着说：‘你好。’随后两人自然地笑起来。",
  "reference_audios": ["/absolute/path/host_a.wav", "/absolute/path/host_b.wav"],
  "format": "mp3"
}
```

需要指定现有音色时可用 `speaker`；图片参考用 `reference_image`（本地绝对路径或URL），不能与 `speaker` 或 `reference_audios` 混用。图片参考是 API 支持的另一种输入方式，不是体验中心第五个模板分类。

**时间控制**：官方输入提示使用 `[2s:5s]`，音效卡点模板使用 `[2.7s:5.7s]` 等小数秒区间。将标记写在对应台词或声音事件前，同时描述停顿、情绪递进、转场和声音强弱。

```json
{
  "prompt": "总长10秒，雨声持续。女子轻声说道：[2.7s:5.7s]‘你终于回来了。’[6s:7s]响起敲门声，最后雨声渐弱。",
  "subtitles": true,
  "format": "mp3"
}
```

区间标记随 `prompt` 原样传给官方 `text_prompt`；没有独立的 `timeline` 参数，也不在 MCP 内做音频裁切或强制对齐。`subtitles=true` 返回的是生成后的人声字幕，`subtitle.sentences` 及其 `words` 的 `start_time` / `end_time` 单位为**毫秒**，不标注所有音效。实际时间落点需核对音频与字幕；不要把提示词控制理解为每次严格命中指定时间。单次最长120秒，台词过长或区间过短可能影响节奏。

**多语种**：目标语言台词配合角色、口音和表演说明；不需要额外的 `language` 参数。官方英语模板用英文描述人物声线、标准美式英语、情绪、环境音和配乐。

```json
{
  "prompt": "A young woman speaks warm, clear American English: ‘Welcome home.’ Soft piano continues underneath. A young man replies quietly: ‘It is good to be back.’",
  "format": "mp3",
  "subtitles": true
}
```

语言支持清单以[官方音频生成 API](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh)为准，控制台模板展示与 API 列举可能不同。四类用法及参数示例也已写入 `generate_audio` 的工具描述，客户端发现工具时即可读取。

### 长文本与实时会话

长文本 `submit_long_text_speech`：

```json
{"request":{"req_params":{"text":"长文本……","speaker":"zh_female_vv_uranus_bigtts","audio_params":{"format":"mp3"}}}}
```

提交后用返回的 `task_id` 查询，`resource_id` 须与提交一致。标准识别提交：

```json
{"request":{"user":{"uid":"mcp"},"audio":{"url":"https://example.com/meeting.wav"},"request":{"model_name":"bigmodel","show_utterances":true}},"mode":"standard"}
```

复刻先用 `clone_voice` 注册已分配的 `S_` 音色，查询训练结果，再 `text_to_speech(voice="S_...")` 合成。音色设计支持 `prompt.text_prompt` 或 `prompt.image_prompt`，完整参数见工具说明。

实时打开最简配置：

```json
{"session":{"audio":{"output":{"voice":"zh_female_vv_jupiter_bigtts"}}}}
```

1. 使用返回的客户端 `session_id`，通过 `send_realtime_event` 发送 `input_audio_buffer.append` 与 `audio_file`（16kHz / mono / int16 裸 PCM），或事件里的 Base64 `audio`。
2. 发送 `input_audio_buffer.commit` 强制判停，或由服务端判断停顿。
3. `receive_realtime_events` 接收转写、回复、音频路径、工具调用和用量。音频 delta 自动落盘，附格式和采样率，不返回巨大 Base64。
4. 调用者执行 Function Calling，再通过 `conversation.item.create` 回传 `role=tool` 和对应 `call_id`。可发送 `response.cancel` 打断、上下文增删查和 `session.update`。
5. `close_realtime_session` 等待关闭确认并释放连接；MCP 退出也会清理全部会话。

实时上传20ms一包。MCP 不直接采集麦克风、播放声音或驱动声卡，客户端负责设备输入输出。同传需16kHz / mono / 16bit WAV或PCM；WAV自动去容器。目标 PCM16k 保存有效WAV，PCM24k保留float32原始PCM并返回格式信息。

播客断线保留 `.partial.*`、`task_id` 和 `last_finished_round_id`，可通过官方 `retry_info` 显式续传；返回的是续传片段，不自动和旧文件合并。妙记 `AllActivate` 是计费选择，必须显式传入；功能仍需各自开关。

## 官方来源与覆盖边界

新增接口来源包括[长文本提交](https://docs.volcengine.com/docs/DoubaoVoice/Tasksubmission?lang=zh)、[音色注册](https://docs.volcengine.com/docs/DoubaoVoice/tone-training-http?lang=zh)、[音色设计](https://docs.volcengine.com/docs/DoubaoVoice/SoundDesignAPI?lang=zh)、[实时识别](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)、[播客](https://docs.volcengine.com/docs/DoubaoVoice/PodcastAPI-websocket-v3protocol?lang=zh)、[实时3.0](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)、[同传](https://docs.volcengine.com/docs/DoubaoVoice/SimultaneousInterpretation20APIAccessDocumentation?lang=zh)、[机器翻译](https://docs.volcengine.com/docs/DoubaoVoice/MachineTranslationLargeModel-APIAccessDocumentation?lang=zh)、[妙记](https://docs.volcengine.com/docs/DoubaoVoice/DoubaoVoiceMinutes-APIAccessDocumentation?lang=zh)、[热词](https://docs.volcengine.com/docs/DoubaoVoice/HotWordManagementAPIv10?lang=zh)、[替换词](https://docs.volcengine.com/docs/DoubaoVoice/ReplacementWordAPIv11?lang=zh)及[控制台OpenAPI](https://api.volcengine.com/api-docs/view?action=ActivateService&serviceCode=speech_saas_prod&version=2025-05-20)。

Speech SDK的离线模型、端侧VAD / 音频处理和Android / iOS接入需原生应用，不能等同于云MCP。术语词表CRUD官方仅公开控制台流程；翻译 / 同传已支持 `corpus.glossary_list`、`glossary_table_id` 和 `glossary_table_name`。同传官方附件的Protobuf尚未声明文档新增的 `detected_language`，本版不猜字段编号。

历史产品使用独立工具与旧版凭据，返回各操作的精确官方 `source` 链接。传统 `/api/v2/asr` 旧 WebSocket 协议未重复实现；一句话和流式识别功能通过现行大模型接口提供。实时对话采用最新3.0，未复制旧1.0/2.0会话协议。所有产品覆盖不等于每个历史 SDK / 协议版本都已适配。

`_ast/` 的Protobuf bindings来自同传官方Python示例，生成日期2026-06-12，调整为包内相对import；运行依赖 `mcp`、`websockets`、`protobuf`。

离线测试覆盖HTTP合同、任务状态、签名、Protobuf、二进制帧、模拟WebSocket收发、音频文件、超时 / 取消清理，以及实际stdio MCP初始化、工具发现与调用。未调用付费云接口，因此不能证明账号开通、配额可用或实际生成质量。

参数说明见工具描述（`src/doubao_speech_mcp/server.py`）。接口细节以官方文档为准：[单向流式语音合成](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http)、[录音文件识别极速版](https://docs.volcengine.com/docs/DoubaoVoice/recording-file-recognition-lite-http)、[音频生成](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http)、[音色列表](https://docs.volcengine.com/docs/6561/1257544)。

## 运行时与稳定性

共享连接池、总超时、工具分组、错误语义和迁移说明见 [MCP 构建与稳定性](../../docs/mcp-reliability.md)。完整工具说明可调用 `get_tool_help(tool="工具名")`。
