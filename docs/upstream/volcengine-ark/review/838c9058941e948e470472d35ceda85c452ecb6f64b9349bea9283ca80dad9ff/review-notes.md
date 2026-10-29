# 2026-10-29 人工契约复核

结论：运行时请求协议无需改动，没有任何包内使用的模型进入弃用/下线名单。唯一的行为性变化是 Draft 视频任务 ID 有效期，已同步工具说明和中英 README，包版本 0.6.2 升到 0.6.3。完整判断见 [审计报告](../../../../audits/volcengine-ark.md)。此审查与原自动捕获报告分开保存。

## 最新正文与快照

- 重抓结果：来源 17/17 成功，0 错误；相对本 PR 待审基线 0 差异（`sources=17/17 changes=0 errors=0`）。
- 18 项变化中 8 个 diff 为 0 行（`base-url-and-authentication`、`image-generation-api`、`multimodal-vectorization-api`、`seedance-2-0`、`seedream-5-0-pro`、`textvectorizationapi`、`vectorization` 等），正文无字面差异，仅指纹或元数据变化，不涉及契约。
- `ark-seedream-4-0-5-0` removed 与 `ark-image-generation-tutorial` added 是 PR #24 登记迁移造成的基线追平；新教程正文中的 `doubao-seedream-5-0-flash-260915`、`doubao-seedream-5-0-lite-260128`、`doubao-seedream-4-0-250828` 与包内 `ark.MODELS`、生命周期预检一致，无需改动。

## 逐项判断

|来源 |变化 |处理 |
|---|---|---|
|`ark-model-deprecation-notice` |仅新增 LTS 机制说明、`doubao-seed-2-0-lite/mini-260428` 加 LTS 标记、内链由 `/docs/ark/...` 迁到 `/docs/...`；下线清单未新增或删除模型 |包内默认与别名模型（`doubao-seed-2-1-pro-260628`、`doubao-seedance-2-5-260628`、`doubao-seedance-2-0-260128` / `fast-260128` / `mini-260615`、`doubao-seedream-5-0-pro-260628` / `flash-260915`）均不在名单。Seedream lite 的 2026-11-24 关停处理保持不变 |
|`ark-model-list` |新增 `kimi-k3-1-pro-261024` 与 Messages API 支持列；LTS 标记；Seedream 教程链接迁移 |包内没有硬编码模型表，`chat` 接受完整模型 ID，不增别名、默认 pro 不变 |
|`ark-chat-api` |`kimi-k3-1-pro-261024`：temperature 固定 1.0、top_p 固定 0.95、frequency/presence_penalty 固定 0.0，其他值报错；Kimi 停止词最多 5 个；新增 Chat API `web_search_options`、`annotations`、`usage.tool_usage` |`chat` 默认不注入这些参数，透传可用，补中英 README 说明限制。`web_search=true` 仍走已验证的 Responses 路径，Chat 内置搜索只记录，不接入 |
|`ark-create-model-responses-api` |3902 行 diff 主要为 `取值固定为 ...` 字段说明重写；新增 kimi 与 `doubao-seed-2-0-code-preview` 的 temperature/top_p 固定值说明 |`chat` 在 `web_search` / `previous_response_id` 时使用 Responses，请求体不设置这些参数，无需改动 |
|`ark-create-video-generation-task-api`、`ark-get-video-generation-task-api`、`ark-seedance-2-5` |2026-10-28 10:00（UTC+8）起创建的 Draft 视频任务 ID 有效期 14 天，此前仍为 7 天，其他任务 ID 7 天；查询接口不再写「仅查询最近 7 天」区间；Seedance 2.0 及之后的有声视频改为双声道 |工具说明与中英 README 的「Draft ID 有效 7 天」已更新；`poll_video` 把 `expired` 当失败终态的逻辑不受影响，包内无硬编码有效期。双声道属输出规格，不涉及请求字段 |
|`ark-web-search` |新增 Chat API 支持（`web_search_options`），页面结构由 Tabs 改为小节；流程与开通要求不变 |同上，只记录 |
|`ark-document-index` |新增 webhook 端点/事件、Seed3D badcase、LTS 机制、`context-compaction`、`read-docs-from-urls`、OCR 字体等文档；旧 `seedream-4-0-5-0` 页面改为 `image-generation-tutorial` |均为未接入的独立能力，仅记录发现，不宣称支持 |

## 本地验证

- volcengine-ark 离线测试：33 项通过。
- 跨包、共享运行时和文档链路测试（`tests/`）：43 项通过（需要 sync 全部 4 个包的 venv，HTTP fixture 需要绑定 127.0.0.1 临时端口）。
- `python3 scripts/upstream_docs.py --check-coverage`：144 个来源覆盖全部远程工具。
- `python3 scripts/sync_shared.py --check` 与 `git diff --check` 通过。
- `uv build --project servers/volcengine-ark` 成功生成 0.6.3 的 sdist 与 wheel。
- 没有调用真实生成、对话或管理 API。
