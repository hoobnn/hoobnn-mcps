# Codex Connector 的 Actions 机器人触发验证

日期：2026-10-12。对象：`hoobnn/hoobnn-mcps` 的接入 PR #1。

## 验证方式

一次性 `push` 工作流在接入分支运行，用 `GITHUB_TOKEN` 调用 GitHub
`issues.createComment`，评论作者确认为 `github-actions[bot]`。请求 Codex
只添加 `docs/audits/connector-probe.md`，内容为
`Actions Connector probe: bot-trigger-v1`，并将提交推回同一个 PR。
禁止修改其他文件、批准、合并、打 tag、发布或调用付费供应商 API。

- [成功工作流](https://github.com/hoobnn/hoobnn-mcps/actions/runs/38213593191)
- [机器人探针评论](https://github.com/hoobnn/hoobnn-mcps/pull/1#issuecomment-6119119186)
- 发送时间：2026-10-12 14:39:31（北京时间）。
- 工作流级 `issues: write` 和 `pull-requests: write` 足以发表评论；未开启仓库的 Actions 创建/批准 PR 开关。
- 第一轮只有 `pull-requests: read` 时发表评论返回 403；补齐评论权限后的重试成功，因此第一轮不是 Connector 拒绝任务的证据。

## 观察结果与范围

Connector 对 PR 打开事件的自动代码审核于北京时间 14:41:12 完成，安全审核于
14:42:02 完成。它们针对先前提交 `092397e`，不是探针评论触发的修改任务。

截至北京时间 14:45:11（发送后 5 分 40 秒），探针评论没有任何 reaction，没有 Connector 任务回复，
PR head 仍为 `8c3e3a009610b6bd7c461ec8ec243abccf7b1bfb`，目标文件未提交。

结论：**尚未验证 Actions 机器人评论能够触发 Connector 的修改任务**。
无回应不能证明永久不支持，也不能排除延迟或账号映射条件；不能据此将无人值守
自动更新切换到 Connector。当前 API Action 方案仍保持未启用，不调用 API。

一次性探针工作流已移除，公开运行记录和评论保留用于复核。不自动合并或发布。

[官方文档](https://learn.chatgpt.com/docs/third-party/github#give-codex-other-tasks)
说明在 PR 评论中用 `@codex` 请求其他任务会启动云端任务，但没有明确保证
`github-actions[bot]` 评论的支持范围。本次验证没有用真人评论替代机器人评论。
