# 官方文档变更检查

成功 17 / 17，变更 18，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [volcengine-ark/ark-base-url-and-authentication](https://docs.volcengine.com/docs/ark/base-url-and-authentication?lang=zh)；工具：chat, embed, generate_image, generate_video, get_job, recover_job
- **changed** [volcengine-ark/ark-chat-api](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)；工具：chat
  - models_added: doubao-seed-2-1-pro-260915, kimi-k3-1-pro-261024
  - endpoints_added: https://ark.cn-beijing.volces.com/api/v3
- **changed** [volcengine-ark/ark-create-model-responses-api](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh)；工具：chat
  - models_added: doubao-seed-2-0-code-preview-260215, doubao-seed-2-0-lite-260215, doubao-seed-2-0-pro-260215, doubao-seed-2-1-pro-260915, kimi-k3-1-pro-261024
  - endpoints_added: https://ark.cn-beijing.volces.com/api/v3
- **changed** [volcengine-ark/ark-create-video-generation-task-api](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)；工具：generate_video
  - models_added: doubao-seedance-1-0-lite-i2v-250428, doubao-seedance-2-0-260128, doubao-seedance-2-5-260628
  - endpoints_added: https://ark.cn-beijing.volces.com/api/v3, https://ark.cn-beijing.volces.com/api/v3/
- **changed** [volcengine-ark/ark-document-index](https://docs.volcengine.com/docs/ark/model-list?lang=zh)；工具：目录发现
  - models_removed: seedream-4-0-5-0
  - document_codes_added: context-compaction, create-webhook-endpoint-api, delete-webhook-endpoint-api, disable-webhook-endpoint-api, enable-webhook-endpoint-api, get-webhook-endpoint-api, get-webhook-event-api, image-generation-tutorial, list-webhook-endpoints-api, list-webhook-events-api, lts-mechanism, ocr-supported-fonts, read-docs-from-urls, receive-webhook-events, reset-webhook-signing-secret-api, seed3d-badcase-query, seed3d-badcase-report, test-webhook-endpoint-api, update-webhook-endpoint-api, webhook-events-reference, webhooks
  - document_codes_removed: seedream-4-0-5-0
- **changed** [volcengine-ark/ark-get-video-generation-task-api](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh)；工具：get_job, recover_job
  - models_added: doubao-seedance-2-0-260128
  - endpoints_added: https://ark.cn-beijing.volces.com/api/v3, https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/$TASK_ID
- **changed** [volcengine-ark/ark-image-generation-api](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)；工具：generate_image, recover_job
- **added** [volcengine-ark/ark-image-generation-tutorial](https://docs.volcengine.com/docs/ark/image-generation-tutorial?lang=zh)；工具：generate_image
  - models_added: Doubao, Seedream, doubao, doubao-seedream-4-0-250828, doubao-seedream-5-0-flash-260915, doubao-seedream-5-0-lite-260128, seedream
  - endpoints_added: https://ark.cn-beijing.volces.com/api/v3, https://ark.cn-beijing.volces.com/api/v3/images/generations
  - doc_links_added: https://docs.volcengine.com/docs/TorchObjectStorage/Datasubscription-5?lang=zh, https://www.volcengine.com/experience/ark?mode=vision&model=doubao-seedream-4-0-250828
- **changed** [volcengine-ark/ark-model-deprecation-notice](https://docs.volcengine.com/docs/ark/model-deprecation-notice?lang=zh)；工具：chat, embed, generate_image, generate_video
- **changed** [volcengine-ark/ark-model-list](https://docs.volcengine.com/docs/ark/model-list?lang=zh)；工具：chat, embed, generate_image, generate_video, list_capabilities
  - models_added: kimi-k3-1-pro-261024
- **changed** [volcengine-ark/ark-multimodal-vectorization-api](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh)；工具：embed
- **changed** [volcengine-ark/ark-seedance-2-0](https://docs.volcengine.com/docs/ark/seedance-2-0?lang=zh)；工具：generate_video
- **changed** [volcengine-ark/ark-seedance-2-5](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)；工具：generate_video, get_job, recover_job
- **removed** [volcengine-ark/ark-seedream-4-0-5-0](https://docs.volcengine.com/docs/ark/seedream-4-0-5-0?lang=zh)；工具：generate_image
  - models_removed: Doubao, Seedream, doubao, doubao-seedream-4-0-250828, doubao-seedream-5-0-flash-260915, doubao-seedream-5-0-lite-260128, seedream
  - endpoints_removed: https://ark.cn-beijing.volces.com/api/v3, https://ark.cn-beijing.volces.com/api/v3/images/generations
  - doc_links_removed: https://docs.volcengine.com/docs/TorchObjectStorage/Datasubscription-5?lang=zh, https://www.volcengine.com/experience/ark?mode=vision&model=doubao-seedream-4-0-250828
- **changed** [volcengine-ark/ark-seedream-5-0-pro](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)；工具：generate_image
- **changed** [volcengine-ark/ark-textvectorizationapi](https://docs.volcengine.com/docs/ark/TextVectorizationAPI?lang=zh)；工具：embed
- **changed** [volcengine-ark/ark-vectorization](https://docs.volcengine.com/docs/ark/vectorization?lang=zh)；工具：embed
- **changed** [volcengine-ark/ark-web-search](https://docs.volcengine.com/docs/ark/web-search?lang=zh)；工具：chat
  - endpoints_added: https://ark.cn-beijing.volces.com/api/v3/chat/completions
