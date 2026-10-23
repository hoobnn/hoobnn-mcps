<div align="center">

# ali-bailian-mcp

An MCP server for Alibaba Cloud Model Studio (Bailian, DashScope) that saves results directly to your machine.

[![PyPI](https://img.shields.io/pypi/v/ali-bailian-mcp?style=flat-square)](https://pypi.org/project/ali-bailian-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE)

[简体中文](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/ali-bailian/README.md) · **English**

</div>

`0.7.0` adds local recordings / Base64 Data URIs for voice cloning, `qwen-audio-3.1-tts-plus`, and thinking controls for MiniMax models hosted on Bailian, with updated workspace and region guidance. TTS usage keeps the provider's units; legacy counters whose units were lost are returned as `legacy_untyped` rather than guessed as characters or tokens.

`0.6.0` follows the official 2026-10-10 model retirements: `clone_voice` / `design_voice` now use `voice-enrollment` with default target `qwen-audio-3.0-tts-flash`; `text_to_speech` adds Qwen-Audio-TTS / CosyVoice with `instructions` style control; `rerank` always uses the native endpoint; `speech_to_text` rejects retired dated snapshots. Voices created for the retired qwen3-tts-vc/vd models no longer work.

`0.5.0` removes `query_video`: video progress is now checked with `get_job`, which downloads the result on completion; the generation tools plus `chat`, `text_to_speech` and `speech_to_text` gain `parameters`. This is a breaking change.

| Tool | What it does | Default model |
|---|---|---|
| `generate_image` | Image generation and editing | `qwen-image-3.0-pro` |
| `chat` | Calls language models on Bailian (Qwen, plus hosted DeepSeek, Kimi, GLM, MiniMax and others) | `qwen3.8-max` |
| `text_to_speech` | Speech synthesis with automatic splitting and joining of long text; routed by model: `qwen3-tts-flash` system voices, Qwen-Audio-TTS / CosyVoice with custom voices and `instructions` tone control | `qwen3-tts-flash` |
| `speech_to_text` | Speech recognition (up to 5 minutes / 10MB), returning text, language and emotion; retired dated snapshots are rejected locally | `qwen3-asr-flash` |
| `generate_video` | Video generation: text-to-video, first frame, first and last frames, multi-subject reference, continuation, up to 30 seconds, with audio | `wan3.0-video` |
| `list_models` | Lists model IDs in the official Bailian model catalog, filterable by name | — |
| `list_jobs` / `get_job` / `recover_job` | Check job progress (in-progress video jobs query Bailian and download on completion), repair delivery, resume TTS | Local job records |

Image models (set `model` to an alias or a full ID):

| Alias | Model | Strengths |
|---|---|---|
| `qwen` (default) | `qwen-image-3.0-pro` | Best text rendering; text-to-image and editing in one |
| `wan` | `wan2.7-image-pro` | 0–9 reference images, 1K / 2K / 4K, image sets, thinking |
| `z` | `z-image-turbo` | Fastest and cheapest, realistic portraits and product shots, text-to-image only |

You can also pass other IDs directly, such as `qwen-image-2.1`, `qwen-image-2.0-pro` or `wan2.7-image`. The `qwen-image`, `qwen-image-max`, `qwen-image-plus` and `qwen-image-edit` series were retired on 2026-10-10.

Language model aliases: `max` → `qwen3.8-max` (default, supports images), `plus` → `qwen3.7-plus`, `flash` → `qwen3.8-flash`; pass other models by ID, such as `deepseek-v4-pro`, `kimi-k3` or `glm-5.3`. `chat` always uses the streaming endpoint and supports multi-turn history, image input, a deep-thinking switch, JSON output and web search.

`MiniMax/MiniMax-M3.1-Flash` joined Bailian on 2026-10-21. `thinking=true` maps to the provider's `thinking={"type":"adaptive"}`; `false` is rejected locally. `reasoning_split` is always `true` and `n` must be `1`. Set `parameters={"reasoning_effort":"high"}` for thinking depth (low/medium/high/xhigh/max; default max). `MiniMax/MiniMax-M3` supports disabling thinking but does not support `reasoning_effort`. Both models use fixed `temperature=1` and `top_p=0.95`; other values have no effect. They do not support `json_mode` or `web_search`. M3.1 ignores `stop`, `parallel_tool_calls=false` cannot guarantee serial calls, and `tool_choice` only supports auto. This `chat` returns text and reasoning and does not implement a full Function Calling loop. Thinking and answers share the output token limit. See [MiniMax direct access](https://help.aliyun.com/zh/model-studio/minimax-api-by-minimax).

For Qwen web search, `parameters={"include_tool_usage":true}` returns `usage.x_tools.search.count/strategy` without filtering. The count measures search intent triggers and is not a billing reconciliation metric. Newly listed IDs such as `deepseek-v4.1-flash-1017` and `xiaomi/mimo-v2.6-pro-ultraspeed` can be passed explicitly; capabilities and account access must match the selected model.

Video is an async job: `generate_video` defaults to `wait=0` and returns `task_id` and `job_id` after submission; then `get_job(job_id=...)` checks progress. It queries once by default; set `wait` for short polling, up to 90 seconds. The video model defaults to `wan` (`wan3.0-video`); `wan-fast` maps to `wan3.0-video-prime`, with the same capabilities and faster generation. Reference media and local files for video are uploaded automatically to Bailian temporary storage (valid for 48 hours).

Obviously unsupported parameter combinations fail locally; everything else is left to server-side validation.

`parameters` carries official fields the tool does not expose individually, deep-merged: for native endpoints (images, video, `qwen3-tts-flash`) into the `parameters` object of the official request, for Qwen-Audio-TTS / CosyVoice into the official `input` object, and for OpenAI-compatible endpoints (`chat`, `speech_to_text`) into the top level of the request body.

## Install

```bash
uv tool install ali-bailian-mcp
```

The command is installed at `~/.local/bin/ali-bailian-mcp`. For client configuration, see the [repository README](https://github.com/hoobnn/hoobnn-mcps/blob/main/README.en.md#configure-your-client).

## Environment variables

| Variable | Description |
|---|---|
| `DASHSCOPE_API_KEY` | Required. Use an API Key from the same region as the workspace |
| `BAILIAN_OUT_DIR` | Output directory for images, audio and video, default `~/Downloads/ali-bailian` |
| `BAILIAN_RESOURCE_MODE` | Delivery mode: `local` (default) downloads to disk; `url` returns links valid for 24 hours only |
| `BAILIAN_JOB_DIR` | Job record directory, default `~/.local/share/ali-bailian-mcp/jobs` |
| `DASHSCOPE_BASE_URL` | Default `https://dashscope.aliyuncs.com` for existing integrations; prefer the workspace root domain below, without `/api/v1` or another path |

Parameters are documented in the tool descriptions (`src/ali_bailian_mcp/server.py`). For endpoint details, Bailian's [text-to-image](https://help.aliyun.com/zh/model-studio/text-to-image), [OpenAI-compatible API](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope), [Qwen TTS](https://help.aliyun.com/zh/model-studio/qwen-tts-api), [Qwen-Audio-TTS](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api), [CosyVoice](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api), [Qwen ASR](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference) and [Wan 3.0 video](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference) documentation is authoritative.

## Domains and regional access

Set `DASHSCOPE_BASE_URL` to your workspace **root domain**: `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com` for Beijing; `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com` for Singapore; the HappyHorse US example uses `https://{WorkspaceId}.us-east-1.maas.aliyuncs.com`. Replace the placeholder with the workspace ID for that region and use a matching API Key. Do not append `/api/v1` or `/compatible-mode/v1`; the MCP adds the tool-specific path.

| Product / implemented protocol | Beijing | Singapore | Scope |
|---|---|---|---|
| Qwen-Audio-TTS, HTTP SpeechSynthesizer | 3.1-plus/flash, 3.0-plus/flash | 3.1-plus/flash, 3.0-plus/flash | Full IDs use `qwen-audio-…-tts-…`; listing does not prove account access |
| CosyVoice, HTTP SpeechSynthesizer | Integrated v3.5 / v3 / v2 models | Not listed by the HTTP API | Singapore realtime support does not imply HTTP synthesis support |
| voice-enrollment cloning | All integrated targets | Qwen-Audio 3.1-plus, 3.0-plus/flash; CosyVoice v3-plus/flash | Cloning availability does not imply availability of this MCP's HTTP synthesis |
| voice-enrollment design | All integrated targets | Not listed | Voices remain bound to their target model |
| HappyHorse video editing | Follow the product API | Follow the product API | US documentation now uses a workspace domain; match region, deployment scope and account access |

The Qwen-Audio-TTS / CosyVoice “model access” pages describe **AOQ / WebSocket realtime protocols**. This MCP implements the **non-realtime HTTP protocols** above; changing a model ID does not add realtime support. See [regions and domains](https://help.aliyun.com/zh/model-studio/regions), [Qwen-Audio-TTS HTTP](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api), [CosyVoice HTTP](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api), and [realtime access](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-model-access). The official domain guide states that legacy DashScope domains no longer receive new features from 2026-09-30; use workspace domains for new features.

## Added in 0.3

| Tool | Capability | Official contract |
|---|---|---|
| `clone_voice` | Clone a voice from a local recording, public URL or Base64 Data URI (voice-enrollment) | [Cloning HTTP API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api) |
| `design_voice` | Design a voice from a text description and save the preview (voice-enrollment) | [Design API](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| `list_voices` / `get_voice` | Paged listing / detail lookup of voice-enrollment custom voices and their review status | Same as above |
| `edit_video` | HappyHorse instruction-based editing, style and element replacement | [Video editing API](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `animate_portrait` | Portrait image + voice → lip-synced digital human | [wan2.2-s2v](https://help.aliyun.com/zh/model-studio/wan-s2v-api) |
| `embed` | Text, image and video embeddings | [Embeddings](https://help.aliyun.com/zh/model-studio/embedding), [Multimodal API](https://help.aliyun.com/en/model-studio/multimodal-embedding-api-reference) |
| `rerank` | Relevance ranking of candidate texts, keeping original indexes | [Rerank API](https://help.aliyun.com/zh/model-studio/text-rerank-api) |
| `list_capabilities` | Tools supported by this MCP, sources and integration limits | Static catalog; does not mean the account has access |
| `list_jobs` / `get_job` / `recover_job` | Local job records, segment resumption and re-download | Local mechanism, no new cloud service required |

### Creating and using voices

Model Studio retired `qwen-voice-design`, `qwen3-tts-vc-*`, `qwen3-tts-vd-*` and `qwen3-tts-instruct-flash` on 2026-10-10. `clone_voice` and `design_voice` now use the current official `voice-enrollment` (`action=create_voice`); creating voices is free:

1. Create: `clone_voice(audio="https://…/sample.wav", prefix="me")` or `design_voice(voice_prompt=…, preview_text=…, prefix="me")`. The default `target_model` is `qwen-audio-3.0-tts-flash`; other Qwen-Audio-TTS / CosyVoice models can be chosen. A voice only works with the model it was created for.
2. Wait for review: the voice is usable once `get_voice(voice=…)` reports `status` `OK` (`DEPLOYING` = in review, `UNDEPLOYED` = rejected).
3. Synthesize: `text_to_speech(text=…, voice=voice_id, instructions="speak gently")`. Without `model`, the target model is inferred from the voice ID prefix and the SpeechSynthesizer protocol is used.

The `audio` argument accepts a local WAV/MP3/M4A file (up to 10MB), a public http/https URL or a Base64 Data URI. Local files are encoded directly as Data URIs; all forms use the official `input.audio`, without temporary uploads. The legacy `url` alias accepts a public URL and cannot be combined with `audio`; the upstream `input.url` remains compatible but is being deprecated. Unsupported `oss://` references are still rejected. Audio should be at least 16kHz, preferably 10–20 seconds and no longer than 60 seconds, with at least 5 seconds of clear speech; remote file specifications and voice quality are checked by the service. If a response lacks a voice ID the voice is never re-created automatically; check with `list_voices(prefix=…)`.

`list_voices` / `get_voice` both use voice-enrollment `list_voice` / `query_voice`; cloned and designed voices share one list. The legacy `kind` values `clone` / `design` / `cosyvoice` are still accepted and all mean `enrollment`. Retired Qwen cloned / designed voices can no longer be used for synthesis. Regional support differs for synthesis, cloning and design; see the access table. `qwen-audio-3.1-tts-plus` is supported by all three tools when passed explicitly. Existing defaults and the `audio` / `audio-plus` aliases are unchanged.

`instructions` maps to the official `instruction`. The 100-character limit (Chinese characters count as 2) applies to CosyVoice only; Qwen-Audio-TTS currently publishes no equivalent limit and is validated by the service. CosyVoice v2 does not support instructions, v3 system voices require the documented fixed instructions, and v3-plus custom voices do not support instructions.

### Video editing and digital humans

The new video tools default to `wait=0`: they only submit and record the job immediately. Then use `get_job(job_id=...)` to check progress, and `recover_job(job_id=...)` if the download fails.

HappyHorse editing takes input video of 3–60 seconds and outputs at most 15 seconds. Digital-human audio must be under 20 seconds and under 15MB, at 480P / 720P resolution, in the Beijing region. Local video media is uploaded to Bailian temporary storage; reference images are sent as data URLs to the editing endpoint. Model and region access still need confirmation with real calls.

### Embeddings and reranking

- Text embeddings: `embed(texts=[...], model="text-embedding-v4")`.
- Multimodal embeddings: `embed(contents=[{"text":"cat"},{"image":"/absolute/cat.png"}], model="qwen3-vl-embedding")`.
- Embeddings do not automatically create an index, database or knowledge base.
- `rerank` defaults to `qwen3.7-text-rerank`; every model, including `qwen3-rerank`, uses the native `/api/v1/services/rerank/text-rerank/text-rerank` endpoint.

### Job recovery

`BAILIAN_JOB_DIR` defaults to `~/.local/share/ali-bailian-mcp/jobs`. Job records use their own UUIDs and are written before the generation request; default output directories also get a random suffix to avoid collisions between calls in the same second.

- Images save the full response and per-item URLs, then deliver with bounded concurrency; recovery only re-downloads.
- Video saves the cloud `task_id`, queries the original task after a restart and refreshes result URLs; it never resubmits generation.
- TTS saves text, generated URLs and files per segment; recovery skips synthesized segments, continues only unsubmitted ones, then joins the WAV. Segments with unknown status are never re-synthesized automatically. Explicitly rejected segments can be resubmitted by an explicit recovery call.
- TTS usage keeps the provider's `characters`, `input_tokens`, `output_tokens`, `total_tokens` and other counters, summing equal units. Old scalar counters have lost their units and remain `legacy_untyped`, separate from new counters; these records do not estimate a bill.
- Voice design records the voice ID before delivering the preview; recovery only re-delivers the preview and never creates the voice again.
- If a tool call times out without returning an ID, `list_jobs` can find the record by time, model and summary.

New return fields are `job_id`, `job_state`, `artifacts` and `request_id`. `job_state` distinguishes `unknown` / `running` / `generated` / `partial` / `download_failed` / `failed` / `delivered`.

`ok` means this call succeeded; submitted or running jobs return `ok=true, completed=false`, and fully delivered jobs return `completed=true`. Partial failure in an image set uses MCP `isError=true` and keeps the successful outputs. `get_job.ok` only means the record was read successfully. `artifacts` contains files, source URLs, per-item errors, byte counts and SHA-256; synthesized WAVs also include actual duration and sample rate.

Downloads are written to a temporary file, checked for non-empty content and HTTP length, then atomically replaced; recovery uses SHA-256 to skip complete files. Verifying download integrity is not the same as checking visual / audio quality. Expired temporary URLs, missing complete synchronous responses, or responses lost to storage failures may be unrecoverable.

Job records keep signed URLs, generation responses and TTS text; the API Key is never stored. `url` mode also writes job records, and a voice preview that only exists as inline data is saved locally. Segment files and response caches are assets needed for recovery and are not cleaned up automatically. The recovery lock uses POSIX `flock` and targets macOS / Linux.

Offline failure tests and real stdio checks pass; on 2026-10-13 every tool was verified with small cloud samples on a Beijing-region account (results in the reliability record). Historical integration scope is in the [integration record](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-expansion.md), and this round's verification is in the [reliability record](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md).

The `media_info` of each output reads the actual width and height from the PNG header; if `ffprobe` is installed, it also reads the actual dimensions, duration and audio track details of other media. When it cannot read them, it explicitly returns `available=false` and never treats request parameters as the actual output spec. No extra Python dependency is needed.

## Runtime and reliability

The shared connection pool, overall timeout, tool groups, error semantics and migration notes are covered in [MCP build and reliability](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md). Call `get_tool_help(tool="<tool name>")` for full tool documentation.

## Official contracts and latest docs

All tools and default models were checked against the official documentation on 2026-10-10; see the [Bailian audit](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/audits/ali-bailian.md). `list_models` now queries the native `/api/v1/models` all-modality paged catalog and returns `complete` plus official metadata; presence in the catalog does not mean the account is authorized. In Beijing, setting `DASHSCOPE_BASE_URL` to your real workspace root domain is recommended. Wan3 supports `link` web page references, which cannot be combined with `file` or with first and last frames. The ASR tool only accepts `qwen3-asr-flash` (dated snapshots were retired on 2026-10-10 and are rejected locally); Fun-ASR, filetrans and realtime need separate protocols. The 2026-10-13 speech migration is described in the audit section "2026-10-13 语音迁移".

## License

[MIT](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE) © 2026 hoobnn. Free to use, modify and distribute, provided the copyright notice is kept.
