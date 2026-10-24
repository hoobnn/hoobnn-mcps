# MiniMax MCP

Independent MiniMax stdio server, distributed as `hoobnn-minimax-mcp`, not the official `minimax-mcp`. See [Chinese documentation](README.md) for the complete contract and migration notes.

`0.3.0` adds `MiniMax-H3-Highspeed` (768P only) and `MiniMax-H3-Lite` (480P / 768P; multimodal references need an explicit non-adaptive `ratio`) to `generate_video`, both 4–15 seconds without 2K.

`0.2.0` renames `enhance_video_prompt` to `create_h3_context_ir_task`, matching the official "create H3-Context-IR task" API; the old name has no alias. This is a breaking change.

Install from PyPI with `uv tool install hoobnn-minimax-mcp` (or from this checkout with `uv tool install ./servers/minimax`). Point your MCP client at the absolute path of `~/.local/bin/hoobnn-minimax-mcp`, without arguments, then restart the client.

Set `MINIMAX_API_KEY` and optionally `MINIMAX_API_HOST` (default `https://api.minimax.cn`; existing `api.minimaxi.com` and international `api.minimax.io` hosts are supported). Existing `MINIMAX_MCP_BASE_PATH` and `MINIMAX_API_RESOURCE_MODE` are accepted. New names are `MINIMAX_OUT_DIR` and `MINIMAX_RESOURCE_MODE` (local/url; default local). `MINIMAX_JOB_DIR` controls durable records, default `~/.local/share/hoobnn-minimax-mcp/jobs`. Records contain input references, prompts and temporary URLs, never API keys. Requires macOS/Linux for POSIX locks.

H3 tools cover generation (`generate_video`), H3-Context-IR tasks (`create_h3_context_ir_task`), 768P-to-2K video regeneration (`regenerate_video`), task querying/listing, uploads and delivery recovery. H3 supports 768P/2K and 4–15 seconds; H3-Highspeed supports 768P only and 4–15 seconds; H3-Lite supports 480P/768P and 4–15 seconds and needs an explicit non-adaptive `ratio` for multimodal references; H3-Max supports 480P/768P and 5–15 seconds. Local media is uploaded automatically. Generation submits asynchronously by default; query with `get_job`. Recovery never resubmits generation. Cloud tasks and uploaded input files have a seven-day window.

Retains `text_to_audio`, `list_voices`, `voice_clone`, `voice_design`, `text_to_image` and `music_generation`. Defaults: speech-2.8-hd, image-01, music-3.0. The official music service notice limits paid APIs to existing paid customers and discontinues free music APIs.

All 14 official API pages were reviewed again on 2026-10-24. Video creation added `MiniMax-H3-Highspeed` and `MiniMax-H3-Lite`, now supported with offline validation; Context-IR and regeneration request contracts are unchanged. The music service discontinuation notice remains; this does not establish renewed access for free models or new accounts. See the [contract review and local validation](../../docs/minimax-contracts.md#2026-10-24-文档更新审查).

Not a fully compatible replacement: no legacy Hailuo V1 tasks or speaker playback; `first_frame_image` becomes `first_frame`, `async_mode` becomes `wait` (0–90 seconds). Voice cloning accepts a local file or uploaded file ID instead of the old `is_url` option. Chat, ASR, streaming and asynchronous long TTS are outside this implementation.

Cancellation/deletion is hidden unless `admin` is included in `MCP_TOOL_GROUPS`. The default groups are video,image,speech,music,files,jobs,help.

Contracts verified against the [official China API overview](https://platform.minimax.cn/docs/api-reference/api-overview) on 2026-10-11. Offline contract and stdio tests do not establish live account access or generated media quality. No paid cloud generation is part of the test suite.
