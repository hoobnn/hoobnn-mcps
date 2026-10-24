# 官方文档变更检查

成功 36 / 36，变更 3，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [ali-bailian/bailian-chat](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)；工具：chat
- **changed** [ali-bailian/bailian-multimodal-embedding](https://help.aliyun.com/zh/model-studio/multimodal-embedding-api-reference)；工具：embed
  - models_removed: multimodal-embedding-one-peace-v1
- **changed** [ali-bailian/bailian-upload](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)；工具：animate_portrait, edit_video, generate_video
  - endpoints_added: https://dashscope-intl.aliyuncs.com/api/v1, https://dashscope-intl.aliyuncs.com/api/v1/uploads, https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions, https://dashscope.aliyuncs.com/api/v1
