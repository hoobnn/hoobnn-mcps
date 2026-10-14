# 官方文档变更检查

成功 17 / 17，变更 5，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [volcengine-ark/ark-chat-api](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)；工具：chat
- **changed** [volcengine-ark/ark-create-model-responses-api](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh)；工具：chat
- **changed** [volcengine-ark/ark-document-index](https://docs.volcengine.com/docs/ark/model-list?lang=zh)；工具：目录发现
  - models_removed: seedance-1-5-pro
  - document_codes_added: get-inference-request-usage-api, get-inference-task-usage-api
  - document_codes_removed: seedance-1-5-pro
- **changed** [volcengine-ark/ark-image-generation-api](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)；工具：generate_image, recover_job
- **changed** [volcengine-ark/ark-web-search](https://docs.volcengine.com/docs/ark/web-search?lang=zh)；工具：chat
