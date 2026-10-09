# volcengine-ark-mcp

调用火山方舟（Volcengine Ark）的 MCP server：Seedream 5.0 生成和编辑图片、Seedance 视频、对话与多模态理解、联网搜索和向量化，产物直接存到本地。

原名 `seedream-mcp`（PyPI 上该名已被他人占用），0.4 起改名，不保留旧命令和 `SEEDREAM_*` 环境变量。

## Seedream 图片生成

| 模型 | 参数 | 独有能力 |
|---|---|---|
| Seedream 5.0 pro（默认） | `model="pro"` → `doubao-seedream-5-0-pro-260628` | 图层拆分、交互编辑、透明背景、fast 模式 |
| Seedream 5.0 lite | `model="lite"` → `doubao-seedream-5-0-260128` | 组图、联网搜索、3K / 4K |

两个模型都支持文生图和单图 / 多图参考生图。模型不支持的参数组合会在本地直接报错，不发请求。

## 环境变量

| 变量 | 说明 |
|---|---|
| `ARK_API_KEY` | 必需，方舟控制台 → API Key 管理 |
| `ARK_OUT_DIR` | 输出目录，默认 `~/Downloads/volcengine-ark` |
| `ARK_RESOURCE_MODE` | 交付方式：`local`（默认）下载到本地，`url` 只返回 24 小时内有效的链接 |
| `ARK_BASE_URL` | 默认 `https://ark.cn-beijing.volces.com/api/v3` |

参数说明见工具描述（`src/volcengine_ark_mcp/server.py`），接口细节以[图片生成 API 文档](https://ark.volcengine.com/region:cn-beijing/docs/ark/image-generation-api)为准。

## 0.3 方舟扩展（未测试）

保留原有生图工具，同时接入方舟其他能力，无需新建MCP配置。

| 工具 | 能力 | 官方来源 |
|---|---|---|
| `generate_video` / `query_video` | Seedance文生、首帧、首尾帧、多模态参考视频 | [创建任务](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)、[查询任务](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh) |
| `chat` | 语言、图片/视频理解、深度思考、结构化输出 | [Chat](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)、[Responses](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh) |
| `chat(web_search=true)` | 联网搜索，保留来源和完整响应 | [Web Search](https://docs.volcengine.com/docs/ark/web-search?lang=zh) |
| `embed` | 文本与多模态向量化 | [向量化](https://docs.volcengine.com/docs/ark/vectorization?lang=zh)、[多模态API](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh) |
| `list_capabilities` | 静态能力目录和边界 | 不联网，不代表账号权限 |
| `list_jobs` / `get_job` / `recover_job` | 本地任务查询与补交付 | 图片和视频留档，跨进程重启恢复 |

### Seedance视频

模型别名：`seedance` → `doubao-seedance-2-5-260628`；`seedance-2` / `seedance-fast` / `seedance-mini` → 相应2.0系列。
也可直接指定完整模型ID或Endpoint ID。不同模型的素材数量、时长、分辨率限制以官方接口为准。

默认 `wait=0`，提交后返回 `task_id`、`job_id`。`query_video(task_id=..., job_id=...)` 复用原目录和下载进度；`recover_job(job_id=...)` 查询原任务，不提交新生成。

图片支持本地路径/data URL/公网URL；视频和音频参考使用公网URL或 `asset://` ID。本轮没有自动上传本地视频/音频。
2.5首帧/首尾帧任务 `ratio=adaptive`；视频编辑通过prompt明确意图，`duration=-1`、`ratio=adaptive`。
`parameters` 可传官方顶层选项，如 `draft`、`return_last_frame`、`output_format`；不能覆盖模型和输入素材。

### 对话与检索

`chat` 默认 `pro` 为 `doubao-seed-2-1-pro-260628`，也可显式指定模型；与生图工具中的pro别名含义不同。
`images` 支持本地图片，`videos` 须公开URL。不开搜索时使用Chat API；开启 `web_search` 或提供 `previous_response_id` 时使用Responses API。
多轮历史采用Chat消息结构，Responses会转换本轮多模态内容；保留 `response_id`、来源注解及完整响应。
`parameters` 透传模型支持的高级选项，不执行模型返回的工具调用。

向量工具须显式指定模型：`texts` 为文本列表；`contents` 为官方类型化数组，例如：

```json
[{"type":"text","text":"猫"},{"type":"image_url","image_url":{"url":"/absolute/cat.png"}}]
```

返回 `data`、`usage` 和完整响应；不自动建索引或知识库。

### 本地恢复

`ARK_JOB_DIR` 默认 `~/.local/share/volcengine-ark-mcp/jobs`。生成前创建记录，响应收到后保留完整响应，内联图片先缓存再交付。
组图逐项记录错误，下载失败可单独补交付；图层记录和 `layers.json` 随恢复更新。部分生成失败会返回 `partial`，不会重新生成失败项。
视频保存原 `task_id`，通过云端查询刷新URL。临时URL或云端任务过期可能无法恢复。

新增返回 `job_id`、`job_state`、`request_id` 和 `artifacts`；生成工具的 `ok` 仅在全部交付时为true。
`get_job.ok` 是记录读取成功；调用超时没拿到ID时可用 `list_jobs` 按时间查找。保留原有files、layers、usage、errors字段。
每项产物记录字节数和SHA-256；下载采用临时文件和原子替换。质量、像素尺寸和媒体播放仍需后续验证。

`url`模式也留存任务元数据；任务目录保存签名URL、响应与图片缓存，不保存API Key。缓存用于恢复，不自动清理。
恢复锁使用POSIX `flock`，面向macOS/Linux。产物默认目录增加随机后缀，避免同秒调用碰撞。

本轮未运行测试、未发起真实生成、未更新已安装MCP。详见 [接入记录](../../docs/mcp-expansion.md)。

产物的 `media_info` 读取PNG头中的实际宽高；若系统已有 `ffprobe`，可读取其他媒体的实际尺寸、时长和音轨信息。不可读取时显式返回 `available=false`，不把请求参数当作实际输出规格。无需新增Python依赖。
