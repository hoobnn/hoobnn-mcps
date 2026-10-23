# 官方文档变更检查

成功 36 / 36，变更 19，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [ali-bailian/bailian-chat](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)；工具：chat
  - models_added: DeepSeek-V3.2, DeepSeek-V4, DeepSeek-V4-Pro, DeepSeek-V4.1-Flash, MiniMax-M3.1-Flash, deepseek-ocr, deepseek-r1, deepseek-r1-0528, deepseek-r1-distill-qwen, deepseek-v3, deepseek-v3-0324, deepseek-v3.1-terminus, deepseek-v3.2, deepseek-v3.2-speciale, deepseek-v3.2-think, deepseek-v4-flash-0731, deepseek-v4-pro, deepseek-v4-pro-0813, deepseek-v4.1-flash, deepseek-v4.1-flash-1017, xiaomi/mimo-v2.5-pro, xiaomi/mimo-v2.6-pro-ultraspeed
- **changed** [ali-bailian/bailian-chat-models](https://help.aliyun.com/zh/model-studio/text-generation-model)；工具：chat
  - models_added: deepseek-r1-distill-llama-70b, deepseek-r1-distill-qwen-1.5b, deepseek-v4-pro
  - models_removed: qwen-1.5b
- **added** [ali-bailian/bailian-cosyvoice-access](https://help.aliyun.com/zh/model-studio/cosyvoice-model-access)；工具：clone_voice, design_voice, text_to_speech
  - models_added: CosyVoice, cosyvoice-android-sdk, cosyvoice-client-events, cosyvoice-harmonyos-sdk, cosyvoice-ios-sdk, cosyvoice-java-sdk, cosyvoice-python-sdk, cosyvoice-server-events, cosyvoice-websocket-api
- **added** [ali-bailian/bailian-minimax-chat](https://help.aliyun.com/zh/model-studio/minimax-api-by-minimax)；工具：chat
  - models_added: MiniMax-M2.5, MiniMax-M2.7, MiniMax-M3, MiniMax-M3.1-Flash, minimax-m3, minimax-m31-differences, qwen-function-calling, qwen-structured-output
  - endpoints_added: https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1, https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions
- **changed** [ali-bailian/bailian-model-directory](https://help.aliyun.com/zh/model-studio/models)；工具：目录发现
  - models_added: MiniMax-M3.1-Flash, deepseek-v4-pro-0813, deepseek-v4.1-flash, minimax-m3-1-flash
  - models_removed: MiniMax-M3, music-h3, music-v1
- **changed** [ali-bailian/bailian-model-lifecycle](https://help.aliyun.com/zh/model-studio/newly-released-models)；工具：目录发现
  - models_added: DeepSeek-OCR, DeepSeek-R1, DeepSeek-R1-0528, DeepSeek-R1-Distill-Qwen-1.5B, DeepSeek-R1-Distill-Qwen-14B, DeepSeek-R1-Distill-Qwen-32B, DeepSeek-R1-Distill-Qwen-7B, DeepSeek-V3, DeepSeek-V3-0324, DeepSeek-V3-1226, DeepSeek-V3.1, DeepSeek-V3.1-Terminus, DeepSeek-V3.2, DeepSeek-V4, DeepSeek-V4-Pro, DeepSeek-V4.1-Flash, DeepSeek-V4.1-Flash-1017, MiniMax-M3.1-Flash, deepseek-ocr, deepseek-r1, deepseek-r1-0528, deepseek-r1-distill-qwen-1.5b, deepseek-r1-distill-qwen-14b, deepseek-r1-distill-qwen-32b, deepseek-r1-distill-qwen-7b, deepseek-v3, deepseek-v3-0324, deepseek-v3.1, deepseek-v3.1-terminus, deepseek-v3.2, deepseek-v3.2-exp, deepseek-v3.2-think, deepseek-v4-flash, deepseek-v4-flash-0731, deepseek-v4-flash-0731-us, deepseek-v4-flash-us, deepseek-v4-pro, deepseek-v4-pro-0813, deepseek-v4-pro-us, deepseek-v4.1-flash, deepseek-v4.1-flash-1017, xiaomi/mimo-v2.5-pro, xiaomi/mimo-v2.6-pro-ultraspeed
  - models_removed: Qwen-1.5B, Qwen-14B, Qwen-32B, Qwen-7B, qwen-1.5b, qwen-14b, qwen-32b, qwen-7b
- **changed** [ali-bailian/bailian-model-pricing](https://help.aliyun.com/zh/model-studio/model-pricing)；工具：目录发现
  - models_added: DeepSeek-, DeepSeek-V4-Flash-0731, MiniMax-M3.1-Flash, deepseek-api, deepseek-ocr, deepseek-r1, deepseek-r1-0528, deepseek-r1-distill-llama-70b, deepseek-r1-distill-qwen-1.5b, deepseek-v3, deepseek-v3-0324, deepseek-v3.1-terminus, deepseek-v3.2, deepseek-v3.2-think, deepseek-v4-flash-0731, deepseek-v4-pro, deepseek-v4-pro-0813, deepseek-v4.1-flash, deepseek-v4.1-flash-1017, qwen-audio-3.1-tts-plus, xiaomi/mimo-v2.5-pro, xiaomi/mimo-v2.6-pro-ultraspeed
  - models_removed: qwen-1.5b, qwen3.8-max-prime
- **added** [ali-bailian/bailian-qwen-audio-tts-access](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-model-access)；工具：clone_voice, design_voice, text_to_speech
  - models_added: Qwen-Audio-TTS, qwen-audio-tts-android-sdk, qwen-audio-tts-client-events, qwen-audio-tts-harmonyos-sdk, qwen-audio-tts-ios-sdk, qwen-audio-tts-java-sdk, qwen-audio-tts-python-sdk, qwen-audio-tts-server-events, qwen-audio-tts-websocket-api
- **changed** [ali-bailian/bailian-qwen-image-legacy](https://help.aliyun.com/zh/model-studio/qwen-image-api)；工具：generate_image
  - models_removed: qwen-image-3.0, qwen-image-3.0-pro, qwen-image-generation-and-editing-api-reference
  - endpoints_removed: https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis, https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/tasks/{task_id}, https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis, https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/tasks/{task_id}
  - doc_links_removed: https://help.aliyun.com/zh/oss/user-guide/what-is-oss)）
- **changed** [ali-bailian/bailian-rate-limit](https://help.aliyun.com/zh/model-studio/rate-limit)；工具：目录发现
  - models_added: DeepSeek-, MiniMax-M3.1-Flash, Qwen-Audio-ASR, Qwen-Audio-ASR-Filetrans, Qwen-Audio-ASR-Message, Qwen-Audio-ASR-Streaming, Qwen3-ASR, Qwen3-ASR-Realtime, Qwen3-TTS, Qwen3-TTS-Realtime, deepseek-ocr, deepseek-r1, deepseek-r1-0528, deepseek-r1-distill-llama-70b, deepseek-r1-distill-qwen-1.5b, deepseek-ratelimit-title, deepseek-v3, deepseek-v3-0324, deepseek-v3.1-terminus, deepseek-v3.2, deepseek-v3.2-think, deepseek-v4-flash-0731, deepseek-v4-pro, deepseek-v4-pro-0813, deepseek-v4.1-flash, deepseek-v4.1-flash-1017, qwen-audio-3.1-tts-plus, xiaomi/mimo-v2.5-pro, xiaomi/mimo-v2.6-pro-ultraspeed
  - models_removed: Qwen-ASR, Qwen-ASR-Realtime, Qwen-Audio-3.1-ASR-Flash-Message, Qwen-Audio-3.x-ASR-Flash, Qwen-Audio-3.x-ASR-Flash-Filetrans, Qwen-Audio-3.x-ASR-Flash-Streaming, Qwen-TTS, Qwen-TTS-Realtime, qwen-1.5b
- **added** [ali-bailian/bailian-regions](https://help.aliyun.com/zh/model-studio/regions)；工具：目录发现
  - models_added: qwen-api-reference
  - endpoints_added: https://dashscope.aliyuncs.com/api/v1, https://dashscope.aliyuncs.com/compatible-mode/v1, https://llm-xxx.cn-beijing.maas.aliyuncs.com/api/v1, https://llm-xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
- **changed** [ali-bailian/bailian-tts-cosyvoice](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)；工具：text_to_speech
- **changed** [ali-bailian/bailian-tts-guide](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)；工具：text_to_speech
  - models_added: cosyvoice-tts-http-api, minimax-synchronous-speech-synthesis-api, qwen-audio-3.1-tts-plus, qwen-audio-tts-http-api
  - models_removed: Qwen-TTS, Qwen3-TTS-Flash, cosyvoice-api, minimax-speech-synthesis, qwen-audio-tts-api
  - endpoints_added: https://YOUR_WORKSPACE_ID.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer
  - endpoints_removed: https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation, https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer
  - doc_links_removed: https://help.aliyun.com/zh/model-studio/get-api-key
- **changed** [ali-bailian/bailian-tts-models](https://help.aliyun.com/zh/model-studio/tts-model)；工具：clone_voice, design_voice, text_to_speech
  - models_added: qwen-audio-3.1-tts-plus
- **changed** [ali-bailian/bailian-tts-qwen-audio](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)；工具：text_to_speech
  - models_added: qwen-audio-3.1-tts-plus
  - endpoints_added: https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer
- **changed** [ali-bailian/bailian-voice-clone](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)；工具：clone_voice, get_voice, list_voices
  - models_added: Qwen-Audio-Realtime, qwen-audio-3.0-realtime-flash, qwen-audio-3.0-realtime-plus, qwen-audio-3.1-realtime-plus, qwen-audio-3.1-tts-plus
- **changed** [ali-bailian/bailian-voice-clone-guide](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)；工具：clone_voice
  - models_added: cosyvoice-model-access, minimax-speech-synthesis, qwen-audio-3.1-tts-plus, qwen-audio-realtime-model-access, qwen-audio-tts-model-access
  - models_removed: qwen-audio-3.1-realtime-plus-myvoice-xxxxxx
  - endpoints_added: https://{workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1
  - endpoints_removed: https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/audio/tts/customization, https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/customization
  - doc_links_removed: https://help.aliyun.com/zh/model-studio/fun-audiochat-realtime#fc60h311, https://help.aliyun.com/zh/model-studio/get-api-key
- **changed** [ali-bailian/bailian-voice-design-guide](https://help.aliyun.com/zh/model-studio/voice-design-user-guide)；工具：design_voice
  - models_added: qwen-audio-3.1-tts-plus
- **changed** [ali-bailian/bailian-wan-video](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference)；工具：generate_video, get_job, recover_job
