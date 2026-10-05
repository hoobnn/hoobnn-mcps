# hoobnn-mcps

hoobnn 的个人 MCP server 集合。每个 server 是 `servers/<name>/` 下的一个独立 Python 包，用 [uv](https://docs.astral.sh/uv/) 直接从 GitHub 安装，不发 PyPI。

| Server | 作用 |
|---|---|
| [`seedream`](servers/seedream) | 火山方舟 Seedream 5.0（pro / lite）生图：文生图、多图参考、组图、联网搜索、图层拆分、交互编辑、透明背景 |

## 安装

```bash
uv tool install "git+https://github.com/hoobnn/hoobnn-mcps#subdirectory=servers/seedream"
uv tool upgrade seedream-mcp     # 更新
```

装好后命令在 `~/.local/bin/seedream-mcp`。各客户端的 MCP 配置里写绝对路径，避免 GUI 客户端找不到 `PATH`：

```bash
# Claude Code
claude mcp add seedream -s user -- ~/.local/bin/seedream-mcp
# Codex
codex mcp add seedream -- ~/.local/bin/seedream-mcp
```

其他客户端按 stdio server 配置：`command` 写上面的绝对路径，不带参数。key 等环境变量不写进配置，由客户端从 shell 环境继承；客户端不继承时，在配置的 `env` 里补上。

## 新增一个 server

1. 在 `servers/<name>/` 下建 `pyproject.toml`（`[project.scripts]` 声明 `<name>-mcp` 入口）、`src/<name>_mcp/` 和 `README.md`。
2. 工具描述要自带用法：调用方只能看到工具描述，看不到 README。
3. 在上面的表格里登记。
