# 官方文档变更检查

成功 14 / 14，变更 4，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [minimax/speech-t2a-http](https://platform.minimax.cn/docs/api-reference/speech-t2a-http)；工具：recover_job, text_to_audio
  - doc_links_added: https://platform.minimaxi.com/docs/guides/speech-t2a-websocket.md#接入地址
- **changed** [minimax/video-generation-v2-create](https://platform.minimax.cn/docs/api-reference/video-generation-v2-create)；工具：generate_video
  - models_added: MiniMax-H3-Highspeed, MiniMax-H3-Lite
- **changed** [minimax/video-generation-v2-h3-context-ir](https://platform.minimax.cn/docs/api-reference/video-generation-v2-h3-context-ir)；工具：create_h3_context_ir_task
  - doc_links_added: https://platform.minimaxi.com/docs/api-reference/video-generation-v2-query.md)或[查询任务列表](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-list.md)接口查询。H3-Context-IR
- **changed** [minimax/video-generation-v2-regeneration](https://platform.minimax.cn/docs/api-reference/video-generation-v2-regeneration)；工具：regenerate_video
  - doc_links_added: https://platform.minimaxi.com/docs/api-reference/video-generation-v2-query.md)、[查询任务列表](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-list.md)和[取消或删除任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-delete.md)接口管理
