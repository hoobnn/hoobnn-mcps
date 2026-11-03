# 官方文档变更检查

成功 36 / 36，变更 4，抓取失败 0。

正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。

- **changed** [ali-bailian/bailian-asr-models](https://help.aliyun.com/zh/model-studio/asr-model)；工具：speech_to_text
- **changed** [ali-bailian/bailian-chat-models](https://help.aliyun.com/zh/model-studio/text-generation-model)；工具：chat
  - models_added: Qwen, Qwen-Character, Qwen-Deep-Research, Qwen-Doc, Qwen-Long, Qwen-MT, Qwen-OCR, Qwen3-VL, deepseek-r1-distill-llama-70b, qwen-deep-research, qwen-doc, qwen-vl-ocr, qwen3-vl-plus
  - models_removed: MiniMax-M2.5, MiniMax-M2.7, MiniMax-M3, deepseek-v4-pro, kimi-k2.5, kimi-k2.6, kimi-k2.7-code, qwen3-coder-flash-2025-07-28, qwen3.5-flash-2026-02-23, qwen3.5-plus-2026-02-15, qwen3.6-27b, qwen3.6-flash-2026-04-16, qwen3.6-plus-2026-04-02, qwen3.7-flash-2026-07-15, qwen3.7-max-2026-05-17, qwen3.7-max-2026-05-20, qwen3.7-max-2026-06-08, qwen3.7-max-preview, qwen3.7-plus-2026-05-26, qwen3.8-max-0902
- **changed** [ali-bailian/bailian-model-directory](https://help.aliyun.com/zh/model-studio/models)；工具：目录发现
- **changed** [ali-bailian/bailian-vision-models](https://help.aliyun.com/zh/model-studio/vision-model)；工具：chat
  - models_added: MiniMax-M3.1-Flash, Qwen, Qwen-Character, Qwen-Deep-Research, Qwen-Doc, Qwen-Long, Qwen-MT, Qwen3-Coder, deepseek-r1-distill-llama-70b, deepseek-r1-distill-qwen-1.5b, deepseek-v4.1-flash-1017, kimi-k3, qwen-deep-research, qwen-doc, qwen-flash, qwen-flash-character, qwen-long, qwen-max, qwen-mt-flash, qwen-mt-lite, qwen-mt-plus, qwen-plus, qwen-plus-character, qwen-plus-character-ja, qwen-structured-output, qwen3-coder-flash, qwen3.7-max
  - models_removed: Qwen-Omni, Qwen3.8, Qwen3.8-Omni-Flash, qwen-omni, qwen3-omni-flash, qwen3.5-flash-2026-02-23, qwen3.5-ocr, qwen3.5-omni-flash, qwen3.5-omni-plus, qwen3.5-plus-2026-02-15, qwen3.6-flash-2026-04-16, qwen3.6-plus-2026-04-02, qwen3.7-flash-2026-07-15, qwen3.7-max-2026-06-08, qwen3.7-plus-2026-05-26, qwen3.8-max-0902, qwen3.8-omni-flash, qwen38-offline
