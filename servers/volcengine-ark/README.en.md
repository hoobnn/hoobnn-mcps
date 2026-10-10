<div align="center">

# volcengine-ark-mcp

An MCP server for Volcengine Ark.

[![PyPI](https://img.shields.io/pypi/v/volcengine-ark-mcp?style=flat-square)](https://pypi.org/project/volcengine-ark-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE)

[简体中文](https://github.com/hoobnn/hoobnn-mcps/blob/main/servers/volcengine-ark/README.md) · **English**

</div>

An MCP server for Volcengine Ark: generate and edit images with Seedream 5.0, Seedance video, chat and multimodal understanding, web search and embeddings, with outputs saved locally.

Formerly `seedream-mcp` (that name is taken on PyPI by someone else). Renamed in 0.4; the old command and the `SEEDREAM_*` environment variables are not kept.

`0.6.0` removes `query_video`: check video progress with `get_job(job_id=...)` or `get_job(task_id=...)`, which downloads the result on completion; `generate_image` gains `parameters`. This is a breaking change.

## Seedream image generation

| Model | Parameter | Exclusive capabilities |
|---|---|---|
| Seedream 5.0 pro (default) | `model="pro"` → `doubao-seedream-5-0-pro-260628` | Layer separation, interactive editing, transparent background, fast mode |
| Seedream 5.0 flash | `model="flash"` → `doubao-seedream-5-0-flash-260915` | Layer separation, interactive editing, transparent background; no fast prompt optimization |
| Seedream 5.0 lite | `model="lite"` → `doubao-seedream-5-0-260128` | Image sets, web search, 3K / 4K |

All three models support text-to-image and single / multi-image reference generation. Parameter combinations a model does not support fail locally, without sending a request.

## Install

```bash
uv tool install volcengine-ark-mcp
```

The command is installed at `~/.local/bin/volcengine-ark-mcp`. For client configuration, see the [repository README](https://github.com/hoobnn/hoobnn-mcps/blob/main/README.en.md#configure-your-client).

## Environment variables

| Variable | Description |
|---|---|
| `ARK_API_KEY` | Required. Ark console › API Key management |
| `ARK_OUT_DIR` | Output directory, default `~/Downloads/volcengine-ark` |
| `ARK_RESOURCE_MODE` | Delivery mode: `local` (default) downloads locally; `url` only returns links valid for 24 hours |
| `ARK_JOB_DIR` | Job record directory, default `~/.local/share/volcengine-ark-mcp/jobs` |
| `ARK_BASE_URL` | Default `https://ark.cn-beijing.volces.com/api/v3` |

Parameters are documented in the tool descriptions (`src/volcengine_ark_mcp/server.py`); the [image generation API docs](https://ark.volcengine.com/region:cn-beijing/docs/ark/image-generation-api) are authoritative for endpoint details.

## 0.3 Ark extensions (pending cloud verification)

The existing image tool stays, and other Ark capabilities are added without a new MCP config.

| Tool | Capability | Official source |
|---|---|---|
| `generate_video` | Seedance text-to-video, first frame, first and last frame, multimodal reference video | [Create task](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh), [Query task](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh) |
| `chat` | Language, image / video understanding, deep thinking, structured output | [Chat](https://docs.volcengine.com/docs/ark/chat-api?lang=zh), [Responses](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh) |
| `chat(web_search=true)` | Web search, keeping sources and the full response | [Web Search](https://docs.volcengine.com/docs/ark/web-search?lang=zh) |
| `embed` | Text and multimodal embeddings | [Embeddings](https://docs.volcengine.com/docs/ark/vectorization?lang=zh), [Multimodal API](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh) |
| `list_capabilities` | Static capability catalog and limits | Offline; does not reflect account permissions |
| `list_jobs` / `get_job` / `recover_job` | Check job progress (a running video job queries Ark and downloads on completion), repair delivery | Images and videos are recorded and recoverable across process restarts |

### Seedance video

Model aliases: `seedance` → `doubao-seedance-2-5-260628`; `seedance-2` / `seedance-fast` / `seedance-mini` → the matching 2.0 series models. A full model ID or Endpoint ID also works. Limits on media count, duration and resolution per model follow the official API.

The default is `wait=0`: submitting returns `task_id` and `job_id`. Query progress with `get_job(job_id=..., wait=30)`; on completion the result is downloaded to the original directory. For a task submitted elsewhere, pass `get_job(task_id=...)`; the first query creates a local record. If the download fails or the link expires, use `recover_job(job_id=...)`. None of these submit a new generation.

Images accept a local path / data URL / public URL; video and audio references take a public URL or an `asset://` ID. Local video / audio is not uploaded automatically in this release.

Seedance 2.5 first frame / first and last frame tasks use `ratio=adaptive`; output duration is 4–30 seconds, 4–15 seconds for the 2.0 series, and both accept `duration=-1`. First and last frame cannot be combined with omni-modal reference; the 2.0 series cannot take audio alone.

The standard 2.0 model supports 4k; fast / mini only 480p / 720p. For video editing, state the intent in the prompt and use `duration=-1`, `ratio=adaptive`; `parameters.omni_reference_task_type="edit"` validates the task type up front, and omitting duration uses the official default.

`parameters` accepts official top-level options such as `draft`, `return_last_frame` and `output_format`; it cannot override the model or the input media.

### Chat and retrieval

`chat` defaults to `pro`, which is `doubao-seed-2-1-pro-260628`; you can also specify a model explicitly. This is not the same as the pro alias in the image tool.

`images` accepts local images; `videos` must be public URLs. Without search, the Chat API is used; with `web_search` on or a `previous_response_id` given, the Responses API is used.

Multi-turn history uses the Chat message structure, and Responses converts the current turn's multimodal content; `response_id` and source annotations are kept, and the full response is available on demand with `include_response=true`. `parameters` passes through advanced options the model supports; tool calls returned by the model are not executed.

The embedding tool requires an explicit model: `texts` is a list of strings; `contents` is the official typed array, for example:

```json
[{"type":"text","text":"cat"},{"type":"image_url","image_url":{"url":"/absolute/cat.png"}}]
```

It returns `data` and `usage`, with the full response on demand via `include_response=true`; it does not build indexes or knowledge bases.

### Local recovery

`ARK_JOB_DIR` defaults to `~/.local/share/volcengine-ark-mcp/jobs`. A record is created before generation, the full response is kept once received, and inline images are cached before delivery.

Image sets record errors per item, and failed downloads can be redelivered individually; layer records and `layers.json` are updated on recovery. A partial generation failure returns `partial` and failed items are not regenerated.

Videos keep the original `task_id` and refresh the URL by querying the cloud. Expired temporary URLs or cloud tasks may not be recoverable.

Results include `job_id`, `job_state`, `request_id` and `artifacts`. `ok` means this call succeeded; submitted or running jobs return `ok=true, completed=false`, fully delivered ones return `completed=true`, and execution errors are returned through MCP `isError=true`.

`get_job.ok` means the record was read successfully; if a call timed out before returning an ID, use `list_jobs` to find it by time. The existing files, layers, usage and errors fields are kept.

Each artifact records its byte size and SHA-256; downloads use a temporary file and atomic replace. Quality, pixel dimensions and media playback still need later verification.

`url` mode also keeps job metadata; the job directory stores signed URLs, responses and the image cache, but not the API Key. The cache is used for recovery and is not cleaned automatically. Recovery locks use POSIX `flock` and target macOS / Linux. Default output directories get a random suffix to avoid collisions between calls in the same second.

The original integration scope is in the [integration record](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-expansion.md). The current runtime and job recovery pass offline failure tests and real stdio checks; cloud generation, account permissions and media quality are not yet verified.

An artifact's `media_info` reads the actual width and height from the PNG header; if `ffprobe` is installed, it reads the actual dimensions, duration and audio tracks of other media. When it cannot read them it returns `available=false` explicitly, rather than treating request parameters as the actual output spec. No extra Python dependencies are needed.

## Runtime and reliability

Shared connection pooling, overall timeouts, tool groups, error semantics and migration notes are in [MCP build and reliability](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/mcp-reliability.md). Call `get_tool_help(tool="tool_name")` for full tool documentation.

## Official API verification

Per-tool mapping, model versions, parameter differences and programmatically fetchable official sources are in the [Volcengine Ark API audit](https://github.com/hoobnn/hoobnn-mcps/blob/main/docs/audits/volcengine-ark.md). Local validation is based on the 2026-10-10 official documentation snapshot; account permissions and actual cloud generation are still unverified.

## License

[MIT](https://github.com/hoobnn/hoobnn-mcps/blob/main/LICENSE) © 2026 hoobnn. Free to use, modify and distribute, provided the copyright notice is kept.
