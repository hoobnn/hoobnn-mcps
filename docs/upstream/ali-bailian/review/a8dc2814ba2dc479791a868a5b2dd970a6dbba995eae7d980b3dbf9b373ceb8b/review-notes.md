# PR #14 本轮审查说明

抓取时间：2026-10-23T06:51:24.893207+00:00。官方来源36/36成功，19项相对PR原捕获基线变化，0失败。旧review目录保留；本目录是更新后的捕获，不表示已合并或云端验收。

落实的契约变更：

- 声音复刻统一使用input.audio，支持公网URL、Base64 Data URI和本地WAV/MP3/M4A；url别名与audio互斥，保留官方旧参数兼容含义，不悄悄覆盖。
- qwen-audio-3.1-tts-plus加入合成、复刻、设计及音色前缀识别。CosyVoice的100字符instruction上限不再错误套用到Qwen-Audio-TTS。
- MiniMax直供M3/M3.1按各自thinking协议处理；M3.1的adaptive-only、reasoning_split=true、n=1和五档reasoning_effort等限制在本地校验。
- 中英README明确workspace根域名、同地域API Key及各产品的HTTP/复刻/设计地域边界；AOQ/WebSocket模型接入页用于监控和区分协议，没有扩展为实时实现。
- 新增include_tool_usage及usage.x_tools可由现有透传/保留逻辑支持，已补回归。完整模型Function Calling循环不在当前chat工具能力中。

判读机器报告时：

- 补DeepSeek/Xiaomi候选提取前缀后，models_added内还包含此前漏提取的历史模型；这不代表这些模型全在本轮发布。
- Qwen旧页移除异步图像章节不影响已使用的同步协议；Wan3只补充MP4/H.264格式；表格样式与推荐位变化不作为接口停用证据。
- HappyHorse美国workspace域名变化已存在于PR原捕获；本轮保留，未虚报为新发生。

详细字段、限制、官方来源及验证边界见docs/audits/ali-bailian.md「2026-10-23上游更新落实」。本次不调用账号接口或付费模型，不合并、不发布。
