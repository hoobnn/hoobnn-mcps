# Doubao Speech 官方接口与模型核实

核实日期：2026-10-10。范围：`servers/doubao-speech` 28 个显式 MCP 工具 + 共享 `get_tool_help`，总计 29 个；26 个涉及远程调用，另外 3 个只读本地目录、示例和工具说明。逐路核实 `speech_http_request` 的 3 个 product、`legacy_speech_request` 的 11 个 operation、ASR 2 个 mode、WS TTS 2 个 mode、词表 13 个 Action，以及控制面 25 个默认 Action/Version。没有调用付费生成、识别、训练、下单或管理接口。

## 结论与修正

固定 endpoint、三类鉴权、默认资源 ID 和控制面 25 个默认版本，均有本轮实时读取的火山官方正文支持。发现并修正四处具体问题：

1. **实时 3.0 输入编码**：官方枚举为 `pcm` / `speech_opus`，原实现接受并透传 `opus`。现在接受 `speech_opus`，旧 `opus` 参数规范化为官方值，保留调用兼容。
2. **音频生成**：官方支持 `pcm`，便捷工具遗漏该格式；采样率必须按格式选择，原验证只有宽泛数值范围。现在补充 PCM，`wav/pcm` 支持 8000、16000、24000、32000、40000、44100、48000；`mp3` 不支持 40000；`ogg_opus` 仅 48000。工具默认 `mp3` 是本地产品选择，官方默认 `wav`，不等于请求错误。
3. **同传 protobuf 版本漂移**：当前官方 `protos.tar.gz` 的 `ReqParams` 有 `extra=80`；`TranslateResponse` 有 `speaker_id=9`、`detected_language=10`、`language_confidence=11`，本地旧 Python demo bindings 缺这些字段。使用官方 proto 和 protoc 6.31.0 重新生成 AST binding；另外三份依赖 descriptor 与当前 bundle 一致。source_segments 保留服务实际返回的语种、置信度与 speaker_id；同步删除能力目录中“官方 protobuf 尚未声明”的过时说明。
4. **异步长文本查询**：官方 `data.task_status` 为 1=running、2=success、3=failure。原实现只看顶层请求成功码，可能将查询到的失败任务报为成功。现在提供明确 status，任务失败返回 `ok=false`，不重新提交。

新增回归测试覆盖上述官方契约，含独立手工编码 protobuf wire fixture。豆包语音全部 **125 项离线测试通过**。这证明本地实现与已取得文档/协议样本相符，不证明账号开通、生产可用、实际模型效果或每个音色授权。

## 本轮实际获取方式

普通文档网页在 HTTP 抓取及 web.open 中是 JavaScript 空壳；追加 `.md` 和 `https://docs.volcengine.com/llms.txt` 同样返回 HTTP 200 HTML，不能算正文获取成功。

从官方公开前端 `main.3613eab6.js` 读取其真实 API 路由后，实测：

- 索引：`GET https://docs.volcengine.com/api/doc/getDocList?LibraryCode=DoubaoVoice`。返回 DocumentID、DocumentCode、父级关系、标题，覆盖当前/历史产品及管理文档。
- 正文：`GET https://docs.volcengine.com/api/doc/getDocDetail?LibraryCode=DoubaoVoice&DocumentCode=audio-generation-http`。无需账号/API Key，返回 `Result.MDContent`、`ContentType`、`UpdatedTime`、`CanonicalURL` 等。
- `Content` 可能是 JSON 编辑器数据；**必须优先 `MDContent`**，不能把编辑器 JSON 或 HTTP 200 HTML 当成 Markdown。
- 本轮成功取得 **73 篇非空 MDContent**，包含 JSON 编辑器类和旧 Markdown 类文档；完整来源及 1 个文档目录源在 `doubao-speech-sources.json`，正文更新时间、字符数与 SHA256 在 `doubao-speech-evidence.json`。这属于官网当前使用的公开读取 API，未发现公开稳定性 SLA，因此脚本应失败报告而非默默采用空内容。
- 一个目录节点 `Consolerelatedinterfaces` 在 detail API 无正文；通过官方索引找到其子 Action 文档逐个核实，没有把目录空壳列为成功正文来源。
- MDContent 覆盖该文档转换正文，但不包含需另取的 SDK zip、proto 包、图片内容以及所有动态代码 tab；协议附件应独立核实。本轮实际下载并检查同传 proto 包，未执行官方 demo。

## 全部工具映射

下表 endpoint 主机默认 `openspeech.bytedance.com`；HTTP 为 POST，特别标注的历史查询为 GET。资源列省略资源 ID 时表示该官方接口使用 API Key 和请求体选择，不擅自加 TTS/ASR 资源。

| MCP 工具 | endpoint / 模式 | 鉴权、模型或资源 | 官方正文 / 核实结论 |
|---|---|---|---|
| `text_to_speech` | `/api/v3/tts/unidirectional` | API Key；`seed-tts-2.0` / `seed-icl-2.0`；1.0 兼容资源见历史协议 | [HTTP](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh)、[二进制/Chunked细节](https://docs.volcengine.com/docs/DoubaoVoice/HTTPChunkedSSEUnidirectionalStreaming-V3?lang=zh)。已确认；本地按字符分段是交付策略，非官方硬限制 |
| `speech_to_text` | `/api/v3/auc/bigmodel/recognize/flash` | API Key；`volc.bigasr.auc_turbo`；`request.model_name=bigmodel` | [极速版](https://docs.volcengine.com/docs/DoubaoVoice/recording-file-recognition-lite-http?lang=zh)。已确认；wav/mp3/ogg/spx/amr/aac/m4a 明确列出 |
| `generate_audio` | `/api/v3/tts/create` | API Key；body.model=`seed-audio-1.0` | [音频生成](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh)。已确认；3000字符、最多3条音频参考、1张图片、最长120秒、PCM与各格式采样率已核实 |
| `submit_long_text_speech` | `/api/v3/tts/submit` | API Key；`seed-tts-2.0` / `seed-icl-2.0` | [提交](https://docs.volcengine.com/docs/DoubaoVoice/Tasksubmission?lang=zh)。已确认；100000字符、unique_id 20–64字符 |
| `query_long_text_speech` | `/api/v3/tts/query` | API Key；提交时资源、task_id | [查询](https://docs.volcengine.com/docs/DoubaoVoice/Resultquery?lang=zh)。已确认；task_status失败语义已修正 |
| `clone_voice` | `/api/v3/tts/voice_clone` | API Key；speaker_id；自定义槽使用 `custom_speaker_id` | [注册](https://docs.volcengine.com/docs/DoubaoVoice/tone-training-http?lang=zh)。已确认；10MB、PCM仅24k单声道；注册是付费训练，本轮未调用 |
| `query_voice` | `/api/v3/tts/get_voice` | API Key；speaker_id/custom_speaker_id | [查询](https://docs.volcengine.com/docs/DoubaoVoice/tone-query-http?lang=zh)。已确认；status=0/1/2/3/4 是音色状态，HTTP查询成功不等于训练成功 |
| `upgrade_voice` | `/api/v3/tts/upgrade_voice` | API Key；speaker_id/custom_speaker_id | [升级](https://docs.volcengine.com/docs/DoubaoVoice/tone-upgrade-http?lang=zh)。已确认；不假定已有音色权限 |
| `design_voice` | `/api/v3/tts/voice_design` | API Key；speaker_id；prompt | [设计](https://docs.volcengine.com/docs/DoubaoVoice/SoundDesignAPI?lang=zh)。已确认；试听text≤300、text_prompt≤200、图片≤10MB |
| `submit_transcription` | standard `/api/v3/auc/bigmodel/submit`；idle `/api/v3/auc/bigmodel/idle/submit` | API Key；standard=`volc.seedasr.auc`，兼容1.0=`volc.bigasr.auc`；idle=`volc.bigasr.auc_idle` | [标准提交](https://docs.volcengine.com/docs/DoubaoVoice/task-submission-http-1?lang=zh)、[闲时提交](https://docs.volcengine.com/docs/DoubaoVoice/task-submission-http?lang=zh)。两路均已确认；URL输入、bigmodel、同一任务UUID |
| `query_transcription` | standard `/api/v3/auc/bigmodel/query`；idle `/api/v3/auc/bigmodel/idle/query` | API Key；原任务UUID和原资源 | [标准查询](https://docs.volcengine.com/docs/DoubaoVoice/result-query-http-1?lang=zh)、[闲时查询](https://docs.volcengine.com/docs/DoubaoVoice/result-query-http?lang=zh)。两路均已确认；待处理/排队状态保留 |
| `translate_text` | `/api/v3/machine_translation/matx_translate` | API Key；`volc.speech.mt`；Seed-X产品线 | [机器翻译](https://docs.volcengine.com/docs/DoubaoVoice/MachineTranslationLargeModel-APIAccessDocumentation?lang=zh)。已确认；text_list≤16，单条≤1024 Tokens，corpus术语透传；本地不猜token精确计数 |
| `submit_minutes` | `/api/v3/auc/lark/submit` | API Key；`volc.lark.minutes` | [妙记](https://docs.volcengine.com/docs/DoubaoVoice/DoubaoVoiceMinutes-APIAccessDocumentation?lang=zh)。已确认；Input.Offline/Params、AllActivate计费选择 |
| `query_minutes` | `/api/v3/auc/lark/query` | API Key；`volc.lark.minutes`，TaskID | [妙记](https://docs.volcengine.com/docs/DoubaoVoice/DoubaoVoiceMinutes-APIAccessDocumentation?lang=zh)。已确认；任务状态独立于请求成功 |
| `manage_word_table` | 热词API Key proxy `/api/proxy/invoke?Action=...`；或OpenAPI AK/SK | 热词version=2022-08-30；替换词version=2023-10-30；region=cn-north-1 | [热词](https://docs.volcengine.com/docs/DoubaoVoice/HotWordManagementAPIv10?lang=zh)、[替换词](https://docs.volcengine.com/docs/DoubaoVoice/ReplacementWordAPIv11?lang=zh)。13个Action逐项在正文确认；替换词未假定支持API Key proxy |
| `speech_console` | `https://open.volcengineapi.com/?Action=...&Version=...` | IAM AK/SK、HMAC-SHA256、service=`speech_saas_prod`；默认region=cn-beijing | 默认25个Action逐文档确认，见后表；旧监控版本及ListApplications用cn-north-1/GET |
| `websocket_text_to_speech` | WSS `/api/v3/tts/bidirection` 或 `/api/v3/tts/unidirectional/stream` | API Key + TTS/ICL resource | [双向](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-text-to-speech-websocket?lang=zh)、[单向](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-websocket?lang=zh)。两路已确认；具体二进制框架依据同endpoint的历史V3协议 |
| `generate_podcast` | WSS `/api/v3/sami/podcasttts` | API Key；`volc.service_type.10050` | [播客](https://docs.volcengine.com/docs/DoubaoVoice/PodcastAPI-websocket-v3protocol?lang=zh)。已确认；action=0/3/4，轮次和失败信息保留 |
| `streaming_speech_to_text` | realtime WSS `/api/v3/sauc/bigmodel_async`；sentence `/api/v3/sauc/bigmodel_nostream` | API Key；2.0小时版=`volc.seedasr.sauc.duration`；可显式选择concurrent或1.0资源 | [实时识别](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)、[一句话](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)。两路已确认；本地只封装PCM/WAV，官方还支持更多格式 |
| `interpret_audio` | WSS `/api/v4/ast/v2/translate` | API Key；`volc.service_type.10053`；官方protobuf | [同传](https://docs.volcengine.com/docs/DoubaoVoice/SimultaneousInterpretation20APIAccessDocumentation?lang=zh)。已确认；源16k/16bit/mono；目标pcm16k/pcm24k float32/ogg_opus48k；proto漂移已修复 |
| `open_realtime_session` | WSS `/api/v3/duplex/realtime/dialogue`，`session.create` | API Key；session.model=`1.2.6.1`，Seeduplex 3.0 | [实时3.0](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)。已确认；JSON协议，与旧二进制实时语音不同 |
| `send_realtime_event` | 同一持久socket；append/commit/cancel/update/context/tool事件 | 本地session_id映射原socket | [实时3.0](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)。已确认；麦克风静音须mute/unmute，不能仅停止送包 |
| `receive_realtime_events` | 同一socket；JSON事件/音频delta/response.done | 同一会话 | [实时3.0](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)。已确认；音频输出pcm=float32或pcm_s16le=int16，均24k；Function Calling按call_id回传 |
| `close_realtime_session` | `session.close` → `session.closed` | 同一会话 | [实时3.0](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)。已确认；传输断开不当成官方ack |
| `speech_http_request` | product=tts/asr_flash/audio，分别对应上表3个HTTP路径 | 与对应产品一致 | **三个枚举分支都已核实**；完整请求透传不等于自动支持未知endpoint或每个账号/模型 |
| `legacy_speech_request` | operation白名单11条，见后表 | 旧AppID/Access Token，Bearer分号语法 | **11个operation都已核实**；不是V3 API Key鉴权 |
| `get_speech_usage_examples` | 本地usage.GUIDES | 无鉴权/无网络 | 示例是官方材料的本地归纳与改写，不是已经产生的云端作品 |
| `list_speech_capabilities` | 本地能力目录 | 无鉴权/无网络 | 静态目录不是账号权限发现；模型/音色实际来源见后节 |

## 模型、资源与结束协议

- TTS/ICL：新版同步与长文本默认2.0资源；模型版本是独立的 `req_params.model`（复刻场景默认 `seed-tts-2.0-standard`；旧V3详细文档还列 `seed-tts-2.0-expressive`）。`S_`等音色命名判断是便利启发式，不足以替代[音色表](https://docs.volcengine.com/docs/DoubaoVoice/Tonelist-1?lang=zh)或 `ListSpeakers(ResourceIDs=...)`。自定义/非典型ID应明确传resource_id。
- HTTP TTS：最新精简正文说code=0成功；同endpoint的[详细Chunked协议](https://docs.volcengine.com/docs/DoubaoVoice/HTTPChunkedSSEUnidirectionalStreaming-V3?lang=zh)明确音频过程包code=0、结束包code=20000000。保留完成标记验证，依据详细wire契约，而非本地样例自行假设。
- WS TTS：旧V3明确二进制header、带event/session_id，ConnectionStarted=50、SessionStarted=150、TTSResponse=352、SessionFinished=152、ConnectionFinished=52。双向生命周期为1→50、100→150、200文本、102结束session、152确认、2→52；单向入口一次发完整请求。新精简文档以EventType字符串描述语义，不足以单独证明wire已切换为JSON；实际同endpoint的详细V3协议仍需保留来源。
- ASR：固定request.model_name=`bigmodel`不表示模型1.0/2.0，真正版本/计费由X-Api-Resource-Id区分。标准2.0=`volc.seedasr.auc`，极速=`volc.bigasr.auc_turbo`，闲时=`volc.bigasr.auc_idle`；流式2.0=`volc.seedasr.sauc.duration`/`concurrent`，旧1.0为`volc.bigasr.sauc.*`。负序号音频包表示上行结束，下行最后包flag/负sequence之后才算完成。
- 播客：固定资源10050，事件100开始→150、360/361/362轮次、363终局meta、154usage、152session结束，再2→52。收到轮次失败或disconnect时保存partial，不将部分音频等同完整成功。
- 同传：AST的model不是请求中可随意更换的LLM ID，而是专属资源10053。100→150、200携PCM、102→152；服务器失败立即取消sender。官方 source_audio.format 字段为 wav；Python demo 按原始文件字节分块直接发送。正文 TaskRequest 与使用步骤明确要求 16kHz/16bit/单声道 wav/pcm，本地按 PCM 路径剥离 WAV 容器符合其中 PCM 描述；未做实际账号验证，不能声称与 demo 字节交付完全一致。protobuf source精确字段编号优先于旧demo生成文件。
- 实时：Seeduplex 3.0明确model=1.2.6.1；输入pcm/speech_opus16k，输出pcm/pcm_s16le/ogg_opus24k。JSON type为官方契约；不能复用旧端到端V2二进制协议。`response.done`含一轮usage；`session.closed`是关闭ack。
- Seed Audio：当前[接口](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh)仍只列 `seed-audio-1.0`。官网已有[1.5营销合作计划](https://docs.volcengine.com/docs/DoubaoVoice/audio1-5marketingplan?lang=zh)，但它不提供API model ID或账号开放契约，**无法据此核实1.5可调用**，本次不擅自改默认模型。

## 历史白名单逐路核实

旧接口鉴权为 `Authorization: Bearer; <Access Token>`（包含分号），AppID在query、app对象或flat body中的位置按官方旧产品不同；cluster由账号开通服务决定。没有把Access Token当作API Key。老TTS仅返回一次完整base64音频，老ASR/subtitle采用提交/查询；pending与task_status单独解读。

| operation | method + endpoint | 官方来源 |
|---|---|---|
| subtitle_submit | POST `/api/v1/vc/submit`，query.appid | [字幕](https://docs.volcengine.com/docs/DoubaoVoice/Audiovideosubtitlegeneration?lang=zh) |
| subtitle_query | GET `/api/v1/vc/query`，query.appid/id | 同上 |
| alignment_submit | POST `/api/v1/vc/ata/submit`，query.appid/caption_type，body.url/audio_text | [打轴](https://docs.volcengine.com/docs/DoubaoVoice/Automaticsubtitletyping?lang=zh) |
| alignment_query | GET `/api/v1/vc/ata/query` | 同上 |
| tts | POST `/api/v1/tts`，body.app.appid/token/cluster | [小模型](https://docs.volcengine.com/docs/DoubaoVoice/HTTPinterfaceone-timecomposition-non-streaming?lang=zh)、[大模型V1](https://docs.volcengine.com/docs/DoubaoVoice/HTTPone-timecompositenon-streaminginterface-V1notrecommended?lang=zh) |
| tts_async_submit | POST `/api/v1/tts_async/submit` | [旧长文本](https://docs.volcengine.com/docs/DoubaoVoice/APIinterfacedocumentation?lang=zh) |
| tts_async_query | GET `/api/v1/tts_async/query`，query.appid/task_id | 同上 |
| tts_emotion_submit | POST `/api/v1/tts_async_with_emotion/submit` | 同上 |
| tts_emotion_query | GET `/api/v1/tts_async_with_emotion/query` | 同上 |
| asr_submit | POST `/api/v1/auc/submit`，body.app | [旧录音识别](https://docs.volcengine.com/docs/DoubaoVoice/AudioFileRecognitionStandardEdition?lang=zh) |
| asr_query | POST `/api/v1/auc/query`，body.appid/token/cluster/id | 同上 |

## 控制面与词表

OpenAPI主机、签名service、region、Action和Version逐项依据正文请求示例核实。默认25个Action使用POST、cn-beijing、speech_saas_prod，下面每行链接均是本轮成功取得的官方正文。

| Action | Version | 官方正文 |
|---|---|---|
| `ActivateService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ActivateService-ActivateService?lang=zh) |
| `AliasResourcePack` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/AliasResourcePack-Updatesoundresourcealiases?lang=zh) |
| `BatchListMegaTTSTrainStatus` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/BatchListMegaTTSTrainStatus-PageQuerySpeakerIDStatus?lang=zh) |
| `CreateAPIKey` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/CreateAPIKey-CreateAPIKey?lang=zh) |
| `DeleteAPIKey` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/DeleteAPIKey-DeleteAPIKey?lang=zh) |
| `FormalizeResourcePacks` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/FormalizeResourcePacks-Conversioneffectpackage?lang=zh) |
| `ListAPIKeys` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ListAPIKeys-PullAPIKeyList?lang=zh) |
| `ListBigModelTTSTimbres` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ListBigModelTTSTimbres-LargeModelSoundList?lang=zh) |
| `ListMegaTTSByOrderID` | `2023-11-07` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ListMegaTTSByOrderID-QuerypurchasedsoundsbyorderID?lang=zh) |
| `ListMegaTTSTrainStatus` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ListMegaTTSTrainStatus-QuerySpeakerIDstatusinformation?lang=zh) |
| `ListSpeakers` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ListSpeakers-LargeModelSoundListNewInterface?lang=zh) |
| `ListTagsForResources` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ListTagsForResources-Queryalllabelsattachedtoaresource?lang=zh) |
| `OrderAccessResourcePacks` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/OrderAccessResourcePacks-SoundOrder?lang=zh) |
| `OrderResourcePacks` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/OrderResourcePacks-Buyeffectspackage?lang=zh) |
| `PauseService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/PauseService-SuspendService?lang=zh) |
| `QuotaMonitoring` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/QuotaMonitoring-Quotaqueryinterface?lang=zh) |
| `RenewAccessResourcePacks` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/RenewAccessResourcePacks-ToneRenewal?lang=zh) |
| `ResourcePacksStatus` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ResourcePacksStatus-effectpackagestatusinformation?lang=zh) |
| `ResumeService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ResumeService-Re-enabletheservice?lang=zh) |
| `ServiceStatus` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/ServiceStatus-ServiceStatus?lang=zh) |
| `TagResources` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/TagResources-Attachtagstoresources?lang=zh) |
| `TerminateService` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/TerminateService-DeactivateService?lang=zh) |
| `UntagResources` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/UntagResources-Removetagsfromresources?lang=zh) |
| `UpdateAPIKey` | `2025-05-20` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/UpdateAPIKey-UpdateAPIKey?lang=zh) |
| `UsageMonitoring` | `2025-05-21` | [文档](https://docs.volcengine.com/docs/DoubaoVoice/UsageMonitoring-CallQueryInterface?lang=zh) |

旧监控接口 `QuotaMonitoring` / `UsageMonitoring` 的 `2021-08-30` 版本走GET、cn-north-1，[旧并发](https://docs.volcengine.com/docs/DoubaoVoice/QPSConcurrentQueryInterfaceDescription?lang=zh)、[旧用量](https://docs.volcengine.com/docs/DoubaoVoice/Callvolumequeryinterfacedescription?lang=zh)均有示例。`ListApplications` 的 `2021-11-22` 版本GET/cn-north-1依据词表正文；它不在默认版本表中，调用时明确version。任意自行输入的Action/Version不可能仅凭“支持透传”就视为已核实。

热词Action：ListBoostingTableLimits、CreateBoostingTable、CheckBoostingTableName、UpdateBoostingTable、DeleteBoostingTable、ListBoostingTable、GetBoostingTable。替换词Action：CreateCorrectTable、CheckCorrectTableName、UpdateCorrectTable、DeleteCorrectTable、ListCorrectTable、GetCorrectTable。两组13个名字均在各自正文找到；Create/Update为multipart File，UTF-8文件小于8MB。API-Key热词代理路由官方明确支持；替换词仅确认AK/SK路线。术语词表正文只提供控制台创建，并通过corpus.glossary_list/table_id/table_name使用，不将其推断为未公开CRUD API。

## 官方材料之间的差异与无法核实项

1. [模型总表](https://docs.volcengine.com/docs/DoubaoVoice/model-list?lang=zh)对Seed Audio 1.0只概括中英文、若干采样率；更具体的当前音频API正文列更多语种以及40000/44100等采样率。具体请求验证按接口正文，不能用总表粗略行覆盖接口枚举；语种和声音表现仍需真实样本验收。
2. 同传本轮从正文附带的[protos.tar.gz](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/6493ecf3887246e3a99968961f716499~tplv-goo7wpa0wc-image.image)看到新字段，但同页[Python demo zip](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f5a5a20f3ae441a49195c2b192c2cf93~tplv-goo7wpa0wc-image.image)的ast_service_pb2仍无detected_language。已按原始proto重新生成，没有依据文档文字手写猜测字段编号。
3. 新版部分ASR字段表将result写成list，旧详细协议样例展示object；本次保留旧样例支持的既有object解析与高级raw完整响应，不把表格标题单独解释为线上schema迁移。未进行账号请求，无法断定全部响应场景形态。
4. 声音复刻自定义speaker命名规则、可用训练次数和后付费转正依赖控制台/具体账号。便捷工具的音色启发式不能证明音色资源授权；预付费槽、后付费custom_speaker_id、跨语种能力不通过真实付费调用猜测。
5. 没有查询IAM账户、API Key、音色库、QPS配额，也没有发真实data/admin请求。因此确认的是**官方公开契约与本地路径映射**，不是所有模型、所有资源、所有账号或历史接口当前权限均已通过线上验证。
6. 公开正文API没有正式稳定性保证；MDContent空、目录节点、错误JSON、HTML空壳必须作为获取失败处理；不存在“任意网页追加.md就能取最新文档”的通用规则。

本轮下载的网页/正文和proto均为官方公开资源；临时分析文件在结束时清理。持久证据保存为正文指纹与来源列表，不把完整官方文章或凭据复制进仓库。
