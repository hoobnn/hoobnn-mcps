# 火山方舟 MCP 官方接口审计

核实时间：2026-10-10（Asia/Shanghai）。范围为 `servers/volcengine-ark` 全部业务工具、模型别名和恢复调用；未向生成、对话、向量接口发送真实请求。结果区分「官方正文确认」「差异已修正」「账号/实际运行无法确认」。官方目录、接口文档能证明公开契约，不能证明本账号模型权限、线上输出或计费结果。

## 完整工具与接口映射

所有远程接口默认使用 `https://ark.cn-beijing.volces.com/api/v3`，请求头为 `Authorization: Bearer <ARK_API_KEY>`、JSON 请求的 `Content-Type: application/json`。北京 Base URL 和 API Key 认证均由[官方鉴权文档](https://docs.volcengine.com/docs/ark/base-url-and-authentication?lang=zh)确认。本项目可用 `ARK_BASE_URL` 覆盖地址；未实现 Access Key 签名路径。

| MCP 工具 | 实现入口 / 官方 HTTP 接口 | 核实结果与官方正文 |
|---|---|---|
| `generate_image` | `ark.generate` → `POST /images/generations` | 确认。prompt/model/image/size/output_format/background/layer_decomposition/sequential_image_generation/tools/optimize_prompt_options/watermark 与[图片 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)对应。local 用 b64_json，url 模式用 url；响应 data、usage、图层字段已对应。 |
| `generate_video` | `products.submit_video` → `POST /contents/generations/tasks` | 确认。模型、content 的 text/image_url/video_url/audio_url 与 role、resolution/ratio/duration/generate_audio/watermark 对应[创建任务 API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)。parameters 用于其余官方顶层字段，最终请求体预检，不能覆盖模型或素材。 |
| `get_job`（视频任务） | `products.get_job/poll_video` → `GET /contents/generations/tasks/{id}` | 确认。[查询 API](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh)包含 queued/running/cancelled/succeeded/failed；任务过期还可能为 expired。成功读取 content.video_url、content.last_frame_url、usage、duration、ratio、resolution、output_format。 |
| `chat` | `products.chat` → `POST /chat/completions` | 确认。[Chat API](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)使用 messages、text/image_url/video_url，thinking、max_tokens、temperature、response_format；响应 choices.message.content/reasoning_content/finish_reason/usage。工具不执行模型返回的函数调用。 |
| `chat(web_search=true)` 或 `previous_response_id` 非空 | `products.chat` → `POST /responses` | 确认。[Responses API](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh)使用 input_text/input_image/input_video，图片/视频地址为字符串；assistant 历史文本为 output_text。转换不修改调用者 history。max_tokens映射max_output_tokens，json_mode映射text.format.json_object。 |
| `chat(web_search=true)` | 同上；tools=`[{"type":"web_search"}]` | 确认。当前采用[基础联网搜索](https://docs.volcengine.com/docs/ark/web-search?lang=zh)，模型自主选择是否搜索；输出保留 url_citation 等 sources。tools 自定义配置被当前透传保护拦截，未开放扩展搜索工具或搜索过滤器；专用 Search API 尚未接入。 |
| `embed(texts=...)` | `products.embed` → `POST /embeddings` | 确认。[文本向量 API](https://docs.volcengine.com/docs/ark/TextVectorizationAPI?lang=zh)使用 model/input，响应 data 为结果列表，usage 为token。dimensions不是该页明确列出的参数，见下方限制。 |
| `embed(contents=...)` | `products.embed` → `POST /embeddings/multimodal` | 确认。[多模态向量 API](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh)支持type=text/image_url/video_url、图片/视频对象中的url、dimensions、instructions、multi_embedding、encoding_format；响应data为对象，按原结构返回，未假设总为列表。 |
| `recover_job` | `products.recover` | 图片读取已保存响应并补交付，不发生成请求；视频优先补下载，需要刷新URL时调用上面的GET查询原task_id。[图片链接期限](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)及[视频任务/链接期限](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh)决定恢复可用性。 |
| `list_jobs` / `get_job` | 本地 `jobs.Store` | 本地实现，无官方远程接口；get_job.ok表示读取成功，job_state表示任务状态。 |
| `list_capabilities` | 静态模型/能力目录 | 本地实现，无权限探测，不代表账号已经开通。模型和参数来自下列官方目录。 |
| `get_tool_help` | MCP运行时注册的完整工具说明 | 本地实现，无远程接口。 |

## 模型别名与公开目录

以下 ID 已逐项在[官方模型目录](https://docs.volcengine.com/docs/ark/model-list?lang=zh)及相应教程确认；目录正文更新时间为 `2026-10-09T09:49:07Z`。

| 工具 / 别名 | 固定模型 ID | 状态 |
|---|---|---|
| 图片 `pro`（保留默认） | `doubao-seedream-5-0-pro-260628` | 官方仍列出。 |
| 图片 `lite` | `doubao-seedream-5-0-260128` | 仍列出；目录标注相关lite旧版本即将下线，需跟踪公告，不能据此自动替换默认。 |
| 图片 `flash`（本次补齐） | `doubao-seedream-5-0-flash-260915` | 最新目录及[pro/flash教程](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)确认；无需修改现有默认。 |
| 视频 `seedance`（保留默认） | `doubao-seedance-2-5-260628` | [2.5教程](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)确认。 |
| 视频 `seedance-2` | `doubao-seedance-2-0-260128` | [2.0系列教程](https://docs.volcengine.com/docs/ark/seedance-2-0?lang=zh)确认。 |
| 视频 `seedance-fast` | `doubao-seedance-2-0-fast-260128` | 同上。 |
| 视频 `seedance-mini` | `doubao-seedance-2-0-mini-260615` | 同上。 |
| 对话 `pro`（保留默认） | `doubao-seed-2-1-pro-260628` | 仍列在推荐模型；当前目录另有260915版本，但未悄悄升级默认。 |
| 对话完整 ID | 例如 `doubao-seed-2-1-pro-260915` | 公开目录确认1024k上下文；需调用者显式选择。 |
| 多模态向量完整 ID | `doubao-embedding-vision-251215` | 当前目录确认128k输入、2048维及1024降维。工具无隐式默认，显式指定。 |
| 文本向量完整 ID | 例如 `doubao-embedding-text-240515` | 文本API仍有此示例，但当前推荐目录未列该旧ID；账号实际可用性无法确认，不增加默认别名。 |

[模型下线公告](https://docs.volcengine.com/docs/ark/model-deprecation-notice?lang=zh)是独立来源，不能将目录未出现或旧教程示例当成服务仍可购买/开通的证明。

## 关键参数核实与必要修正

### 图片

依据[图片 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)和[图片教程](https://docs.volcengine.com/docs/ark/seedream-4-0-5-0?lang=zh)：

- pro/flash最多10张参考；lite最多14张。组图与搜索仅lite支持；总参考数+最大生成数不能超过15。group是最大数量，模型不保证正好生成该数量。
- pro/flash档位1K/1.5K/2K；lite档位2K/3K/4K。显式宽高的总像素限制分别为921600–4624220及3686400–16777216，宽高比1/16–16；图层拆分仅支持档位或auto，不能填写像素尺寸。本次增加预检。
- 图层拆分/透明背景可用于pro与flash；fast提示词优化仅pro支持。之前未识别flash能力，本次补齐别名及能力校验。
- 拆层只允许单张png/jpeg，透明编辑只允许单张含透明通道的输入；代码核对输入数量，但尚未解码检查远程图片格式、像素或透明通道，服务端仍最终校验。普通本地参考格式和30MB限制已对应。
- 输出默认jpeg；透明背景默认png；拆层中底图遵循output_format，各层总是png。原来缺少响应output_format时默认命名png，本次改为保存请求格式并在旧内联缓存中按文件签名识别，避免把JPEG命名为PNG。
- 图片URL有效24小时；拆层任一层失败官方定义为整体失败。PNG/JPEG格式和大小预检不证明生成质量、透明细节或图层还原质量。

### 视频

依据[创建任务](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)和[2.5教程](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)：

- 原校验统一允许2–30秒，与官方不同：2.5是4–30秒，2.0系列4–15秒，均支持-1；本次按已知模型预检。1.0或不可识别Endpoint不套用2.x限制。
- 首帧/首尾帧与全模态参考不可混用；2.5参考图片/视频/音频最多30/10/10；2.0最多9/3/3且不能只输入音频。本次修正预检。
- 2.5支持480p/720p/1080p，2.0标准版支持额外4k，fast/mini仅480p/720p。本次核对resolution，保留4k支持。
- 2.5首帧/首尾帧ratio仅adaptive。新增官方omni_reference_task_type支持auto/reference/edit/extend；明确edit要求reference_video、adaptive、duration省略或-1，extend要求reference_video、adaptive。本工具经parameters透传并校验，未凭prompt文本猜测任务类型。
- draft目前仅2.5的480p；mov仅2.5；seed/frames文档支持范围为1.0系列。本次在已识别2.x模型中拦截不支持的值。所有预检在parameters合并后执行，避免覆盖绕过限制。
- 生成尾帧为jpeg；原保存名last-frame.png，本次修正为last-frame.jpg。视频输出格式继续取查询响应output_format。
- 视频URL有效24小时，查询任务范围为近7天，2.5视频URL下载次数最多100次。恢复不是永久存档，过期后查询不保证仍有任务/链接。
- 远程视频/音频的真实格式、时长、文件体积及参考总时长未下载探测，不宣称本地预检已覆盖；模型实际任务类型由官方判定，auto仍可能异步失败。

### 对话、搜索与向量

[Chat API](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)与[Responses API](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh)的输入类型、thinking、JSON输出字段已匹配。thinking是enabled/disabled/auto，本工具bool只覆盖前两者，auto可经parameters配置。max_tokens/max_output_tokens含义不同，Responses计入回答+思维链，Chat随模型定义。temperature通常0–2，部分旧模型固定为1；目前依赖服务端模型校验。

[搜索指南](https://docs.volcengine.com/docs/ark/web-search?lang=zh)还包含扩展搜索工具；当前MCP只选择基础web_search，不等于全部Search/Agent能力。真实搜索是否执行、次数和结果来源仍需云端响应验证。

[文本向量 API](https://docs.volcengine.com/docs/ark/TextVectorizationAPI?lang=zh)要求非空文本成员、单条UTF-8不超过100000字节，示例模型每条4096 tokens；文档建议少量文本以改善性能，未将建议强制当成batch上限。该页未列dimensions，工具当前可透传此字段，兼容性无法从官方页确认。

[多模态向量 API](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh)确认dimensions为1024/2048；视频格式mp4/avi/mov、单文件≤50MB，视觉嵌入不理解音频。multi_embedding不能为空对象，至少包含type；压缩需调用者自行解码。每种模型的input、视频抽帧和维度适用范围不同，未把这些限制误套给全部模型。

## 官方文档程序化获取：实测结果

普通页面常返回JavaScript壳，不能将HTTP200当成正文已取得。本次从官方页面加载的doccenter静态JS中确认其自身读取路径，随后匿名GET实测：

1. `https://www.volcengine.com/api/doc/getDocDetail?LibraryCode=ark&DocumentCode=image-generation-api` 返回200 JSON，`Result.MDContent` 为22968字符的官方Markdown正文；同响应`ContentType=json`、`Content`是富文本JSON，不应因此误判没有Markdown。
2. 其余接口/教程/模型等16个正文来源均有非空MDContent。字段还包括DocumentID、DocumentCode、LibraryID、Title、UpdatedTime等。视频创建正文更新时间为2026-10-08，Chat/Responses/模型目录于2026-10-09更新。
3. `https://www.volcengine.com/api/doc/getDocList?LibraryCode=ark` 返回200，Result为完整目录数组（约257KB），包含DocumentCode/DocumentID/Title/ContentType等；用于发现新增/移除文档。目录内部时间戳会产生噪声，应规范化再比较。
4. `https://www.volcengine.com/api/doc/getDocumentCode?LibraryID=82379&DocumentID=1541523` 返回`LibraryCode=ark, DocumentCode=image-generation-api`，可将历史数字URL映射到稳定slug。
5. `/llms.txt`、`/llms-full.txt`本次返回HTML壳；`/docs/ark/image-generation-api.md`也返回HTML而非Markdown，不能作为可靠纯文本地址。

登记文件：[volcengine-ark-sources.json](volcengine-ark-sources.json)。fetch_url指向上面的官方文档JSON读取接口，正文提取需优先Result.MDContent；它是官方站点自用路径，尚未查到对外稳定性SLA，不应等同正式云产品OpenAPI。没有用登录Cookie、API Key或付费接口获取资料，核实阶段未保存整篇正文；汇总更新检查在 docs/upstream/snapshots 保存已核实正文的压缩快照，以生成后续diff。

## 验证与未确认边界

本次新增 `test_official_contracts.py`，验证官方限制映射、flash能力、参数覆盖后的预检、图片格式识别、JPEG尾帧名称；与既有jobs故障测试一起执行。离线测试不证明本账号权限、线上输出规格、搜索实际调用、云端费用或媒体质量。

仍需日后在明确授权的账号上验证：旧文本嵌入模型可用性、文本接口dimensions支持、Endpoint映射后的真实模型限制、输入远程素材格式与时长、最新版模型的真实Responses/搜索组合，以及图层/透明结果是否满足交付要求。本次未发任何真实付费请求。
