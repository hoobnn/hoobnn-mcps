# 百炼与火山方舟 MCP 接入记录

日期：2026-10-09。用户授权实施规划，并明确本轮不进行测试。

## 范围与状态

| 功能 | 官方契约核对 | 实现 | 测试 |
|---|---|---|---|
| Seedance生成、任务查询、编辑/延长提示词与高级参数 | 已阅读官方文档 | 已写入seedream包 | 待用户开启测试阶段 |
| 方舟Chat / Responses、多模态、深度思考、搜索、JSON | 已阅读官方文档 | 已写入seedream包 | 同上 |
| 方舟文本/多模态向量 | 已阅读官方文档 | 已写入seedream包 | 同上 |
| 百炼Qwen复刻、设计、分页列表和音色查找 | 已阅读官方文档 | 已写入ali-bailian包 | 同上 |
| 百炼HappyHorse视频编辑、wan2.2-s2v数字人 | 已阅读官方文档 | 已写入ali-bailian包 | 同上 |
| 百炼文本/多模态向量、文本重排序 | 已阅读官方文档 | 已写入ali-bailian包 | 同上 |
| 图片、视频、百炼分段TTS、音色设计试听恢复 | 本地设计审阅 | 已写入两个包 | 同上 |
| 豆包音色、长文本TTS等 | 独立任务负责 | 本任务不修改其目录 | 独立任务负责 |

“已写入”仅代表开发产物，不表示通过测试或线上验收。未执行编译、导入、单元、集成、真实生成或音色训练；未安装升级、提交或推送。
评审阶段为当前Agent的官方契约核对和源码审阅，没有独立Agent评审。测试阶段明确延期，三个阶段不能合并标记完成。

## 关键设计决策

- 保留原MCP入口、配置和工具名；seedream包扩展为方舟入口，不新增重复账号配置。
- 每个包独立安装，标准库任务模块分别内置在两个包内，无需GitHub外的共享包。两个 `jobs.py` 维护同一实现。
- 恢复目录默认位于 `~/.local/share/<server>-mcp/jobs`，可通过 `BAILIAN_JOB_DIR` / `SEEDREAM_JOB_DIR` 设置。
- 生成请求前留档为unknown；同步超时未收到完整结果，不自动重试。异步任务拿到task_id后持久化，再查询交付。
- 图片响应留档后按产物逐项交付；Seedream内联Base64缓存到任务目录，防止本地输出失败后必须再次生成。
- 成功产物用SHA-256验证后跳过，临时文件下载完成再原子替换。部分生成失败不自动补生成。
- TTS每段生成URL和请求ID单独保存；仅接续未提交/明确被拒绝的分段，未知段需人工判断。最后合并WAV，校验段间采样参数一致。
- `ok`保留为布尔字段，但生成工具只有全交付才返回true；部分成功保留files并返回partial/error。读取工具的ok只表示读取成功。
- 产物metadata优先读取PNG头；其他媒体可选调用已安装ffprobe，返回实际规格或available=false，不用请求参数冒充实际尺寸。
- 静态 `list_capabilities` 返回not_tested/account_verified=false，不把官方存在的能力等同于当前账号可用。
- Qwen音色没有单独详情查询，get_voice使用分页列表查找；达到上限明确报告未完成查找。
- 自定义音色仅创建Qwen非实时VC/VD并接入对应TTS；不把CosyVoice/Qwen-Audio的不同合成端点混用。
- 本地视频/音频自动上传目前只在百炼实现；方舟使用公网URL/asset ID。模型细节限制继续由服务端校验。
- 不自动调用模型返回的Function Calling，不自动创建知识库，不自动购买或开通服务。

## 官方来源与接口映射

| 能力 | 路径与关键字段 | 来源 |
|---|---|---|
| 百炼音色 | `/api/v1/services/audio/tts/customization`；model=qwen-voice-enrollment/qwen-voice-design，input.action=create/list；CosyVoice=query_voice | [复刻](https://help.aliyun.com/en/model-studio/voice-clone-design-http-api)、[设计](https://help.aliyun.com/zh/model-studio/voice-design-api-references) |
| 百炼编辑 | `/api/v1/services/aigc/video-generation/video-synthesis`；happyhorse-1.0-video-edit，input.media的video/reference_image | [编辑](https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference) |
| 百炼数字人 | `/api/v1/services/aigc/image2video/video-synthesis`；input.image_url/audio_url | [数字人](https://help.aliyun.com/zh/model-studio/wan-s2v-api) |
| 百炼多模态向量 | `/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding`；input.contents | [API](https://help.aliyun.com/en/model-studio/multimodal-embedding-api-reference) |
| 百炼重排序 | 新模型原生rerank/text-rerank；qwen3-rerank使用compatible-api/v1/reranks | [API](https://help.aliyun.com/zh/model-studio/text-rerank-api) |
| 方舟视频 | `/contents/generations/tasks`及`/{id}`；content角色素材、status、content.video_url | [创建](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)、[查询](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh) |
| 方舟对话 | `/chat/completions`；messages/response_format/thinking | [API](https://docs.volcengine.com/docs/ark/chat-api?lang=zh) |
| 方舟搜索 | `/responses`；input/tools/previous_response_id；输出注解来源 | [Responses](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh)、[搜索](https://docs.volcengine.com/docs/ark/web-search?lang=zh) |
| 方舟向量 | `/embeddings`及`/embeddings/multimodal`；input | [多模态](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh)、[向量](https://docs.volcengine.com/docs/ark/vectorization?lang=zh) |

## 待开启的测试阶段

以下仅是后续验收清单，本轮没有执行，也没有新增测试文件。

1. 工具schema、模块导入、独立安装包和原有工具兼容。
2. API请求体、模型地域、Qwen音色分页、两种rerank接口及Responses多模态内容转换。
3. 图片4项中1项下载失败，重启补下载：生成API只调用一次，完整文件不重复下载。
4. 视频提交后工具超时，从list_jobs找回task_id并接续；未知提交不得自动重投。
5. TTS成功分段保留、未知段不重投、明确拒绝段可显式接续、采样参数不一致时拒绝拼接。
6. 缓存写入/下载/图层索引失败、签名URL过期、损坏文件、并发恢复、没有产物、服务端部分失败。
7. 两家真实最小媒体样本与定制音色试听；检查实际图像尺寸、视频时长/音轨及播放质量。
8. 模型列表和能力目录与当前账号权限核对；源码正确和真实交付分别记录。
