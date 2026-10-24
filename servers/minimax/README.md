# MiniMax MCP

独立重写的 MiniMax stdio MCP，重点支持 H3 V2。包名 `hoobnn-minimax-mcp`，不是官方 `minimax-mcp`，不依赖后者。沿用本仓库的连接池、超时取消、任务持久化与交付恢复机制。

`0.3.0` 的 `generate_video` 新增 `MiniMax-H3-Highspeed`（仅 768P）与 `MiniMax-H3-Lite`（480P / 768P，多模态参考需显式指定具体 `ratio`），均为 4–15 秒、不支持 2K。

`0.2.0` 将 `enhance_video_prompt` 更名为 `create_h3_context_ir_task`，与官方「创建 H3-Context-IR 任务」对应；旧名不保留别名，这是不兼容变更。

## 安装与迁移

从 PyPI 安装：

```bash
uv tool install hoobnn-minimax-mcp
```

本地开发可在仓库根目录运行 `uv tool install ./servers/minimax`。

客户端命令改为 `~/.local/bin/hoobnn-minimax-mcp` 的绝对路径，不带参数。原来的 `uvx minimax-mcp -y` 启动的是官方包，单纯升级它不会获得本实现。需要重启 MCP 客户端后才会发现新工具。

| 环境变量 | 用途 |
|---|---|
| `MINIMAX_API_KEY` | 必填，与 API 区域匹配；不写入任务记录 |
| `MINIMAX_API_HOST` | 默认 `https://api.minimax.cn`；也接受已有的 `https://api.minimaxi.com` 或国际站 `https://api.minimax.io` |
| `MINIMAX_OUT_DIR` | 默认 `~/Downloads/minimax`，兼容旧 `MINIMAX_MCP_BASE_PATH` |
| `MINIMAX_RESOURCE_MODE` | `local`（默认）或 `url`；兼容旧 `MINIMAX_API_RESOURCE_MODE` |
| `MINIMAX_JOB_DIR` | 默认 `~/.local/share/hoobnn-minimax-mcp/jobs` |
| `MCP_TOOL_GROUPS` | 默认启用 video,image,speech,music,files,jobs,help；取消/删除需显式加入 admin |

配置保留旧四个环境变量即可。任务文件包含素材引用、最终提示词、临时结果 URL 和响应，不包含 API key。恢复锁依赖 POSIX，支持 macOS/Linux。

## H3 视频

| 工具 | 行为 |
|---|---|
| `generate_video` | 文生、首帧、尾帧、首尾帧、多模态参考，支持 H3 / H3-Highspeed / H3-Lite / H3-Max |
| `create_h3_context_ir_task` | 创建 H3-Context-IR 任务（`/v2/h3_context_ir`），异步生成增强提示词；不自动再提交视频 |
| `regenerate_video` | 创建视频再生成任务（`/v2/video_regeneration`），合规的 H3 768P 产物再生成 2K；不是通用超分 |
| `query_video_generation` / `get_job` | 查询 V2 任务并交付结果 |
| `list_video_tasks` | 分页列出云端最近 7 天任务 |
| `delete_video_task` | 取消排队任务或删除已结束任务记录，默认隐藏 |
| `upload_file` | 上传生成素材或音色复刻音频，返回 `mm_file://` 引用 |
| `list_jobs` / `recover_job` | 本地任务发现及交付恢复，不重新生成 |

`MiniMax-H3` 支持 768P / 2K、4–15 整数秒，默认 2K、5 秒；`MiniMax-H3-Highspeed` 仅支持 768P、4–15 秒；`MiniMax-H3-Lite` 支持 480P / 768P、4–15 秒，默认 768P，多模态参考须显式指定具体 `ratio`（不支持 adaptive）；`MiniMax-H3-Max` 支持 480P / 768P、5–15 秒，默认 768P。后三者均不支持 2K。

```json
{"prompt":"小猫抬头望向窗外，雨点轻敲玻璃，镜头缓慢靠近。", "model":"MiniMax-H3", "resolution":"2K", "duration":5, "ratio":"16:9"}
```

`prompt` 可搭配 `first_frame`、`last_frame` 或 `reference_images` / `reference_videos` / `reference_audios`。也可单独提供官方 `content` 数组。首尾帧与参考素材互斥；所有模式需要一个非空文本项。文生默认 16:9，图生跟随原图，其余默认 adaptive。

图片、视频、音频支持公网 URL、`mm_file://ID`、Base64 data URI 和本地绝对路径。本地素材会上传，生成输入文件有效期 7 天；上传接口负责校验真实尺寸、时长和编码。调用前本地校验类型、大小、数量、模型和组合规则。图片最多 30 MB、参考视频 50 MB、参考音频 15 MB，请求体最多 64 MB。

生成默认只提交，返回 `job_id` / `task_id` 与 `completed=false`。`get_job` 查询完成后自动交付；`wait` 可设 0–90 秒。云端任务查询窗口 7 天，成功响应直接提供 `task.content.url`，不走旧的 `file_id` 下载链路。下载失败时 `recover_job` 重新查询原任务刷新链接，并跳过完整文件。

每次生成、提示词增强和再生成是独立计费请求。提交前写任务记录；网络超时且没有 `task_id` 时标记 `unknown`，不会自动重试。先用 `list_jobs` / `list_video_tasks` 核对，再用已找到的 `task_id` 接续。任务总超时由 `MCP_TOOL_TIMEOUT_SEC` 控制，默认 300 秒。

## 保留的媒体能力

- `text_to_audio`：同步语音，默认 `speech-2.8-hd`，最多 10000 字符。
- `list_voices`、`voice_clone`、`voice_design`：音色查询、复刻、设计；复刻原音频可传本地文件或已有 file_id。
- `text_to_image`：`image-01` / `image-01-live`，支持人物参考及部分生成失败报告。
- `music_generation`：`music-3.0` / `music-2.6` 歌曲或纯音乐。官方 2026-08-20 公告已停止免费音乐接口，付费接口仅历史付费用户继续使用；不承诺当前账号权限。

2026-10-24 已复核全部 14 个官方接口页：创建任务新增 `MiniMax-H3-Highspeed`、`MiniMax-H3-Lite`，已接入并离线验证；Context-IR 和再生成的请求契约未变。音乐停服公告仍在，不能据此认定免费接口或新账号已恢复开放。完整差异与本地验收见 [契约复核](../../docs/minimax-contracts.md#2026-10-24-文档更新审查)。

工具名尽量沿用官方 MCP，但不是所有旧参数的原样替代：视频只实现 H3 V2，不接受旧 Hailuo V1 模型/任务；`first_frame_image` 改为 `first_frame`，`async_mode` 改为默认异步的 `wait`。`voice_clone` 的 URL 下载参数 `is_url` 改为本地 `file` 或预上传 `file_id`。不实现本机扬声器 `play_audio`、语言模型、ASR、WebSocket 流式和异步长文本语音。

## 官方来源与验证

以 [中国站接口概览](https://platform.minimax.cn/docs/api-reference/api-overview) 和各接口 OpenAPI 正文为准，首次核对日期 2026-10-11，最近复核 2026-10-23。来源映射见仓库 `docs/audits/minimax-sources.json`，差异及限制见 `docs/minimax-contracts.md`。

离线测试覆盖 V2 请求、任务状态、下载恢复、旧媒体响应、V1/V2 错误和真实 MCP stdio。没有进行付费云端生成，也不把离线通过当成账号权限或成片质量验收。

```bash
uv sync --locked --project servers/minimax
servers/minimax/.venv/bin/python -m unittest discover -s servers/minimax/tests
python3 scripts/sync_shared.py --check
python3 scripts/upstream_docs.py --check-coverage
uv build --project servers/minimax
```
