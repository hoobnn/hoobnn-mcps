<div align="center">

# hoobnn-mcps

MCP servers for Volcengine Ark, Doubao Speech and Alibaba Cloud Model Studio.

[![CI](https://img.shields.io/github/actions/workflow/status/hoobnn/hoobnn-mcps/test.yml?branch=main&style=flat-square&label=CI)](https://github.com/hoobnn/hoobnn-mcps/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

[简体中文](README.md) · **English**

</div>

hoobnn's personal collection of MCP servers. Each server is a standalone Python package under `servers/<name>/`, published to PyPI; installing with [uv](https://docs.astral.sh/uv/) is recommended.

| Server | What it does |
|---|---|
| [`volcengine-ark`](servers/volcengine-ark) | Volcengine Ark: Seedream images, Seedance video, language and multimodal understanding, web search, embeddings and job recovery (newly added products are not yet verified against the cloud) |
| [`doubao-speech`](servers/doubao-speech) | Doubao Speech: synthesis (including async long text), recognition, audio generation, podcasts, simultaneous interpretation, translation, Minutes, voice cloning and voice design; Realtime Dialogue 3.0, word tables and console management are opt-in |
| [`ali-bailian`](servers/ali-bailian) | Alibaba Cloud Model Studio (Bailian): images, language, TTS / ASR, voice cloning and design, video generation / editing / digital humans, embeddings and reranking, job recovery (newly added products are not yet verified against the cloud) |

The three servers overlap in places. Each tool description states which scenarios it suits; roughly:

| Need | Prefer | Alternative |
|---|---|---|
| Images: layer separation, transparent background, image sets | `volcengine-ark` Seedream | — |
| Images: Chinese / English text on posters, multi-image fusion | `ali-bailian` qwen / wan | — |
| Video: local reference video / audio, document or web page reference | `ali-bailian` Wan (uploads automatically) | `volcengine-ark` Seedance (reference media must be public URLs) |
| Chat: Doubao Seed | `volcengine-ark` `chat` | — |
| Chat: Qwen, DeepSeek, Kimi, GLM and others | `ali-bailian` `chat` | — |
| Speech synthesis, recognition, cloning | `doubao-speech` (Chinese voices, dialects, subtitles, long text, speaker diarization) | `ali-bailian` (Qwen voices; ASR returns emotion and language) |

A voice cloned or designed with one provider can only be used by that provider's synthesis tool. All three servers use `get_job` to check async job progress and download results automatically on completion; `recover_job` is only for repairing delivery.

## Install

### From PyPI

Install locally from PyPI with `uv tool install`; the commands land in `~/.local/bin/<name>-mcp`:

```bash
uv tool install volcengine-ark-mcp
uv tool install ali-bailian-mcp
uv tool install doubao-speech-mcp
```

For the latest unreleased code, install from the GitHub subdirectory, for example `uv tool install "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/volcengine-ark"`.

Install first and run the local entry point, so that each launch does not resolve dependencies or touch the network. Actual startup time depends on the machine, dependency cache and client handshake; the repository tests verify that all three entry points complete stdio initialization, tool discovery, a call and shutdown.

### Configure your client

Use absolute paths in each client's MCP config, so GUI clients do not depend on `PATH`:

```bash
claude mcp add volcengine-ark -s user -- ~/.local/bin/volcengine-ark-mcp
codex mcp add volcengine-ark -- ~/.local/bin/volcengine-ark-mcp
grok mcp add -s user volcengine-ark ~/.local/bin/volcengine-ark-mcp
agy mcp add volcengine-ark ~/.local/bin/volcengine-ark-mcp
pi mcp add volcengine-ark -- ~/.local/bin/volcengine-ark-mcp
opencode mcp add --global volcengine-ark -- ~/.local/bin/volcengine-ark-mcp
hermes mcp add volcengine-ark --command ~/.local/bin/volcengine-ark-mcp
```

For other clients, configure a stdio server: set `command` to the absolute path above, with no arguments.

Keep keys and other environment variables out of the config and let the client inherit them from the shell. Codex and Hermes filter environment variables, so forward the variable names explicitly instead of writing values: in Codex add `env_vars = ["ARK_API_KEY", ...]` under `[mcp_servers.<name>]`; in Hermes write `ARK_API_KEY: ${ARK_API_KEY}` under `env`. Codex tool calls time out after 60 seconds by default; for image and video generation set `tool_timeout_sec = 300`. The environment variables each server needs are listed in its own README.

### Update

After a new release, update and then restart the client:

```bash
uv tool upgrade volcengine-ark-mcp ali-bailian-mcp doubao-speech-mcp
```

### Uninstall

Run `uv tool uninstall <name>-mcp`, then remove the matching MCP entry from your client.

### Migrating from seedream-mcp

Run `uv tool uninstall seedream-mcp`, install `volcengine-ark`, replace the MCP name and command in your client, and rename the `SEEDREAM_*` environment variables to `ARK_OUT_DIR` / `ARK_RESOURCE_MODE` / `ARK_JOB_DIR`.

## Usage

The common tool groups are exposed by default. Doubao Speech's `realtime` (persistent realtime sessions) and `admin` (word tables and console management) groups are off by default; `list_speech_capabilities` lists the disabled groups and how to enable them. Set `MCP_TOOL_GROUPS` in the MCP process environment to add or remove groups by purpose, for example `image,jobs,help` for Ark, `language,help` for Bailian, or `speech,jobs,help,realtime` for Doubao Speech. Disabled tools are completely invisible to the model. Groups are fixed at startup, so restart after changing them.

## How it works

The three standalone packages share an HTTP / MCP runtime kept in sync by a check: connection pooling, overall timeouts, cancellation, bounded concurrency, explicit errors and structured results. Build conventions, comparisons with similar implementations, compatibility changes and verification limits are in [MCP build and reliability](docs/mcp-reliability.md).

Per-endpoint and per-model verification for all three MCPs, the discrepancies fixed and how the documents are fetched are in the [official contract audit](docs/official-contracts.md).

## Development

Development checks:

```bash
python3 scripts/sync_shared.py --check
uv sync --locked --project servers/volcengine-ark
uv sync --locked --project servers/ali-bailian
uv sync --locked --project servers/doubao-speech
servers/volcengine-ark/.venv/bin/python -m unittest discover -s servers/volcengine-ark/tests
servers/ali-bailian/.venv/bin/python -m unittest discover -s servers/ali-bailian/tests
servers/doubao-speech/.venv/bin/python -m unittest discover -s servers/doubao-speech/tests
servers/doubao-speech/.venv/bin/python -m unittest discover -s tests
```

After changing the shared sources (`shared/`), run `python3 scripts/sync_shared.py`. CI checks the standalone packages, sync drift, failure contracts and real stdio, and needs no cloud credentials.

### Adding a server

1. Under `servers/<name>/`, create `pyproject.toml` (declaring the `<name>-mcp` entry point in `[project.scripts]`), `src/<name>_mcp/` and `README.md`.
2. Keep selection criteria, key limits, billing and recovery semantics in the tool descriptions; serve long examples on demand through `get_tool_help`, rather than only pointing callers to the README.
3. Register it in the table above.

### Release

Bump the version in `servers/<name>/pyproject.toml` and commit, then push a `<name>-v<version>` tag (for example `git tag volcengine-ark-v0.6.0 && git push origin volcengine-ark-v0.6.0`). `publish.yml` checks the version, runs the tests, builds and publishes through PyPI Trusted Publishing, with no token needed.

### Official documentation updates

`python3 scripts/upstream_docs.py --check-coverage` checks the official source mapping for the remote tools; `python3 scripts/upstream_docs.py` fetches the document bodies and produces candidate model / endpoint changes with a full diff. A manually triggered GitHub Actions workflow is ready; scheduled runs and automatic implementation changes are not enabled.

## License

[MIT](LICENSE) © 2026 hoobnn. Free to use, modify and distribute, provided the copyright notice is kept.
