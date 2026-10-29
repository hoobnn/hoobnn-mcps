# 2026-10-29 人工契约复核

结论：声音复刻新加坡地域新增 `qwen-audio-3.1-tts-flash`，同步 `clone_voice` 工具帮助并发布 0.7.2；其余变化不影响现有请求协议。完整判断见 [审计报告](../../../../audits/ali-bailian.md)。

## 变化判断

- `bailian-voice-clone-guide`：新加坡支持模型补充 `qwen-audio-3.1-tts-flash`。本地白名单本就包含该模型且不按地域拦截，只更新工具帮助中的地域说明。
- `bailian-asr-models`：`qwen-audio-3.0-asr-flash` 文件上限由 10 MB 调整为 2 GB（时长仍 ≤5 分钟）。`speech_to_text` 只放行 `qwen3-asr-flash`，其限制未变，无需修改。
- `bailian-model-pricing`：ASR 价格分组标题由 `Qwen-Audio-3.x-ASR-Flash*` 改为 `Qwen-Audio-ASR*`，模型 ID 不变；`qwen-audio-3.0-asr-flash*` 的免费额度取消；Fun-ASR 实时表格行重排。不硬编码价格，只记录。
- `bailian-rate-limit`：`deepseek-v4.1-flash(-1017)`、`glm-5.3` 等改为动态限流。本 MCP 不硬编码限额，只记录。

## 最新正文与快照

- 最新重抓：2026-10-29，来源 36/36 成功，0 错误；相对本 PR 待审基线 0 差异。

## 本地验证

- 百炼离线测试 51 项通过；跨包、共享运行时和文档链路测试 43 项通过。
- `scripts/upstream_docs.py --check-coverage`（144 个来源）、`scripts/sync_shared.py --check`、`git diff --check` 通过；0.7.2 wheel/sdist 构建通过。
- 没有调用真实生成、语音或管理 API。
