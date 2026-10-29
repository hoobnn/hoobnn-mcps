# 官方文档变更检查

成功 36 / 36，变更 4，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [ali-bailian/bailian-asr-models](https://help.aliyun.com/zh/model-studio/asr-model)；工具：speech_to_text
- **changed** [ali-bailian/bailian-model-pricing](https://help.aliyun.com/zh/model-studio/model-pricing)；工具：目录发现
  - models_added: Qwen-Audio-ASR, Qwen-Audio-ASR-Filetrans, Qwen-Audio-ASR-Message, Qwen-Audio-ASR-Streaming
  - models_removed: Qwen-Audio-3.1-ASR-Flash-Message, Qwen-Audio-3.x-ASR-Flash, Qwen-Audio-3.x-ASR-Flash-Filetrans, Qwen-Audio-3.x-ASR-Flash-Streaming
- **changed** [ali-bailian/bailian-rate-limit](https://help.aliyun.com/zh/model-studio/rate-limit)；工具：目录发现
- **changed** [ali-bailian/bailian-voice-clone-guide](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)；工具：clone_voice
