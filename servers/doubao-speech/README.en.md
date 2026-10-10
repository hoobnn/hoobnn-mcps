<div align="center">

# doubao-speech-mcp

An MCP server for Doubao Speech.

[![PyPI](https://img.shields.io/pypi/v/doubao-speech-mcp?style=flat-square)](https://pypi.org/project/doubao-speech-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE)

[简体中文](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/doubao-speech/README.md) · **English**

</div>

A stdio MCP server for the Doubao Speech cloud APIs. Endpoints were checked against the [official catalog](https://docs.volcengine.com/docs/DoubaoVoice/list?lang=zh) on 2026-10-10.

`0.4.0` reorganizes the tools by purpose: each task has a single entry point, common capabilities all use named parameters, and only `speech_raw_request` still needs hand-written official JSON. 18 tools are exposed by default (previously 29); realtime sessions and management APIs are now opt-in. This is a breaking change and old tool names have no aliases; see [migration](#migrating-from-03x) below for the mapping.

| Tool | What it does | Endpoint / model |
|---|---|---|
| `text_to_speech` | Speech synthesis: 2.0 voices, voice instructions, 8 dialects, 30+ languages, pronunciation fixes, SRT subtitles; text over 5000 characters automatically switches to async long-text synthesis (up to 100,000 characters) | Sync unidirectional streaming HTTP / async long text, `seed-tts-2.0` (cloned voices use `seed-icl-2.0` automatically) |
| `generate_audio` | Audio generation: produces audio mixing sound effects, music and multi-character dialogue from a description, up to 120 seconds, optionally referencing a voice, audio or image | `seed-audio-1.0` |
| `generate_podcast` | Two-host podcast: from a `text` article / `url` link / `topic` searched online / `dialogue` turn-by-turn script; can output the script only | WebSocket podcast protocol |
| `speech_to_text` | Recorded-audio recognition: `flash` sync (100MB / 2 hours); `standard` / `idle` async (URL, 512MB / 5 hours, supports speaker diarization) | Turbo / Standard / Idle editions |
| `summarize_meeting` | Minutes: transcription plus full summary, chapters, to-dos, Q&A and translation via on/off parameters; result JSON is downloaded automatically | Async HTTP |
| `translate_text` | Seed-X machine translation, terminology via `glossary`, automatic language detection | 1–16 texts per call |
| `interpret_audio` | Simultaneous interpretation 2.0: S2T subtitles / S2S speech, hot words, terminology, target voice | WebSocket + official Protobuf |
| `clone_voice` / `design_voice` / `get_voice` / `upgrade_voice` | Voice cloning, voice design, training status query, upgrade | New V3 HTTP |
| `list_jobs` / `get_job` / `recover_job` | Async jobs (long text, standard recognition, Minutes): check progress, save results automatically, repair delivery | Local job records |
| `speech_raw_request` | Fallback: HTTP synthesis / turbo recognition / audio generation, WebSocket synthesis, streaming recognition, legacy APIs, called with the official request body as-is | Fixed endpoints |
| `list_speech_capabilities` / `get_speech_usage_examples` | Product catalog, disabled tool groups and how to enable them, summaries of official templates and call examples | Local lookup, not billed |

Opt-in groups (set `MCP_TOOL_GROUPS` and restart, for example `speech,voice,jobs,help,realtime`):

| Tool group | Tools | Why it is off by default |
|---|---|---|
| `realtime` | `open_realtime_session` / `send_realtime_event` / `receive_realtime_events` / `close_realtime_session` | Persistent sessions need turn-by-turn sending and receiving, which suits dedicated voice apps |
| `admin` | `manage_word_table` (hot word / replacement word tables), `speech_console` (console OpenAPI) | Needs IAM AK/SK and can create, delete and place orders |

Every named-parameter tool has `parameters`: fields of the official request body that the tool does not list separately (SSML, watermark, bit_rate, `ssd_version` and so on) are deep-merged in, and `parameters` wins on conflicts; for TTS, `req_params.additions` can be written directly as an object. Submit calls submit only once; queries never resubmit or purchase resources.

## Install

```bash
uv tool install doubao-speech-mcp
```

The command is installed at `~/.local/bin/doubao-speech-mcp`. For client configuration, see the [repository README](https://github.com/hoobnn/hoobnn-mcps/blob/main/README.en.md#configure-your-client).

## Environment variables

| Variable | Description |
|---|---|
| `VOLC_SPEECH_API_KEY` | Required. Doubao Speech console › API Key management (single-key auth in the new console), with the matching services activated |
| `VOLC_ACCESS_KEY_ID` / `VOLC_SECRET_ACCESS_KEY` | IAM AK/SK, needed for the console API and replacement word management; distinct from the speech API key |
| `VOLC_SPEECH_APP_ID` / `VOLC_SPEECH_ACCESS_TOKEN` | Legacy credentials for older products (such as subtitles); not replaced automatically by the new key |
| `DOUBAO_SPEECH_OUT_DIR` | Audio output directory, default `~/Downloads/doubao-speech` |
| `DOUBAO_SPEECH_JOB_DIR` | Async job records, default `~/.local/share/doubao-speech-mcp/jobs` |
| `VOLC_SPEECH_BASE_URL` | Default `https://openspeech.bytedance.com` |

Audio generation and podcasts can take longer than 300 seconds, so set the client timeout accordingly. Async jobs write a local record before submission, and `get_job` downloads results from the official temporary URLs into the output directory on completion.

Run and verify locally:

```bash
uv sync --project servers/doubao-speech
uv run --project servers/doubao-speech doubao-speech-mcp
servers/doubao-speech/.venv/bin/python -m unittest discover -s servers/doubao-speech/tests -v
```

An MCP client can launch the server locally using the absolute path of this project's `.venv/bin/doubao-speech-mcp`. An installed GitHub version must be upgraded after a release and the client restarted; source changes do not replace a server that is already running.

## Examples

Full examples and tips are in the [usage guide](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/doubao-speech/docs/usage-examples.md). Inside MCP, call `get_speech_usage_examples` directly; it returns the analysis of official templates, tool parameters, tips and source links:

```json
{"product": "audio", "category": "timing"}
```

`product` accepts `audio`, `tts`, `voice`, `podcast`, `asr`, `translation`, `minutes` and `realtime`; only `audio` supports `category=text/reference/timing/multilingual`. Omitting the category returns all examples for that product. Examples are adapted from official usage; replace file paths, URLs, assigned voice IDs and session IDs. Looking up examples does not upload or generate audio.

### Audio generation 1.0: the four official usage types

Checked against the [template categories of the official experience center](https://console.volcengine.com/speech/new/experience/audio?projectName=default) on 2026-10-09: text generation, reference generation, time control and multilingual. All four use `generate_audio` and can be combined. The JSON below is MCP tool arguments; the example prompts are adapted from official usage and have not been verified with real cloud generation.

| Official category | How to write it and MCP parameters | Official template examples |
|---|---|---|
| Text generation | `prompt` describes characters, lines, ambient sound, music and effects in order | Crime thriller, palace poison tasting, two-host podcast conversation |
| Reference generation | `reference_audios` provides voice samples, referenced in `prompt` as `@音频1`, `@音频2`; describe the referenced voice, emotion, style and pacing | Two-host product pitch, police standoff, multi-role performance |
| Time control | `prompt` gives the total length and `[start s:end s]` ranges, fractional seconds allowed | Sound effects on cue, emotional build-up, narrative transitions, narration pacing |
| Multilingual | `prompt` uses lines in the target language and describes language, accent, character and delivery | English, Japanese, Korean, French and other templates |

Text generation: define the characters and scene first, then arrange the sounds in the order they happen; put lines in quotes and keep them separate from performance directions.

```json
{
  "prompt": "雨声持续。青年女子嗓音清亮，紧张地说：‘有人来了。’随后响起三声敲门声，低音弦乐渐强。",
  "model": "seed-audio-1.0",
  "format": "mp3"
}
```

Reference generation: the first sample in the list maps to `@音频1` and the second to `@音频2`. For multi-person dialogue, make each character's reference explicit. Replace the absolute paths below with real files, or pass reachable audio URLs. Up to 3 samples, each at most 30 seconds and 10MB.

```json
{
  "prompt": "主持人甲参考@音频1的音色，热情地说：‘欢迎。’主持人乙参考@音频2的音色，轻笑着说：‘你好。’随后两人自然地笑起来。",
  "reference_audios": ["/absolute/path/host_a.wav", "/absolute/path/host_b.wav"],
  "format": "mp3"
}
```

To use an existing voice, pass `speaker`; for an image reference, pass `reference_image` (local absolute path or URL), which cannot be combined with `speaker` or `reference_audios`. Image reference is another input mode the API supports, not a fifth template category of the experience center.

Time control: the official input hint uses `[2s:5s]`, and the sound-effect cue templates use fractional ranges such as `[2.7s:5.7s]`. Put the marker before the matching line or sound event, and describe pauses, emotional build-up, transitions and loudness.

```json
{
  "prompt": "总长10秒，雨声持续。女子轻声说道：[2.7s:5.7s]‘你终于回来了。’[6s:7s]响起敲门声，最后雨声渐弱。",
  "subtitles": true,
  "format": "mp3"
}
```

Range markers are passed as-is inside `prompt` to the official `text_prompt`; there is no separate `timeline` parameter, and the MCP does not trim or force-align audio. `subtitles=true` returns subtitles for the generated speech; `start_time` / `end_time` in `subtitle.sentences` and their `words` are in milliseconds, and not every sound effect is labeled. Check the actual timing against the audio and subtitles; prompt-based control does not guarantee hitting the specified times every time. A single generation is at most 120 seconds, and overly long lines or overly short ranges may hurt pacing.

Multilingual: use lines in the target language together with character, accent and delivery notes; no extra `language` parameter is needed. The official English templates describe the voice, standard American English, emotion, ambient sound and music in English.

```json
{
  "prompt": "A young woman speaks warm, clear American English: ‘Welcome home.’ Soft piano continues underneath. A young man replies quietly: ‘It is good to be back.’",
  "format": "mp3",
  "subtitles": true
}
```

The list of supported languages follows the [official audio generation API](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh); the console templates may differ from what the API lists. The four usage types and parameter examples are also written into the `generate_audio` tool description, so clients can read them on tool discovery.

### Long text, recognition and Minutes

Long-text synthesis (async automatically above 5000 characters, forced with `long_text=true`):

```json
{"text": "长文本……", "voice": "zh_female_vv_uranus_bigtts", "long_text": true}
```

Returns `job_id` immediately; query with `get_job(job_id=..., wait=30)`, and on completion `speech.mp3` is saved to the output directory. In async mode `format` can only be mp3 / pcm / ogg_opus, and `subtitles` outputs `sentences.json`.

Meeting recording with speaker diarization (uses the Standard edition automatically; the audio must be a downloadable URL):

```json
{"audio": "https://example.com/meeting.wav", "speakers": true, "parameters": {"request": {"ssd_version": "300"}}}
```

Minutes:

```json
{"file_url": "https://example.com/meeting.wav", "summary": true, "chapters": true, "todos": true}
```

`bundle_billing` (official `AllActivate`) only selects bundled billing and does not enable features. For cloning, first register the assigned `S_` voice with `clone_voice`, check the training result with `get_voice`, then synthesize with `text_to_speech(voice="S_...")`.

### Realtime sessions (requires the `realtime` group)

Minimal configuration:

```json
{"session":{"audio":{"output":{"voice":"zh_female_vv_jupiter_bigtts"}}}}
```

1. Using the returned client `session_id`, send `input_audio_buffer.append` with `audio_file` (16kHz / mono / int16 raw PCM) through `send_realtime_event`, or a Base64 `audio` inside the event.
2. Send `input_audio_buffer.commit` to force end-of-turn, or let the server detect the pause.
3. `receive_realtime_events` receives transcripts, replies, audio paths, tool calls and usage. Audio deltas are written to disk automatically with format and sample rate, instead of returning huge Base64.
4. The caller executes Function Calling, then returns `role=tool` with the matching `call_id` via `conversation.item.create`. You can send `response.cancel` to interrupt, add, delete or query context, and send `session.update`.
5. `close_realtime_session` waits for the close confirmation and releases the connection; exiting the MCP also cleans up all sessions.

Realtime upload sends one packet per 20ms. The MCP does not capture the microphone, play sound or drive the sound card; the client handles device input and output. Simultaneous interpretation needs 16kHz / mono / 16bit WAV or PCM; WAV containers are stripped automatically. Target PCM16k is saved as valid WAV; PCM24k keeps raw float32 PCM and returns format information.

If a podcast disconnects, `.partial.*`, `task_id` and `last_finished_round_id` are kept, and you can resume explicitly through `parameters.retry_info`; the result is the resumed segment and is not merged with the old file automatically.

### Migrating from 0.3.x

| Old tool | Now |
|---|---|
| `submit_long_text_speech` / `query_long_text_speech` | `text_to_speech(long_text=true)` + `get_job` |
| `websocket_text_to_speech` | `speech_raw_request(product="tts_websocket")` |
| `speech_http_request` | `speech_raw_request(product="tts" / "asr_flash" / "audio")` |
| `submit_transcription` / `query_transcription` | `speech_to_text(mode="standard" / "idle")` + `get_job` |
| `streaming_speech_to_text` | `speech_raw_request(product="asr_stream")` |
| `submit_minutes` / `query_minutes` | `summarize_meeting` + `get_job` |
| `query_voice` | `get_voice` |
| `legacy_speech_request` | `speech_raw_request(product="legacy", operation=...)` |
| The `request` parameter of `clone_voice` / `design_voice` / `upgrade_voice` / `generate_podcast` / `translate_text` / `interpret_audio` | Named parameters, with other fields in `parameters` |
| Realtime sessions, `manage_word_table`, `speech_console` | Same names; enable `realtime` / `admin` in `MCP_TOOL_GROUPS` |

`clone_voice.language` now accepts codes such as `zh` and `en` and converts them to the official integer enum; the string form in older examples did not match the official contract.

## Official sources and coverage limits

Sources for newly added endpoints include [long-text submission](https://docs.volcengine.com/docs/DoubaoVoice/Tasksubmission?lang=zh), [voice registration](https://docs.volcengine.com/docs/DoubaoVoice/tone-training-http?lang=zh), [voice design](https://docs.volcengine.com/docs/DoubaoVoice/SoundDesignAPI?lang=zh), [realtime recognition](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh), [podcast](https://docs.volcengine.com/docs/DoubaoVoice/PodcastAPI-websocket-v3protocol?lang=zh), [Realtime 3.0](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh), [simultaneous interpretation](https://docs.volcengine.com/docs/DoubaoVoice/SimultaneousInterpretation20APIAccessDocumentation?lang=zh), [machine translation](https://docs.volcengine.com/docs/DoubaoVoice/MachineTranslationLargeModel-APIAccessDocumentation?lang=zh), [Minutes](https://docs.volcengine.com/docs/DoubaoVoice/DoubaoVoiceMinutes-APIAccessDocumentation?lang=zh), [hot words](https://docs.volcengine.com/docs/DoubaoVoice/HotWordManagementAPIv10?lang=zh), [replacement words](https://docs.volcengine.com/docs/DoubaoVoice/ReplacementWordAPIv11?lang=zh) and the [console OpenAPI](https://api.volcengine.com/api-docs/view?action=ActivateService&serviceCode=speech_saas_prod&version=2025-05-20).

The Speech SDK's offline models, on-device VAD / audio processing and Android / iOS integration require native apps and are not equivalent to a cloud MCP. Terminology table CRUD is only published officially as a console flow; translation / simultaneous interpretation use terminology through `glossary`, `glossary_table_id` (or `glossary_table_name` in `parameters`). The Protobuf in the official simultaneous interpretation attachment does not yet declare the `detected_language` added in the docs, so this version does not guess its field number.

Legacy products use separate tools and legacy credentials, and return the exact official `source` link for each operation. The old `/api/v2/asr` WebSocket protocol is not re-implemented; sentence and streaming recognition are provided through the current large-model APIs. Realtime dialogue uses the latest 3.0 and does not copy the old 1.0 / 2.0 session protocols. Covering every product does not mean every historical SDK / protocol version is supported.

The Protobuf bindings in `_ast/` come from the official Python example for simultaneous interpretation, generated on 2026-06-12, adjusted to package-relative imports; runtime dependencies are `mcp`, `websockets` and `protobuf`.

Offline tests cover HTTP contracts, job states, signing, Protobuf, binary frames, simulated WebSocket send/receive, audio files, timeout / cancellation cleanup, and real stdio MCP initialization, tool discovery and calls. No paid cloud APIs were called, so the tests cannot prove account activation, available quota or actual generation quality.

Parameter details are in the tool descriptions (`src/doubao_speech_mcp/server.py`). Official documentation is authoritative for endpoint details: [unidirectional streaming TTS](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http), [recorded-file recognition turbo](https://docs.volcengine.com/docs/DoubaoVoice/recording-file-recognition-lite-http), [audio generation](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http), [voice list](https://docs.volcengine.com/docs/6561/1257544).

## Runtime and reliability

Shared connection pooling, overall timeouts, tool groups, error semantics and migration notes are in [MCP build and reliability](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md). For full tool documentation, call `get_tool_help(tool="tool_name")`.

## License

[MIT](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE) © 2026 hoobnn. Free to use, modify and distribute, provided the copyright notice is kept.
