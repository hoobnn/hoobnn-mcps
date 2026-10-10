<div align="center">

# ali-bailian-mcp

An MCP server for Alibaba Cloud Model Studio (Bailian, DashScope) that saves results directly to your machine.

[![PyPI](https://img.shields.io/pypi/v/ali-bailian-mcp?style=flat-square)](https://pypi.org/project/ali-bailian-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE)

[简体中文](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/ali-bailian/README.md) · **English**

</div>

`0.5.0` removes `query_video`: video progress is now checked with `get_job`, which downloads the result on completion; the generation tools plus `chat`, `text_to_speech` and `speech_to_text` gain `parameters`. This is a breaking change.

| Tool | What it does | Default model |
|---|---|---|
| `generate_image` | Image generation and editing | `qwen-image-3.0-pro` |
| `chat` | Calls language models on Bailian (Qwen, plus hosted DeepSeek, Kimi, GLM, MiniMax and others) | `qwen3.8-max` |
| `text_to_speech` | Speech synthesis with 20 system voices, tone control in natural language, and automatic splitting and joining of long text | `qwen3-tts-flash` / `qwen3-tts-instruct-flash` |
| `speech_to_text` | Speech recognition (up to 5 minutes / 10MB), returning text, language and emotion | `qwen3-asr-flash` |
| `generate_video` | Video generation: text-to-video, first frame, first and last frames, multi-subject reference, continuation, up to 30 seconds, with audio | `wan3.0-video` |
| `list_models` | Lists model IDs in the official Bailian model catalog, filterable by name | — |
| `list_jobs` / `get_job` / `recover_job` | Check job progress (in-progress video jobs query Bailian and download on completion), repair delivery, resume TTS | Local job records |

Image models (set `model` to an alias or a full ID):

| Alias | Model | Strengths |
|---|---|---|
| `qwen` (default) | `qwen-image-3.0-pro` | Best text rendering; text-to-image and editing in one |
| `wan` | `wan2.7-image-pro` | 0–9 reference images, 1K / 2K / 4K, image sets, thinking |
| `z` | `z-image-turbo` | Fastest and cheapest, realistic portraits and product shots, text-to-image only |

You can also pass other IDs directly, such as `qwen-image-2.0-pro`, `qwen-image-max`, `qwen-image-edit-max` or `wan2.7-image`.

Language model aliases: `max` → `qwen3.8-max` (default, supports images), `plus` → `qwen3.7-plus`, `flash` → `qwen3.8-flash`; pass other models by ID, such as `deepseek-v4-pro`, `kimi-k3` or `glm-5.3`. `chat` always uses the streaming endpoint and supports multi-turn history, image input, a deep-thinking switch, JSON output and web search.

Video is an async job: `generate_video` defaults to `wait=0` and returns `task_id` and `job_id` after submission; then `get_job(job_id=...)` checks progress. It queries once by default; set `wait` for short polling, up to 90 seconds. The video model defaults to `wan` (`wan3.0-video`); `wan-fast` maps to `wan3.0-video-prime`, with the same capabilities and faster generation. Reference media and local files for video are uploaded automatically to Bailian temporary storage (valid for 48 hours).

Obviously unsupported parameter combinations fail locally; everything else is left to server-side validation.

`parameters` carries official fields the tool does not expose individually, deep-merged: for native endpoints (images, video, TTS) into the `parameters` object of the official request, and for OpenAI-compatible endpoints (`chat`, `speech_to_text`) into the top level of the request body.

## Install

```bash
uv tool install ali-bailian-mcp
```

The command is installed at `~/.local/bin/ali-bailian-mcp`. For client configuration, see the [repository README](https://github.com/hoobnn/hoobnn-mcps/blob/main/README.en.md#configure-your-client).

## Environment variables

| Variable | Description |
|---|---|
| `DASHSCOPE_API_KEY` | Required. Bailian console › API Key (Beijing region) |
| `BAILIAN_OUT_DIR` | Output directory for images, audio and video, default `~/Downloads/ali-bailian` |
| `BAILIAN_RESOURCE_MODE` | Delivery mode: `local` (default) downloads to disk; `url` returns links valid for 24 hours only |
| `BAILIAN_JOB_DIR` | Job record directory, default `~/.local/share/ali-bailian-mcp/jobs` |
| `DASHSCOPE_BASE_URL` | Default `https://dashscope.aliyuncs.com`; for the Singapore region use `https://dashscope-intl.aliyuncs.com`. Keys cannot be used across regions |

Parameters are documented in the tool descriptions (`src/ali_bailian_mcp/server.py`). For endpoint details, Bailian's [text-to-image](https://help.aliyun.com/zh/model-studio/text-to-image), [OpenAI-compatible API](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope), [Qwen TTS](https://help.aliyun.com/zh/model-studio/qwen-tts-api), [Qwen ASR](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference) and [Wan 3.0 video](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference) documentation is authoritative.

## Added in 0.3 (pending cloud verification)

| Tool | Capability | Official contract |
|---|---|---|
| `clone_voice` | Qwen voice cloning, local audio / URL → fixed voice | [Cloning HTTP API](https://help.aliyun.com/en/model-studio/voice-clone-design-http-api) |
| `design_voice` | Designs a voice from a natural-language description, returning the voice and a preview WAV | [Design API](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| `list_voices` / `get_voice` | Paged listing and lookup of custom voices | Same as above; Qwen details are found by scanning the paged list |
| `edit_video` | HappyHorse instruction-based editing, style and element replacement | [Video editing API](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| `animate_portrait` | Portrait image + voice → lip-synced digital human | [wan2.2-s2v](https://help.aliyun.com/zh/model-studio/wan-s2v-api) |
| `embed` | Text, image and video embeddings | [Embeddings](https://help.aliyun.com/zh/model-studio/embedding), [Multimodal API](https://help.aliyun.com/en/model-studio/multimodal-embedding-api-reference) |
| `rerank` | Relevance ranking of candidate texts, keeping original indexes | [Rerank API](https://help.aliyun.com/zh/model-studio/text-rerank-api) |
| `list_capabilities` | Tools supported by this MCP, sources and integration limits | Static catalog; does not mean the account has access |
| `list_jobs` / `get_job` / `recover_job` | Local job records, segment resumption and re-download | Local mechanism, no new cloud service required |

### Creating and using voices

`clone_voice` targets `qwen3-tts-vc-2026-01-22` by default; `design_voice` targets `qwen3-tts-vd-2026-01-26`.

Creation returns `voice` and `target_model`; afterwards you must call `text_to_speech(text=..., voice=<returned voice>, model=<returned target model>)`. The default flash system-voice models cannot use these custom voices. The creation tools currently support Qwen non-realtime VC / VD; the voice list can also query CosyVoice / Qwen-Audio, but synthesis for those two is out of scope for this round.

Qwen has no separate detail endpoint, so `get_voice` searches the paged list; reaching `max_pages` only means the search is incomplete, not that the voice does not exist.

### Video editing and digital humans

The new video tools default to `wait=0`: they only submit and record the job immediately. Then use `get_job(job_id=...)` to check progress, and `recover_job(job_id=...)` if the download fails.

HappyHorse editing takes input video of 3–60 seconds and outputs at most 15 seconds. Digital-human audio must be under 20 seconds and under 15MB, at 480P / 720P resolution, in the Beijing region. Local video media is uploaded to Bailian temporary storage; reference images are sent as data URLs to the editing endpoint. Model and region access still need confirmation with real calls.

### Embeddings and reranking

- Text embeddings: `embed(texts=[...], model="text-embedding-v4")`.
- Multimodal embeddings: `embed(contents=[{"text":"cat"},{"image":"/absolute/cat.png"}], model="qwen3-vl-embedding")`.
- Embeddings do not automatically create an index, database or knowledge base.
- `rerank` defaults to `qwen3.7-text-rerank` through the native endpoint; `qwen3-rerank` goes through `/compatible-api/v1/reranks`. Full requests and responses keep the endpoint differences.

### Job recovery

`BAILIAN_JOB_DIR` defaults to `~/.local/share/ali-bailian-mcp/jobs`. Job records use their own UUIDs and are written before the generation request; default output directories also get a random suffix to avoid collisions between calls in the same second.

- Images save the full response and per-item URLs, then deliver with bounded concurrency; recovery only re-downloads.
- Video saves the cloud `task_id`, queries the original task after a restart and refreshes result URLs; it never resubmits generation.
- TTS saves text, generated URLs and files per segment; recovery skips synthesized segments, continues only unsubmitted ones, then joins the WAV. Segments with unknown status are never re-synthesized automatically. Explicitly rejected segments can be resubmitted by an explicit recovery call.
- Voice design records the voice ID before delivering the preview; recovery only re-delivers the preview and never creates the voice again.
- If a tool call times out without returning an ID, `list_jobs` can find the record by time, model and summary.

New return fields are `job_id`, `job_state`, `artifacts` and `request_id`. `job_state` distinguishes `unknown` / `running` / `generated` / `partial` / `download_failed` / `failed` / `delivered`.

`ok` means this call succeeded; submitted or running jobs return `ok=true, completed=false`, and fully delivered jobs return `completed=true`. Partial failure in an image set uses MCP `isError=true` and keeps the successful outputs. `get_job.ok` only means the record was read successfully. `artifacts` contains files, source URLs, per-item errors, byte counts and SHA-256; synthesized WAVs also include actual duration and sample rate.

Downloads are written to a temporary file, checked for non-empty content and HTTP length, then atomically replaced; recovery uses SHA-256 to skip complete files. Verifying download integrity is not the same as checking visual / audio quality. Expired temporary URLs, missing complete synchronous responses, or responses lost to storage failures may be unrecoverable.

Job records keep signed URLs, generation responses and TTS text; the API Key is never stored. `url` mode also writes job records, and a voice preview that only exists as inline data is saved locally. Segment files and response caches are assets needed for recovery and are not cleaned up automatically. The recovery lock uses POSIX `flock` and targets macOS / Linux.

Offline failure tests and real stdio checks pass; no paid cloud generation has been made, and the newly added products still await cloud verification. Historical integration scope is in the [integration record](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-expansion.md), and this round's verification is in the [reliability record](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md).

The `media_info` of each output reads the actual width and height from the PNG header; if `ffprobe` is installed, it also reads the actual dimensions, duration and audio track details of other media. When it cannot read them, it explicitly returns `available=false` and never treats request parameters as the actual output spec. No extra Python dependency is needed.

## Runtime and reliability

The shared connection pool, overall timeout, tool groups, error semantics and migration notes are covered in [MCP build and reliability](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md). Call `get_tool_help(tool="<tool name>")` for full tool documentation.

## Official contracts and latest docs

All tools and default models were checked against the official documentation on 2026-10-10; see the [Bailian audit](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/audits/ali-bailian.md). `list_models` now queries the native `/api/v1/models` all-modality paged catalog and returns `complete` plus official metadata; presence in the catalog does not mean the account is authorized. In Beijing, setting `DASHSCOPE_BASE_URL` to your real workspace root domain is recommended. Wan3 supports `link` web page references, which cannot be combined with `file` or with first and last frames. The ASR tool only integrates the Qwen3-ASR-Flash HTTP series; Fun-ASR, filetrans and realtime need separate protocols.

## License

[MIT](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE) © 2026 hoobnn. Free to use, modify and distribute, provided the copyright notice is kept.
