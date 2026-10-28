# 官方文档变更检查

成功 36 / 36，变更 18，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [ali-bailian/bailian-asr](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)；工具：speech_to_text
  - models_removed: QwenTranscription.async_call, QwenTranscription.fetch, QwenTranscription.wait, qwen_asr
- **changed** [ali-bailian/bailian-catalog](https://help.aliyun.com/zh/model-studio/list-models)；工具：list_models
- **changed** [ali-bailian/bailian-chat-models](https://help.aliyun.com/zh/model-studio/text-generation-model)；工具：chat
  - models_added: MiniMax-M3.1-Flash, deepseek-v4.1-flash-1017, kimi-k2.6, kimi-k3, qwen3.6-27b, qwen3.6-35b-a3b
  - models_removed: deepseek-r1-distill-llama-70b
- **changed** [ali-bailian/bailian-embedding](https://help.aliyun.com/zh/model-studio/embedding)；工具：embed
- **changed** [ali-bailian/bailian-model-directory](https://help.aliyun.com/zh/model-studio/models)；工具：目录发现
  - models_added: qwen-audio-3-1-realtime-flash, qwen-audio-3.1-realtime-flash
- **changed** [ali-bailian/bailian-model-lifecycle](https://help.aliyun.com/zh/model-studio/newly-released-models)；工具：目录发现
  - models_added: qwen-audio-3.1-realtime-flash
- **changed** [ali-bailian/bailian-model-pricing](https://help.aliyun.com/zh/model-studio/model-pricing)；工具：目录发现
  - models_added: qwen-audio-3.1-realtime-flash
- **changed** [ali-bailian/bailian-multimodal-embedding](https://help.aliyun.com/zh/model-studio/multimodal-embedding-api-reference)；工具：embed
  - doc_links_added: https://help.aliyun.com/zh/model-studio/developer-reference/error-code, https://help.aliyun.com/zh/model-studio/get-api-key
- **changed** [ali-bailian/bailian-rate-limit](https://help.aliyun.com/zh/model-studio/rate-limit)；工具：目录发现
  - models_added: qwen-audio-3.1-realtime-flash
- **changed** [ali-bailian/bailian-rerank](https://help.aliyun.com/zh/model-studio/text-rerank-api)；工具：rerank
  - doc_links_added: https://help.aliyun.com/zh/model-studio/get-api-key
- **changed** [ali-bailian/bailian-tts](https://help.aliyun.com/zh/model-studio/qwen-tts-api)；工具：text_to_speech
  - models_removed: qwen_tts.SpeechSynthesizer.call
- **changed** [ali-bailian/bailian-tts-models](https://help.aliyun.com/zh/model-studio/tts-model)；工具：clone_voice, design_voice, text_to_speech
  - models_added: Qwen-TTS, cosyvoice-voice-list, qwen-audio-3-1-tts-plus, qwen-audio-tts-voice-list, qwen-tts-voice-list
  - models_removed: Qwen, Qwen3-TTS-Flash
- **changed** [ali-bailian/bailian-upload](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)；工具：animate_portrait, edit_video, generate_video
- **changed** [ali-bailian/bailian-voice-clone](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)；工具：clone_voice, get_voice, list_voices
  - models_added: qwen-audio-3.1-realtime-flash
- **changed** [ali-bailian/bailian-voice-clone-guide](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)；工具：clone_voice
  - models_added: qwen-audio-3.1-realtime-flash
- **changed** [ali-bailian/bailian-voice-design-guide](https://help.aliyun.com/zh/model-studio/voice-design-user-guide)；工具：design_voice
  - endpoints_removed: https://{workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/customization
- **changed** [ali-bailian/bailian-wan-image](https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference)；工具：generate_image
- **changed** [ali-bailian/bailian-wan-s2v](https://help.aliyun.com/zh/model-studio/wan-s2v-api)；工具：animate_portrait, get_job
  - doc_links_added: https://help.aliyun.com/zh/model-studio/developer-reference/error-code
