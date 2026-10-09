# doubao-speech-mcp

调用火山引擎豆包语音的 MCP server，结果直接存到本地：

| 工具 | 作用 | 接口 / 模型 |
|---|---|---|
| `text_to_speech` | 语音合成：2.0 音色、自然语言语音指令、8 种方言、30+ 语种、读音修正、SRT 字幕，长文本自动分段拼接 | 单向流式 HTTP，`seed-tts-2.0`（复刻音色自动用 `seed-icl-2.0`） |
| `speech_to_text` | 录音文件识别：同步返回，100MB / 2 小时以内，热词、上下文、分句和说话人 | 录音文件识别极速版，`volc.bigasr.auc_turbo` |
| `generate_audio` | 音频生成：按描述生成音效、配乐、多角色对白混合的音频，最长 120 秒，可参考音色、音频或图片 | `seed-audio-1.0` |

服务端会校验大部分参数，明显不合法的组合在本地直接报错。

## 环境变量

| 变量 | 说明 |
|---|---|
| `VOLC_SPEECH_API_KEY` | 必需，豆包语音控制台 → API Key 管理（新版控制台单 key 鉴权），并开通对应服务 |
| `DOUBAO_SPEECH_OUT_DIR` | 音频输出目录，默认 `~/Downloads/doubao-speech` |
| `VOLC_SPEECH_BASE_URL` | 默认 `https://openspeech.bytedance.com` |

`generate_audio` 一次要几十秒到两分钟，Codex 要设 `tool_timeout_sec = 300`。

参数说明见工具描述（`src/doubao_speech_mcp/server.py`）。接口细节以官方文档为准：[单向流式语音合成](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http)、[录音文件识别极速版](https://docs.volcengine.com/docs/DoubaoVoice/recording-file-recognition-lite-http)、[音频生成](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http)、[音色列表](https://docs.volcengine.com/docs/6561/1257544)。
