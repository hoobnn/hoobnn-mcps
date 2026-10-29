# 2026-10-29 人工契约复核

结论：有两处契约变化需要适配（Seed-Realtime 客户端打断、流式识别 `audio.codec`），其余为链接迁移、格式转换与勘误。已发布 `0.5.2`（待主分支合并后发版）。完整判断见 [审计报告](../../../../audits/doubao-speech.md)。此审查与原自动捕获报告分开保存。

## 为什么 77 个来源全部显示 changed

- 相对主分支基线：65 个来源正文 SHA-256 完全相同（diff 为 0 行）；12 个正文有变化。
- 77 个来源的 `url` 与 `fetch_url` 都变了：PR #24 已把登记迁到 `docs/doubao-voice/*` slug 与数字 LibraryID/DocumentID，基线比较包含这两个字段，所以全部判为 changed。工具映射 `tools` 无变化。
- 12 个有正文变化的文档中，大部分只是 HTML 标签转 Markdown、示例代码块改为 `mixin-react` 组件、内链从 `DoubaoVoice/*`、`docs/6561/*` 迁到 `doubao-voice/*`，报告里的 `endpoints_added` / `doc_links_*` 多数是解析格式变化造成的假差异（例如 ASR 的两个 `sauc` endpoint 在旧文本里就存在，现在被写成 Markdown 链接）。
- `doubao-voice-document-index` 的 3147 行 diff 是目录 `DocumentCode` 从 CamelCase 改为 kebab-case（如 `Accessmust-read` 变 `access-must-read`），无新增产品页。

## 逐项判断

| 文档 | 变化 | 处理 |
| --- | --- | --- |
| seedrealtime | 删除“不再支持客户端打断、`response.cancel` 已废弃”的说明，新增“客户端打断”上行事件 `response.cancel`（取消进行中的响应，由 `response.canceled` 确认） | 适配：放开 mode=seed 对 `response.cancel` 的本地拦截，工具帮助、使用示例、中英文 README 同步；未连真实服务验证 |
| 双向 / 单向流式 ASR websocket | 音频参数表不再列 `audio.codec`（原为 `raw` / `opus`，默认 raw） | 适配：流式识别不再显式发送 `codec="raw"`，默认即 raw；录音文件识别的 `ogg` + `opus` 未变 |
| 录音文件识别极速版、提交任务（两个）、单向流式 ASR | 罗马尼亚语代码勘误 `ro-R0` 变 `ro-RO` | 代码未内置语种表，无需改 |
| 双向 TTS websocket | 字段名勘误 `SessioId` 变 `SessionId` | 代码使用 `session_id` 协议字段，无需改 |
| 查询任务结果（http-1） | 响应字段表由 HTML 转 Markdown，字段无增减 | 仅记录 |
| 单向 TTS http / websocket、端到端实时 | 仅内链迁移与示例组件化 | 仅记录；接入必读链接已指向 `access-must-read` |
| 其余 65 个来源 | 正文无变化 | 无 |

同时把包内残留的旧链接迁到当前 canonical：`streaming_asr.py`、`server.py` 的音色列表、`products.py` 的 `asr_idle`（极速版识别）、`management.py` 注释。审计文档中的历史记录（旧 `LibraryCode=DoubaoVoice` 抓取方式）保留为历史事实。

## 最新正文与快照

- 重抓：来源 77/77 成功，0 错误；相对本 PR 待审基线 0 差异。
- 全部基线快照保留，原待审基线与完整 diff 不改。

## 本地验证

- 豆包语音离线测试：155 项通过（seed 模式 `response.cancel` 用例改为期望放行，流式识别用例去掉 `codec`）。
- 跨包、共享运行时和文档链路测试：43 项通过。
- `python3 scripts/upstream_docs.py --check-coverage`：144 个来源覆盖全部远程工具。
- `python3 scripts/sync_shared.py --check` 与 `git diff --check` 通过；`0.5.2` wheel / sdist 构建成功。
- 没有调用真实语音 API。Seed `response.cancel` 与省略 `codec` 的线上行为未做真实账号验证，以官方文档为准。
