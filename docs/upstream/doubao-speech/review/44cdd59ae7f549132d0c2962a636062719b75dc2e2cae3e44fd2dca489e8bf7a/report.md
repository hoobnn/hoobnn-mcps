# 官方文档变更检查

成功 77 / 77，变更 5，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [doubao-speech/doubao-access-mustread](https://docs.volcengine.com/docs/DoubaoVoice/access-mustread?lang=zh)；工具：close_realtime_session, open_realtime_session, receive_realtime_events, send_realtime_event
  - models_added: Doubao
- **changed** [doubao-speech/doubao-audio1-5marketingplan](https://docs.volcengine.com/docs/DoubaoVoice/audio1-5marketingplan?lang=zh)；工具：generate_audio
- **changed** [doubao-speech/doubao-podcast](https://docs.volcengine.com/docs/DoubaoVoice/podcast?lang=zh)；工具：generate_podcast
- **added** [doubao-speech/doubao-seedrealtime](https://docs.volcengine.com/docs/DoubaoVoice/seedrealtime?lang=zh)；工具：close_realtime_session, open_realtime_session, receive_realtime_events, send_realtime_event
  - models_added: Doubao
  - endpoints_added: wss://openspeech.bytedance.com/api/v3/seedrealtime
  - doc_links_added: https://docs.volcengine.com/docs/6561/1257544?lang=zh, https://docs.volcengine.com/docs/6561/1257544?lang=zh)，同时也支持复刻音色, https://docs.volcengine.com/docs/87772/2272949?lang=zh, https://docs.volcengine.com/docs/87772/2272953?redirect=1&lang=zh, https://docs.volcengine.com/docs/DoubaoVoice/access-mustread?lang=zh#llUZxXnt, https://www.volcengine.com/docs/6561/2549732?AuditDocumentID=397063&lang=zh, https://www.volcengine.com/docs/6561/2549732?AuditDocumentID=397063&lang=zh#llUZxXnt, https://www.volcengine.com/docs/6561/2549732?AuditDocumentID=397063&lang=zh)，了解协议设计原则、注意事项与最佳实践等，避免因协议不熟悉导致接入异常
- **changed** [doubao-speech/doubao-voice-document-index](https://docs.volcengine.com/docs/DoubaoVoice)；工具：get_speech_usage_examples, list_speech_capabilities
  - models_added: Doubao-Seed-Realtime-1.0
  - document_codes_added: history-podcast, seedrealtime
