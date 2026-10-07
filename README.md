# hoobnn-mcps

hoobnn 的个人 MCP server 集合。每个 server 是 `servers/<name>/` 下的一个独立 Python 包，用 [uv](https://docs.astral.sh/uv/) 直接从 GitHub 安装，不发 PyPI。

| Server | 作用 |
|---|---|
| [`seedream`](servers/seedream) | 火山方舟 Seedream 5.0（pro / lite）生图：文生图、多图参考、组图、联网搜索、图层拆分、交互编辑、透明背景 |
| [`ali-bailian`](servers/ali-bailian) | 阿里云百炼：千问 / 万相 / Z-Image 生图与编辑，调用千问及百炼托管的 DeepSeek、Kimi、GLM 等语言模型 |

## 安装

用 `uvx` 直接从 GitHub 运行，不需要预先安装。以 seedream 为例，其他 server 把 `seedream` 换成对应目录名（命令是 `<name>-mcp`）：

```bash
# Claude Code
claude mcp add seedream -s user -- uvx --from "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/seedream" seedream-mcp
claude mcp add ali-bailian -s user -- uvx --from "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/ali-bailian" ali-bailian-mcp
# Codex
codex mcp add seedream -- uvx --from "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/seedream" seedream-mcp
```

其他客户端按 stdio server 配置：`command` 写 `uvx`，`args` 写 `["--from", "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/<name>", "<name>-mcp"]`。GUI 客户端找不到 `PATH` 时，`command` 改写 `uvx` 的绝对路径（`which uvx`）。

uvx 会缓存已解析的版本；要拉取最新代码，在 `uvx` 后加一次 `--refresh` 运行（例如 `uvx --refresh --from "git+..." seedream-mcp`）。

key 等环境变量不写进配置，由客户端从 shell 环境继承；客户端不继承时，在配置的 `env` 里补上。

## 新增一个 server

1. 在 `servers/<name>/` 下建 `pyproject.toml`（`[project.scripts]` 声明 `<name>-mcp` 入口）、`src/<name>_mcp/` 和 `README.md`。
2. 工具描述要自带用法：调用方只能看到工具描述，看不到 README。
3. 在上面的表格里登记。
