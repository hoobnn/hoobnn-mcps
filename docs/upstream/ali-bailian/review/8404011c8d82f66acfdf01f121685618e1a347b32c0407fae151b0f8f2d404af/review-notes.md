# 2026-10-26 人工契约复核

结论：本次为文档适配，无需修改运行时请求协议。完整判断与官方链接见 [审计报告](../../../../audits/ali-bailian.md)。中英文 README 已补充调用约束；此审查与原自动捕获报告分开保存。

## 最新正文与快照

- 最新重抓时间（UTC）：`2026-10-26T08:08:47.868826+00:00`。
- 来源 36/36 成功，0 错误；相对本 PR 待审基线 0 差异。
- 全部 36 个基线快照解压及 SHA-256 校验通过，保留原待审基线与完整 diff。

## 本地验证

- 供应商离线测试：51 项通过。
- 跨包、共享运行时和文档链路测试：42 项通过（HTTP fixture 需要允许绑定 127.0.0.1 临时端口；沙箱内最初 8 项因此失败，放开本地绑定后全部通过）。
- `python3 scripts/upstream_docs.py --check-coverage`：144 个来源覆盖全部远程工具。
- `python3 scripts/sync_shared.py --check` 与 `git diff --check` 通过。
- 没有调用真实生成、语音或管理 API；本次无需提升包版本。

Kimi 请求构造补充离线探针：3 个完整模型 ID 默认均不注入 `n`、`parallel_tool_calls`、`reasoning_effort`、`enable_thinking_history`；显式 `reasoning_effort=max` / `enable_thinking_history=true` 正确透传，assistant 历史 `reasoning_content` 原样保留。
