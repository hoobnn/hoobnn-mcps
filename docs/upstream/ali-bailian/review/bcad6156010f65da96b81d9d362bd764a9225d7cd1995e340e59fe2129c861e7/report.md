# 官方文档变更检查

成功 32 / 32，变更 2，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [ali-bailian/bailian-happyhorse-edit](https://help.aliyun.com/zh/model-studio/happyhorse-video-edit-api-reference)；工具：edit_video, get_job
  - endpoints_added: https://{WorkspaceId}.us-east-1.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis, https://{WorkspaceId}.us-east-1.maas.aliyuncs.com/api/v1/tasks/{task_id}
  - endpoints_removed: https://dashscope-us.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis, https://dashscope-us.aliyuncs.com/api/v1/tasks/{task_id}
- **changed** [ali-bailian/bailian-voice-design-guide](https://help.aliyun.com/zh/model-studio/voice-design-user-guide)；工具：design_voice
