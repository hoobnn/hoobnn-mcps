"""stdio MCP server：百炼图像、语言、语音、定制音色、视频、检索与任务恢复。

环境变量：DASHSCOPE_API_KEY（必需）、BAILIAN_OUT_DIR（默认 ~/Downloads/ali-bailian）、
BAILIAN_RESOURCE_MODE（local 下载到本地，url 只返回链接；默认 local）、DASHSCOPE_BASE_URL（可选）。
"""

import os
import time
import uuid
from pathlib import Path

from .mcp_runtime import ReliableMCPServer

from . import dashscope, media, products

OUT_ROOT = Path(os.environ.get("BAILIAN_OUT_DIR", "~/Downloads/ali-bailian")).expanduser()
MODE = os.environ.get("BAILIAN_RESOURCE_MODE", "local").strip().lower()
if MODE not in ("local", "url"):
    raise SystemExit(f"BAILIAN_RESOURCE_MODE 只能是 local 或 url，当前是 {MODE!r}")

mcp = ReliableMCPServer("ali-bailian", groups={
    "image": {"generate_image"}, "language": {"chat"},
    "speech": {"text_to_speech", "speech_to_text", "clone_voice", "design_voice", "list_voices", "get_voice"},
    "video": {"generate_video", "edit_video", "animate_portrait"},
    "embedding": {"embed", "rerank"}, "jobs": {"list_jobs", "get_job", "recover_job"},
    "help": {"list_models", "list_capabilities", "get_tool_help"}})


def target_dir(out_dir):
    root = Path(out_dir).expanduser() if out_dir else OUT_ROOT
    return root / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])


@mcp.tool()
def generate_image(
    prompt: str,
    model: str = "qwen",
    images: list[str] | None = None,
    size: str | None = None,
    n: int | None = None,
    group: int | None = None,
    negative_prompt: str | None = None,
    prompt_extend: bool | None = None,
    seed: int | None = None,
    thinking: bool | None = None,
    watermark: bool = False,
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """用阿里云百炼的生图模型生成或编辑图片，结果保存到本地，返回文件路径。

    选模型（别名或完整模型 ID 都行）：
    - "qwen"（默认）→ qwen-image-3.0-pro：千问旗舰，文字渲染最强（中英文海报、标题、招牌），文生图和图片编辑
      二合一。总像素 512*512–2560*2560，默认 2048*2048，n 最多 6。
    - "wan" → wan2.7-image-pro：万相旗舰，0–9 张参考图（多图融合、换装、风格迁移），支持 1K / 2K / 4K 档位、
      group 组图（1–12 张连贯的图）和 thinking。wan2.7-image 是更便宜的标准版（最高 2K）。
    - "z" → z-image-turbo：最快最便宜，写实人像和产品图好，只支持文生图，每次 1 张。
    其他可用 ID：qwen-image-2.0-pro / qwen-image-2.0（文生图 + 编辑，n 最多 6）、qwen-image-max（写实）/
    qwen-image-plus-2026-01-09（艺术风格），这两个只支持文生图和固定尺寸 1664*928、1328*1328、928*1664 等；
    qwen-image-edit-max / qwen-image-edit-plus（专用图片编辑）。完整列表用 list_models("image")。

    参数：
    - prompt：千问和万相都能理解长提示词（万相最多 5000 字）。要画的文字用引号括起来。多图时用「图1」「图2」指明
      各取什么。
    - images：参考图或待编辑的图，本地绝对路径或 URL，单张不超过 10MB。
    - size：写 宽*高（如 1024*1536，也接受 1024x1536）；wan 还可以只写 1K / 2K / 4K 档位（4K 仅文生图），
      宽高比写进 prompt。不写用模型默认值。
    - n：一次生成几张相互独立的图；group：只有 wan 支持，生成 N 张内容连贯的组图（如分镜、系列海报），会覆盖 n。
    - negative_prompt：不想出现的内容。prompt_extend：是否让模型改写扩充提示词，不传用模型默认值（千问默认开），
      要严格按原文出图时设 false。seed：固定随机种子。thinking：wan 的推理增强，默认开。
    - watermark：是否加「AI 生成」水印，默认不加。
    - out_dir：输出目录，默认 BAILIAN_OUT_DIR 下按时间戳新建。交付方式为 url 时忽略。
    - parameters：官方请求 parameters 对象里本工具没单独列出的字段，深度合并，同名时以这里为准。

    按成功生成的张数计费，n 和 group 越大越贵，批量生成前先和用户确认数量。同步调用，单张通常十几秒到一分钟。
    返回 job_id、job_state、artifacts、request_id、ok、model、files、text（模型改写后的提示词，有的话）、usage、error。交付方式由 BAILIAN_RESOURCE_MODE
    决定：local 时 files 是本地路径，url 时 files 是 24 小时内有效的图片链接，需要长期保存要及时下载。
    """
    opts = dict(prompt=prompt, model=model, images=images or [], size=size, n=n, group=group,
                negative_prompt=negative_prompt, prompt_extend=prompt_extend, seed=seed, thinking=thinking,
                watermark=watermark, parameters=parameters)
    return dashscope.generate_image(opts, target_dir(out_dir), mode=MODE)


@mcp.tool()
def chat(
    prompt: str,
    model: str = "max",
    system: str | None = None,
    history: list[dict] | None = None,
    images: list[str] | None = None,
    thinking: bool | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
    web_search: bool = False,
    parameters: dict | None = None,
) -> dict:
    """调用阿里云百炼上的语言模型，返回回答文本。适合要第二意见、换个模型交叉验证、或用特定模型处理任务。

    选模型（别名或完整模型 ID 都行）：
    - "max"（默认）→ qwen3.8-max：千问旗舰，能看图。
    - "plus" → qwen3.7-plus：性价比均衡。
    - "flash" → qwen3.8-flash：最快最便宜，适合简单任务和批量处理。
    百炼也托管第三方模型，直接写 ID：deepseek-v4-pro、kimi-k3、glm-5.3、MiniMax/MiniMax-M3 等。模型更新很快，
    不确定 ID 时先用 list_models 查。

    参数：
    - prompt：本轮用户消息。system：系统提示词。
    - history：之前的多轮对话，OpenAI 格式的列表，如 [{"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}]，不含本轮 prompt。工具本身不保存会话，多轮要自己带上历史。
    - images：随 prompt 一起发的图片，本地绝对路径或 URL，需要模型支持看图（qwen3.8-max、qwen3.6-plus、
      qwen3-vl-plus 等）。
    - thinking：是否开启深度思考，不传用模型默认值（千问新模型默认开）。简单问题设 false 更快更省。
      thinking_budget：思考的最大 token 数。
    - max_tokens：回答的最大 token 数。temperature：采样温度。
    - json_mode：要求输出合法 JSON，prompt 里要写明 JSON 结构，且最好同时设 thinking=false。
    - web_search：让模型联网搜索后回答（千问系列支持）。
    - parameters：官方请求体里本工具没单独列出的字段（OpenAI 兼容接口顶层），深度合并，不能覆盖 model/messages/stream。

    返回 ok、model、content（回答）、reasoning（思考过程，有的话）、finish_reason（length 表示被 max_tokens 截断）、
    usage、error。
    """
    opts = dict(prompt=prompt, model=model, system=system, history=history, images=images or [],
                thinking=thinking, thinking_budget=thinking_budget, max_tokens=max_tokens,
                temperature=temperature, json_mode=json_mode, web_search=web_search,
                parameters=parameters)
    return dashscope.chat(opts)


@mcp.tool()
def text_to_speech(
    text: str,
    voice: str = "Cherry",
    instructions: str | None = None,
    language: str | None = None,
    model: str | None = None,
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """用千问 TTS 把文字合成语音，保存为 wav（24kHz 单声道），返回文件路径。中文音色、方言、SRT 字幕、超长文本优先用 doubao-speech 的 text_to_speech。

    - text：要朗读的文字。长文本会自动按句切段合成再拼接成一个文件（url 交付方式下不拼接，需自己分段，
      每段 250 字以内）。
    - voice：系统音色，默认 Cherry。女声：Cherry 芊悦（阳光亲切）、Serena 苏瑶（温柔）、Chelsie 千雪（二次元）、
      Momo 茉兔（撒娇搞怪）、Vivian 十三（可爱小暴躁）、Mia 乖小妹（乖巧）、Bellona 燕铮莺（洪亮清晰）、
      Bunny 萌小姬（萝莉）、Elias 墨讲师（讲课）、Nini 邻家妹妹（软糯）、Seren 小婉（助眠）、Stella 少女阿月（甜）；
      男声：Ethan 晨煦（标准普通话、阳光）、Moon 月白（率性帅气）、Eldric Sage 沧明子（沉稳老者）、
      Mochi 沙小弥（小大人）、Vincent 田叔（烟嗓）、Neil 阿闻（新闻主持）、Arthur 徐大爷（讲故事）、Pip 顽屁小孩。
    - instructions：用自然语言控制语速、情绪、语气、角色，如「语速稍快，语气兴奋」「像深夜电台主持人一样低沉
      缓慢」。传了会自动改用 qwen3-tts-instruct-flash。
    - language：Chinese、English、Japanese、Korean、French、German、Russian、Italian、Spanish、Portuguese，
      不传自动识别。中英混读不用设。
    - model：不传时自动选 flash/instruct。自定义音色必须传创建返回的target_model（非实时VC/VD），不能用默认模型。
    - out_dir：输出目录，默认 BAILIAN_OUT_DIR 下按时间戳新建。
    - parameters：官方请求 parameters 对象里本工具没单独列出的字段，深度合并，同名时以这里为准。

    按字符计费。返回 job_id、job_state、artifacts、request_id、ok、model、files、chunks（分了几段）、usage、error。url 交付方式下 files 是 24 小时内有效的链接。
    """
    opts = dict(text=text, voice=voice, instructions=instructions, language=language, model=model,
                parameters=parameters)
    return media.text_to_speech(opts, target_dir(out_dir), mode=MODE)


@mcp.tool()
def speech_to_text(
    audio: str,
    context: str | None = None,
    language: str | None = None,
    itn: bool = False,
    model: str = "qwen3-asr-flash",
    parameters: dict | None = None,
) -> dict:
    """用千问 ASR 把一段音频转成文字，同时返回识别出的语种和情绪。超过 10MB / 5 分钟、需要说话人分离或热词时用 doubao-speech 的 speech_to_text。

    - audio：本地绝对路径或 URL。本地文件支持 mp3、wav、m4a、aac、flac、ogg、opus、amr、webm，不超过 10MB，
      时长不超过 5 分钟。更长的音频先切段再分别识别。
    - context：背景文字，提高专有名词、人名、术语的识别准确率，如「这是一段关于 Kubernetes 和 Istio 的技术分享」。
    - language：已知语种时指定（zh、en、ja、ko、yue 等），能提高准确率；不传自动识别。
    - itn：是否把口语数字转成阿拉伯数字（如「二零二六年」→「2026年」），默认不转。
    - model：默认 qwen3-asr-flash，也可写其非实时快照 ID；filetrans/realtime及Fun-ASR使用不同协议。
    - parameters：官方请求体里本工具没单独列出的字段（OpenAI 兼容接口顶层），深度合并，不能覆盖 model/messages/stream。

    按音频时长计费。返回 ok、model、text、language、emotion、usage、error。
    """
    return media.speech_to_text(dict(audio=audio, context=context, language=language, itn=itn, model=model,
                                     parameters=parameters))


@mcp.tool()
def generate_video(
    prompt: str = "",
    model: str = "wan",
    first_frame: str | None = None,
    last_frame: str | None = None,
    reference_images: list[str] | None = None,
    reference_videos: list[str] | None = None,
    reference_audios: list[str] | None = None,
    file: str | None = None,
    link: str | None = None,
    resolution: str = "1080P",
    ratio: str = "adaptive",
    duration: int | None = None,
    audio: bool = True,
    prompt_extend: bool | None = None,
    seed: int | None = None,
    watermark: bool = False,
    wait: int = 0,
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """用万相 3.0 生成视频（mp4，30fps，默认带同步音频）。异步任务：提交后最多等 wait 秒，没完成就返回 task_id，
    之后用 get_job 查进度，完成时自动下载。生成通常要一到几分钟，分辨率越高、时长越长越慢。

    模型：model="wan"（默认）→ wan3.0-video；"wan-fast" → wan3.0-video-prime，能力相同、速度明显更快。

    按传入的素材决定玩法（素材都可以是本地绝对路径或 URL，本地文件会自动上传到百炼临时存储）：
    - 文生视频：只给 prompt。
    - 首帧生视频：first_frame；首尾帧生视频：first_frame + last_frame。
    - 多主体参考：reference_images（最多 10 张）、reference_videos（最多 5 段）、reference_audios（最多 5 段，
      如指定配音或音乐），prompt 里用「图1」「视频1」「音频1」按各自顺序指代。
    - 视频续写：只传 1 段 reference_videos，prompt 写「将视频1向后延长……」，输入加输出总长不超过 30 秒。
    - file/link：参考文档或公开网页，二选一，要求prompt_extend=true；不能与首尾帧混用。
    prompt 最多 2 万字，可以写分镜、镜头运动、台词和音效。

    参数：
    - resolution：1080P（默认）/ 720P / 480P。ratio：adaptive（默认，跟随素材或由模型决定）、16:9、9:16、
      1:1、4:3、3:4、21:9。
    - duration：2–30 秒，-1 让模型自己决定；不传用模型默认值。
    - audio：是否生成音轨（人声、音效、配乐），默认生成。
    - prompt_extend：是否让模型改写扩充提示词，默认开。seed：随机种子。watermark：是否加水印，默认不加。
    - wait：默认 0，只提交不等；1–90 秒可轮询。生成与交付还受 MCP_TOOL_TIMEOUT_SEC 总预算限制。
    - out_dir：输出目录，默认 BAILIAN_OUT_DIR 下按时间戳新建。
    - parameters：官方请求 parameters 对象里本工具没单独列出的字段，深度合并，同名时以这里为准。

    按输出视频的秒数计费，分辨率越高越贵，生成前先和用户确认时长和分辨率。
    返回 job_id、job_state、artifacts、request_id、ok、model、task_id、status（PENDING / RUNNING / SUCCEEDED / FAILED）、files、usage、error。
    """
    opts = dict(prompt=prompt, model=model, first_frame=first_frame, last_frame=last_frame,
                reference_images=reference_images or [], reference_videos=reference_videos or [],
                reference_audios=reference_audios or [], file=file, link=link, resolution=resolution, ratio=ratio,
                duration=duration, audio=audio, prompt_extend=prompt_extend, seed=seed, watermark=watermark,
                parameters=parameters)
    return media.generate_video(opts, target_dir(out_dir), wait, mode=MODE)


@mcp.tool()
def list_models(keyword: str | None = None, max_pages: int = 20) -> dict:
    """查询百炼官方模型目录（包括视频等全模态），按名称过滤，最多max_pages页。
    返回模型ID及能力、快照、上下文、价格等官方字段；complete标记是否取完分页。
    目录存在不等于当前API Key拥有调用权限，account_verified固定false；权限需单独核实。
    """
    return dashscope.list_models(keyword, max_pages)


@mcp.tool()
def clone_voice(audio: str, target_model: str = "qwen3-tts-vc-2026-01-22", preferred_name: str = "custom_voice",
                text: str | None = None, language: str | None = None) -> dict:
    """用Qwen声音复刻创建固定音色。audio为本地wav/mp3/m4a（10MB以内）、公开URL或data URL，建议清晰单人录音。复刻的音色只能用于百炼 TTS；用于豆包合成请用 doubao-speech 的 clone_voice。
    target_model默认非实时VC模型；preferred_name为1–16位字母/数字/下划线；text可提供准确录音文本。
    返回voice和target_model，合成时必须把两者传给text_to_speech，不能沿用默认flash模型。
    会产生音色创建费用，不自动重试创建；模型支持与录音时长由服务端校验。新增功能尚未完成云端验证。
    """
    return products.clone_voice(audio, target_model, preferred_name, text, language)


@mcp.tool()
def design_voice(voice_prompt: str, preview_text: str, target_model: str = "qwen3-tts-vd-2026-01-26",
                 preferred_name: str = "custom_voice", out_dir: str | None = None) -> dict:
    """通过中文/英文描述创建Qwen音色并保存试听wav。voice_prompt最多2048字符，preview_text为试听台词，最多1024字符。设计的音色只能用于百炼 TTS。
    返回voice、target_model和试听files/job_id；后续text_to_speech必须指定这两个字段。
    会产生音色创建费用；试听保存失败用recover_job补交付，不能再次调用design_voice代替恢复。尚未完成云端验证。
    """
    return products.design_voice(voice_prompt, preview_text, target_model, preferred_name, target_dir(out_dir), MODE)


@mcp.tool()
def list_voices(kind: str = "clone", page_index: int = 0, page_size: int = 20, prefix: str | None = None) -> dict:
    """分页查询自定义音色。kind=clone（Qwen复刻）/design（Qwen设计）/cosyvoice（CosyVoice与Qwen-Audio共享音色接口）。
    page_index从0起，page_size=1–100；prefix仅cosyvoice支持。保留目标模型等官方字段。不会创建或删除音色。
    """
    return products.list_voices(kind, page_index, page_size, prefix)


@mcp.tool()
def get_voice(voice: str, kind: str = "clone", max_pages: int = 10) -> dict:
    """查找音色。Qwen没有单独的详情接口，clone/design从分页列表查找，最多max_pages页；cosyvoice走query_voice。
    达到页数上限会明确返回尚不能判断，不能视为音色不存在。
    """
    return products.get_voice(voice, kind, max_pages)


@mcp.tool()
def edit_video(video: str, prompt: str, reference_images: list[str] | None = None,
               resolution: str = "720P", audio_setting: str = "auto", watermark: bool = False,
               seed: int | None = None, wait: int = 0, out_dir: str | None = None,
               parameters: dict | None = None) -> dict:
    """HappyHorse视频指令编辑：修改风格/元素，video为本地文件或公开URL，reference_images最多5张本地图片/URL。
    输入视频3–60秒，输出最多15秒，超15秒只取前15秒；详细文件限制见官方接口。
    resolution=720P/1080P；audio_setting=origin保留原音轨、auto由模型决定。
    parameters合并进官方parameters对象。异步计费任务，wait=0默认只提交，最多90秒；之后用get_job查进度，返回task_id/job_id。尚未完成云端验证。
    """
    return products.edit_video(video, prompt, reference_images or [], resolution, audio_setting,
                               watermark, seed, target_dir(out_dir), wait, MODE, parameters)


@mcp.tool()
def animate_portrait(image: str, audio: str, resolution: str = "480P", wait: int = 0,
                     out_dir: str | None = None, parameters: dict | None = None) -> dict:
    """wan2.2-s2v数字人对口型：图片+人声驱动人物口型、表情、动作。输入本地文件或公开URL。
    图片jpg/png/webp等，音频wav/mp3，音频须小于15MB且小于20秒；resolution=480P/720P。
    本地素材上传百炼临时存储。parameters合并进官方parameters对象。按输出秒数计费；wait=0默认只提交，最多90秒，之后用get_job查进度。
    返回task_id/job_id。北京地域能力，尚未完成云端验证。
    """
    return products.animate_portrait(image, audio, resolution, target_dir(out_dir), wait, MODE, parameters)


@mcp.tool()
def embed(model: str = "text-embedding-v4", texts: list[str] | None = None, contents: list[dict] | None = None,
          dimensions: int | None = None, parameters: dict | None = None) -> dict:
    """百炼文本/多模态向量化。texts为文本列表；contents用[{"text":"猫"},{"image":"/absolute/cat.png"}]等官方结构。方舟 Doubao 向量模型用 volcengine-ark 的 embed。
    必须且只能选一项。多模态请显式指定model=qwen3-vl-embedding等；图片支持本地路径，视频需公开URL。
    dimensions设置维度；parameters透传模型支持的参数，如enable_fusion。返回向量、usage；include_response=true可取完整response。
    按输入计费，不自动建索引或知识库。尚未完成云端验证。
    """
    return products.embed(model, texts, contents, dimensions, parameters)


@mcp.tool()
def rerank(query: str, documents: list[str], model: str = "qwen3.7-text-rerank",
           top_n: int | None = None, return_documents: bool = False) -> dict:
    """对候选文档按与query的相关性排序，返回原索引和relevance_score；top_n控制数量，return_documents返回原文。
    qwen3.7-text-rerank走原生接口，qwen3-rerank走compatible-api/v1/reranks，两者请求体不同。
    分数用于本次请求内比较。按输入计费，模型及地域权限以服务端为准；尚未完成云端验证。
    """
    return products.rerank(query, documents, model, top_n, return_documents)


@mcp.tool()
def list_jobs(limit: int = 20, kind: str | None = None) -> dict:
    """列出最近本地任务，不联网。工具超时未拿到job_id时可按时间/model/summary找回记录；limit=1–100，kind可筛选image/video/tts等。"""
    return products.STORE.list(limit, kind)


@mcp.tool()
def get_job(job_id: str | None = None, task_id: str | None = None, wait: int = 0) -> dict:
    """查任务进度和结果，job_id 或 task_id 二选一（都给时须属于同一任务）。
    视频类任务（generate_video/edit_video/animate_portrait）还在生成时查询百炼一次（wait 1–90 秒可轮询），
    完成即下载到原输出目录；已结束的任务只读本地记录。只给 task_id 且本地没有记录时，新建本地记录再查询。
    不会重新提交生成。返回 job_state、completed、files、usage；ok=false 表示查询或交付失败。
    """
    return products.get_job(job_id, task_id, wait, target_dir(None), MODE)


@mcp.tool()
def recover_job(job_id: str, wait: int = 0) -> dict:
    """修复交付或续做（正常查进度用 get_job）：视频查原task_id；图片/试听只补下载；TTS跳过已合成分段并继续尚未提交的分段（这些分段仍会计费）。
    状态未知的同步请求不自动重试。校验完整文件后跳过；wait=0视频查一次，最多90秒。临时结果过期可能无法恢复。
    """
    if not 0 <= wait <= 90:
        return {"ok": False, "error": "wait范围0–90秒"}
    return products.recover(job_id, wait)


@mcp.tool()
def list_capabilities() -> dict:
    """列出百炼MCP工具和官方来源，不联网，不代表账号权限；新增能力未完成云端验证。"""
    return {"ok": True, "account_verified": False, "validation": "offline_only",
            "tools": {"image": ["generate_image"], "language": ["chat", "list_models"],
                      "speech": ["text_to_speech", "speech_to_text"],
                      "voice": ["clone_voice", "design_voice", "list_voices", "get_voice"],
                      "video": ["generate_video", "edit_video", "animate_portrait"],
                      "retrieval": ["embed", "rerank"], "jobs": ["list_jobs", "get_job", "recover_job"]},
            "docs": products.DOCS,
            "limits": ["自定义音色创建和合成必须使用相同target_model", "Qwen音色详情从列表查找",
                       "TTS仅支持非实时Qwen3系列，实时模型尚未接入", "恢复锁使用POSIX flock，面向macOS/Linux",
                       "地域、服务开通及实际输出规格尚需后续测试"]}


def main():
    mcp.run()
