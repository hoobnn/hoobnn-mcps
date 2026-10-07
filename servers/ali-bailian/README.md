# ali-bailian-mcp

调用阿里云百炼（DashScope）的 MCP server，提供三个工具：

| 工具 | 作用 |
|---|---|
| `generate_image` | 生图和图片编辑，图片直接存到本地 |
| `chat` | 调用百炼上的语言模型（千问，以及托管的 DeepSeek、Kimi、GLM、MiniMax 等） |
| `list_models` | 列出当前 API Key 能调用的模型 ID |

生图模型（`model` 写别名或完整 ID）：

| 别名 | 模型 | 特点 |
|---|---|---|
| `qwen`（默认） | `qwen-image-3.0-pro` | 文字渲染最强，文生图和编辑二合一 |
| `wan` | `wan2.7-image-pro` | 0–9 张参考图、1K / 2K / 4K、组图、thinking |
| `z` | `z-image-turbo` | 最快最便宜，写实人像和产品图，只支持文生图 |

也可以直接写 `qwen-image-2.0-pro`、`qwen-image-max`、`qwen-image-edit-max`、`wan2.7-image` 等其他 ID。

语言模型别名：`max` → `qwen3.8-max`（默认，能看图）、`plus` → `qwen3.7-plus`、`flash` → `qwen3.8-flash`；其他模型直接写 ID，如 `deepseek-v4-pro`、`kimi-k3`、`glm-5.3`。`chat` 统一走流式接口，支持多轮历史、看图、深度思考开关、JSON 输出和联网搜索。

模型不支持的明显参数组合在本地直接报错，其余交给服务端校验。

## 环境变量

| 变量 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 必需，百炼控制台 → API Key（北京地域） |
| `BAILIAN_OUT_DIR` | 图片输出目录，默认 `~/Downloads/ali-bailian` |
| `BAILIAN_RESOURCE_MODE` | 交付方式：`local`（默认）下载到本地，`url` 只返回 24 小时内有效的链接 |
| `DASHSCOPE_BASE_URL` | 默认 `https://dashscope.aliyuncs.com`；新加坡地域用 `https://dashscope-intl.aliyuncs.com`，key 不能跨地域混用 |

参数说明见工具描述（`src/ali_bailian_mcp/server.py`），接口细节以百炼的[文生图](https://help.aliyun.com/zh/model-studio/text-to-image)和 [OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)文档为准。
