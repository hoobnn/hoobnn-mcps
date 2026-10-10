# hoobnn-mcps

hoobnn 的个人 MCP server 集合。每个 server 是 `servers/<name>/` 下的一个独立 Python 包，已发布到 PyPI，推荐用 [uv](https://docs.astral.sh/uv/) 安装。

| Server | 作用 |
|---|---|
| [`volcengine-ark`](servers/volcengine-ark) | 火山方舟：Seedream图像、Seedance视频、语言与多模态理解、联网搜索、向量化和任务恢复（新增产品待云端验证） |
| [`doubao-speech`](servers/doubao-speech) | 豆包语音：合成（含异步长文本）、识别、音频生成、播客、同传、翻译、妙记、复刻与音色设计；实时对话3.0、词表及控制台管理按需启用 |
| [`ali-bailian`](servers/ali-bailian) | 阿里云百炼：图像、语言、TTS/ASR、音色复刻与设计、视频生成/编辑/数字人、向量与重排序、任务恢复（新增产品待云端验证） |

三个 server 有重叠的能力，工具描述里写明了各自适合的场景，大致分工：

| 需求 | 优先用 | 另一选择 |
|---|---|---|
| 图片：图层拆分、透明背景、组图 | `volcengine-ark` Seedream | — |
| 图片：海报中英文字、多图融合 | `ali-bailian` qwen / wan | — |
| 视频：本地参考视频 / 音频、文档或网页参考 | `ali-bailian` 万相（自动上传） | `volcengine-ark` Seedance（参考素材需公网 URL） |
| 对话：豆包 Seed | `volcengine-ark` `chat` | — |
| 对话：千问、DeepSeek、Kimi、GLM 等 | `ali-bailian` `chat` | — |
| 语音合成、识别、复刻 | `doubao-speech`（中文音色、方言、字幕、长文本、说话人分离） | `ali-bailian`（千问音色；ASR 返回情绪和语种） |

各家复刻 / 设计的音色只能在同一家的合成工具里使用。异步任务在三个 server 里都用 `get_job` 查进度，完成后自动下载结果；`recover_job` 只用来修复交付。

## 安装

用 `uv tool install` 从 PyPI 装到本机，命令在 `~/.local/bin/<name>-mcp`：

```bash
uv tool install volcengine-ark-mcp
uv tool install ali-bailian-mcp
uv tool install doubao-speech-mcp
uv tool upgrade volcengine-ark-mcp ali-bailian-mcp doubao-speech-mcp     # 发布新版本后更新
```

需要未发布的最新代码时，从 GitHub 子目录安装，例如 `uv tool install "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/volcengine-ark"`。

从 `seedream-mcp` 迁移：`uv tool uninstall seedream-mcp` 后安装 `volcengine-ark`，客户端里的 MCP 名和命令一并替换，`SEEDREAM_*` 环境变量改为 `ARK_OUT_DIR` / `ARK_RESOURCE_MODE` / `ARK_JOB_DIR`。

推荐先安装，再通过本地入口运行，避免每次启动都解析依赖和访问网络。实际启动时间受机器、依赖缓存和客户端握手影响；仓库测试验证三个入口都能完成 stdio 初始化、工具发现、调用及退出。

各客户端的 MCP 配置里写绝对路径，避免 GUI 客户端找不到 `PATH`：

```bash
claude mcp add volcengine-ark -s user -- ~/.local/bin/volcengine-ark-mcp
codex mcp add volcengine-ark -- ~/.local/bin/volcengine-ark-mcp
grok mcp add -s user volcengine-ark ~/.local/bin/volcengine-ark-mcp
agy mcp add volcengine-ark ~/.local/bin/volcengine-ark-mcp
pi mcp add volcengine-ark -- ~/.local/bin/volcengine-ark-mcp
opencode mcp add --global volcengine-ark -- ~/.local/bin/volcengine-ark-mcp
hermes mcp add volcengine-ark --command ~/.local/bin/volcengine-ark-mcp
```

其他客户端按 stdio server 配置：`command` 写上面的绝对路径，不带参数。

key 等环境变量不写进配置，由客户端从 shell 环境继承。Codex 和 Hermes 会过滤环境变量，要显式转发变量名而不是写值：Codex 在 `[mcp_servers.<name>]` 里加 `env_vars = ["ARK_API_KEY", ...]`，Hermes 在 `env` 里写 `ARK_API_KEY: ${ARK_API_KEY}`。Codex 的工具调用默认 60 秒超时，生图和视频建议设 `tool_timeout_sec = 300`。

## 新增一个 server

1. 在 `servers/<name>/` 下建 `pyproject.toml`（`[project.scripts]` 声明 `<name>-mcp` 入口）、`src/<name>_mcp/` 和 `README.md`。
2. 工具描述保留选择条件、关键限制、计费与恢复语义；长示例通过 `get_tool_help` 按需读取，不能只让调用方去看 README。
3. 在上面的表格里登记。

## 稳定性与调用效率

三个独立包共用经过同步校验的 HTTP/MCP 运行时：连接池、总超时、取消、有限并发、明确错误与结构化结果。构建规范、同类实现对照、兼容性变化和验证边界见 [MCP 构建与稳定性](docs/mcp-reliability.md)。

默认暴露常用工具组；豆包语音的 `realtime`（持久实时会话）和 `admin`（词表与控制台管理）默认不启用，`list_speech_capabilities` 会列出未启用的组和启用方法。在 MCP 进程环境中设置 `MCP_TOOL_GROUPS` 可按用途增减，例如方舟 `image,jobs,help`、百炼 `language,help`、豆包语音 `speech,jobs,help,realtime`。被关掉的工具对模型完全不可见，分组在启动时固定，更改后需重启。

开发检查：

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

共享源码修改后执行 `python3 scripts/sync_shared.py`。CI 检查独立包、同步漂移、故障契约与真实 stdio，不需要云服务密钥。

发布：改好 `servers/<name>/pyproject.toml` 的版本号并提交后，推送 `<name>-v<版本>` tag（如 `git tag volcengine-ark-v0.6.0 && git push origin volcengine-ark-v0.6.0`），`publish.yml` 校验版本、跑测试、构建，并通过 PyPI Trusted Publishing 发布，无需 token。

## 官方契约与文档更新

三个 MCP 的逐项接口/模型核实、差异修正及文档抓取方式见 [官方契约审计](docs/official-contracts.md)。

`python3 scripts/upstream_docs.py --check-coverage` 检查远程工具的官方来源映射；`python3 scripts/upstream_docs.py` 拉取正文并生成模型/接口候选变化及完整 diff。已准备手动触发的 GitHub Actions 工作流，尚未启用定时运行或自动修改实现。

## 许可证

[MIT](LICENSE) © 2026 hoobnn。可自由使用、修改和分发，需保留版权声明。
