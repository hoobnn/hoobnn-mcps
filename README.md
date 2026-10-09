# hoobnn-mcps

hoobnn 的个人 MCP server 集合。每个 server 是 `servers/<name>/` 下的一个独立 Python 包，用 [uv](https://docs.astral.sh/uv/) 直接从 GitHub 安装，不发 PyPI。

| Server | 作用 |
|---|---|
| [`volcengine-ark`](servers/volcengine-ark) | 火山方舟：Seedream图像、Seedance视频、语言与多模态理解、联网搜索、向量化和任务恢复（新增接入未测试） |
| [`doubao-speech`](servers/doubao-speech) | 豆包语音：合成、复刻、音色设计、识别、音频生成、播客、实时对话3.0、同传、翻译、妙记、词表及控制台管理 |
| [`ali-bailian`](servers/ali-bailian) | 阿里云百炼：图像、语言、TTS/ASR、音色复刻与设计、视频生成/编辑/数字人、向量与重排序、任务恢复（新增接入未测试） |

## 安装

用 `uv tool install` 从 GitHub 装到本机，命令在 `~/.local/bin/<name>-mcp`：

```bash
uv tool install "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/volcengine-ark"
uv tool install "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/ali-bailian"
uv tool install "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/doubao-speech"
uv tool upgrade volcengine-ark-mcp ali-bailian-mcp doubao-speech-mcp     # 推送新代码后更新
```

从 `seedream-mcp` 迁移：`uv tool uninstall seedream-mcp` 后安装 `volcengine-ark`，客户端里的 MCP 名和命令一并替换。

不用 `uvx --from git+...` 直接运行：它每次启动都要联网确认最新提交，要 2–4 秒，`codex exec`、`opencode run` 这类无头调用会在 server 起来前就开始回答，拿不到工具。装好后启动约 0.3 秒。

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
2. 工具描述要自带用法：调用方只能看到工具描述，看不到 README。
3. 在上面的表格里登记。
