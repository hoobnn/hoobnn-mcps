# 官方文档变更检查

成功 74 / 74，变更 3，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [doubao-speech/doubao-endtoend-realtime-voice-full-duplex-version](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)；工具：close_realtime_session, open_realtime_session, receive_realtime_events, send_realtime_event
- **changed** [doubao-speech/doubao-tonelist-1](https://docs.volcengine.com/docs/DoubaoVoice/Tonelist-1?lang=zh)；工具：open_realtime_session, speech_raw_request, text_to_speech
- **changed** [doubao-speech/doubao-voice-document-index](https://docs.volcengine.com/docs/DoubaoVoice)；工具：get_speech_usage_examples, list_speech_capabilities
  - document_codes_added: podcast, podcast_mustread
