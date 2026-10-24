# 官方文档变更检查

成功 77 / 77，变更 3，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [doubao-speech/doubao-endtoend-realtime-voice-full-duplex-version](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)；工具：close_realtime_session, open_realtime_session, receive_realtime_events, send_realtime_event
  - doc_links_added: https://docs.volcengine.com/docs/DoubaoVoice/access-mustread?lang=zh)中的音频约束规范输入音频；人声过轻或背景噪声过大均可能导致效果下降
  - doc_links_removed: https://www.volcengine.com/docs/6561/2534847?lang=zh
- **changed** [doubao-speech/doubao-seedrealtime](https://docs.volcengine.com/docs/DoubaoVoice/seedrealtime?lang=zh)；工具：close_realtime_session, open_realtime_session, receive_realtime_events, send_realtime_event
- **changed** [doubao-speech/doubao-voice-document-index](https://docs.volcengine.com/docs/DoubaoVoice)；工具：get_speech_usage_examples, list_speech_capabilities
