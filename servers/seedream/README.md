# seedream-mcp

调用火山方舟 Seedream 5.0 生成和编辑图片的 MCP server，提供一个 `generate_image` 工具，图片直接存到本地。

| 模型 | 参数 | 独有能力 |
|---|---|---|
| Seedream 5.0 pro（默认） | `model="pro"` → `doubao-seedream-5-0-pro-260628` | 图层拆分、交互编辑、透明背景、fast 模式 |
| Seedream 5.0 lite | `model="lite"` → `doubao-seedream-5-0-260128` | 组图、联网搜索、3K / 4K |

两个模型都支持文生图和单图 / 多图参考生图。模型不支持的参数组合会在本地直接报错，不发请求。

## 环境变量

| 变量 | 说明 |
|---|---|
| `ARK_API_KEY` | 必需，方舟控制台 → API Key 管理 |
| `SEEDREAM_OUT_DIR` | 图片输出目录，默认 `~/Downloads/seedream` |
| `SEEDREAM_RESOURCE_MODE` | 交付方式：`local`（默认）下载到本地，`url` 只返回 24 小时内有效的链接 |
| `ARK_BASE_URL` | 默认 `https://ark.cn-beijing.volces.com/api/v3` |

参数说明见工具描述（`src/seedream_mcp/server.py`），接口细节以[图片生成 API 文档](https://ark.volcengine.com/region:cn-beijing/docs/ark/image-generation-api)为准。
