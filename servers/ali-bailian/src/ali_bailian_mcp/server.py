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
    其他可用 ID：qwen-image-2.1 系列（最多 10 张参考图）、qwen-image-2.0-pro / qwen-image-2.0（文生图 + 编辑，
    n 最多 6）。qwen-image / qwen-image-max / qwen-image-plus / qwen-image-edit 系列已于 2026-10-10 下线。
    完整列表用 list_models("image")。

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
    voice: str | None = None,
    instructions: str | None = None,
    language: str | None = None,
    model: str | None = None,
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """用百炼非实时 TTS 把文字合成语音，保存为 wav（24kHz 单声道），返回文件路径。按模型名自动选择协议。
    中文系统音色、方言、SRT 字幕、超长文本也可用 doubao-speech 的 text_to_speech。

    - model（别名或完整 ID）：
      - 不传：voice 是 clone_voice/design_voice 生成的自定义音色 ID（以 {target_model}- 开头）时自动用该 target_model，
        否则用 "flash" → qwen3-tts-flash（multimodal-generation 协议，系统音色，不支持指令）。
      - "audio" → qwen-audio-3.0-tts-flash，"audio-plus" → qwen-audio-3.0-tts-plus，也可传 qwen-audio-3.1-tts-flash；
        "cosyvoice" → cosyvoice-v3.5-plus，也可传 cosyvoice-v3.5-flash / v3-plus / v3-flash / v2。
        这些走 SpeechSynthesizer 协议，支持系统音色、自定义音色（须与创建时的 target_model 一致）和 instructions。
    - text：要朗读的文字。长文本自动按句切成 250 字以内的段合成再拼接（url 交付方式下不拼接，需自己分段）。
    - voice：qwen3-tts-flash 默认 Cherry，可选 Serena、Ethan、Chelsie、Momo、Vivian、Moon、Neil、Arthur 等系统音色。
      Qwen-Audio-TTS/CosyVoice 必须指定：对应模型的系统音色（如 longanhuan_v3.6，见官方音色列表，不能跨模型混用；
      cosyvoice-v3.5 系列没有系统音色）或自定义音色 ID。
    - instructions：语气/情感/方言指令（官方字段 instruction），如「用温柔的语气，语速稍慢」「请用河南话表达」。
      不超过 100 字符（汉字按 2 计）。仅 Qwen-Audio-TTS 与 cosyvoice-v3.5/v3 系列支持；cosyvoice-v3-plus/v3-flash 的
      系统音色须用官方音色列表规定的固定指令，cosyvoice-v3-plus 的自定义音色不支持；qwen3-tts-flash 不支持。
    - language：qwen3-tts-flash 写 Chinese、English、Japanese 等；Qwen-Audio-TTS/CosyVoice 写语种代码（zh、en、ja…，
      对应 language_hints）。不传自动识别。
    - out_dir：输出目录，默认 BAILIAN_OUT_DIR 下按时间戳新建。
    - parameters：qwen3-tts-flash 合并进官方 parameters 对象；Qwen-Audio-TTS/CosyVoice 合并进官方 input 对象
      （如 rate、pitch、volume、seed、hot_fix），不能覆盖 text/voice/model，local 交付时 format 只能是 wav。

    按字符（qwen-audio-3.1-tts-flash 按 token）计费。返回 job_id、job_state、artifacts、request_id、ok、model、files、
    chunks（分了几段）、usage、error。url 交付方式下 files 是 24 小时内有效的链接。
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
    - model：只支持 qwen3-asr-flash。其日期快照（如 qwen3-asr-flash-2026-02-10）已于 2026-10-10 下线，本地直接拒绝；
      filetrans/realtime、Qwen-Audio-ASR 及 Fun-ASR 使用不同协议。
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
def clone_voice(audio: str, target_model: str = "qwen-audio-3.0-tts-flash", prefix: str = "custom",
                language: str | None = None, enable_preprocess: bool | None = None,
                max_prompt_audio_length: float | None = None) -> dict:
    """声音复刻：用 voice-enrollment（action=create_voice）从一段录音创建自定义音色，返回 voice（音色 ID）。创建免费。
    - audio：公网可访问的 http/https 音频 URL（WAV 16bit/MP3/M4A，≤10MB，推荐 10–20 秒、最长 60 秒，含至少 5 秒连续清晰朗读）。
      不接受本地文件、data URL 或 oss://：官方要求公网 URL，且未说明支持百炼临时上传地址。
    - target_model：后续合成用的模型，默认 qwen-audio-3.0-tts-flash；可选 qwen-audio-3.0-tts-plus、qwen-audio-3.1-tts-flash、
      cosyvoice-v3.5-plus/v3.5-flash/v3-plus/v3-flash/v2。音色只能用于该模型。
    - prefix：音色名前缀，1–10 位字母或数字；音色 ID 形如 {target_model}-{prefix}-{唯一标识}。
    - language：样本语种代码（zh、en…，language_hints），cosyvoice-v2 不支持。
    - enable_preprocess（降噪增强）、max_prompt_audio_length（3–30 秒）：cosyvoice-v3-plus/v2 不支持。
    音色需审核：用 get_voice 确认 status=OK 后，再 text_to_speech(voice=音色ID) 合成。响应缺少音色 ID 时不自动重建。
    每个账号最多 1000 个音色。仅北京地域完整支持，需要复刻也可用 doubao-speech 的 clone_voice。
    """
    return products.clone_voice(audio, target_model, prefix, language, enable_preprocess, max_prompt_audio_length)


@mcp.tool()
def design_voice(voice_prompt: str, preview_text: str, target_model: str = "qwen-audio-3.0-tts-flash",
                 prefix: str = "custom", language: str | None = None, sample_rate: int = 24000,
                 response_format: str = "wav", out_dir: str | None = None) -> dict:
    """声音设计：用 voice-enrollment（action=create_voice）按文字描述创建音色，返回 voice（音色 ID）并保存试听音频。创建免费。
    - voice_prompt：声音描述，仅中英文，≤500 字符，如「沉稳的中年男性，语速缓慢，音色低沉有磁性」。描述声音特质，不要求模仿真人。
    - preview_text：试听文本，15–200 字符，中英文。
    - target_model：默认 qwen-audio-3.0-tts-flash；可选 qwen-audio-3.0-tts-plus、qwen-audio-3.1-tts-flash、
      cosyvoice-v3.5-plus/v3.5-flash/v3-plus/v3-flash。音色只能用于该模型。
    - prefix：1–10 位字母或数字；音色 ID 形如 {target_model}-vd-{prefix}-{唯一标识}。
    - language：zh 或 en，须与 preview_text 语种一致。sample_rate=16000/24000/48000，response_format=wav/mp3/pcm。
    音色 ID 先于试听文件记入本地任务；试听下载失败可用 recover_job 补交付，不会重新创建。设计带随机性，可多次生成择优。
    返回 job_id、job_state、artifacts、files、voice、target_model、error。北京地域能力。
    """
    return products.design_voice(voice_prompt, preview_text, target_model, prefix, target_dir(out_dir), MODE,
                                 language, sample_rate, response_format)


@mcp.tool()
def list_voices(kind: str = "enrollment", page_index: int = 0, page_size: int = 20, prefix: str | None = None) -> dict:
    """分页查询 voice-enrollment（Qwen-Audio-TTS/CosyVoice）下的全部自定义音色，复刻和设计音色在同一列表。
    kind 旧值 clone/design/cosyvoice 仍可传，均等价于 enrollment（已下线的 Qwen 复刻/设计音色无法再用于合成）。
    page_index 从 0 起，page_size=1–100，prefix 按音色名前缀过滤。返回 voice_id、status、创建时间等官方字段。不会创建或删除音色。
    """
    return products.list_voices(kind, page_index, page_size, prefix)


@mcp.tool()
def get_voice(voice: str, kind: str = "enrollment", max_pages: int | None = None) -> dict:
    """查询自定义音色详情（voice-enrollment query_voice）：status（DEPLOYING 审核中 / OK 可用 / UNDEPLOYED 未通过）、
    target_model（合成时必须用的模型）、创建时间等。kind 旧值 clone/design/cosyvoice 等价；max_pages 仅为兼容旧调用保留，不再使用。
    """
    return products.get_voice(voice, kind)


@mcp.tool()
def edit_video(video: str, prompt: str, reference_images: list[str] | None = None,
               resolution: str = "720P", audio_setting: str = "auto", watermark: bool = False,
               seed: int | None = None, wait: int = 0, out_dir: str | None = None,
               parameters: dict | None = None) -> dict:
    """HappyHorse视频指令编辑：修改风格/元素，video为本地文件或公开URL，reference_images最多5张本地图片/URL。
    输入视频3–60秒，输出最多15秒，超15秒只取前15秒；详细文件限制见官方接口。
    resolution=720P/1080P；audio_setting=origin保留原音轨、auto由模型决定。
    parameters合并进官方parameters对象。异步计费任务，wait=0默认只提交，最多90秒；之后用get_job查进度，返回task_id/job_id。
    """
    return products.edit_video(video, prompt, reference_images or [], resolution, audio_setting,
                               watermark, seed, target_dir(out_dir), wait, MODE, parameters)


@mcp.tool()
def animate_portrait(image: str, audio: str, resolution: str = "480P", wait: int = 0,
                     out_dir: str | None = None, parameters: dict | None = None) -> dict:
    """wan2.2-s2v数字人对口型：图片+人声驱动人物口型、表情、动作。输入本地文件或公开URL。
    图片jpg/png/webp等，音频wav/mp3，音频须小于15MB且小于20秒；resolution=480P/720P。
    本地素材上传百炼临时存储。parameters合并进官方parameters对象。按输出秒数计费；wait=0默认只提交，最多90秒，之后用get_job查进度。
    返回task_id/job_id。北京地域能力。
    """
    return products.animate_portrait(image, audio, resolution, target_dir(out_dir), wait, MODE, parameters)


@mcp.tool()
def embed(model: str = "text-embedding-v4", texts: list[str] | None = None, contents: list[dict] | None = None,
          dimensions: int | None = None, parameters: dict | None = None) -> dict:
    """百炼文本/多模态向量化。texts为文本列表；contents用[{"text":"猫"},{"image":"/absolute/cat.png"}]等官方结构。方舟 Doubao 向量模型用 volcengine-ark 的 embed。
    必须且只能选一项。多模态请显式指定model=qwen3-vl-embedding等；图片支持本地路径，视频需公开URL。
    dimensions设置维度；parameters透传模型支持的参数，如enable_fusion。返回向量、usage；include_response=true可取完整response。
    按输入计费，不自动建索引或知识库。
    """
    return products.embed(model, texts, contents, dimensions, parameters)


@mcp.tool()
def rerank(query: str, documents: list[str], model: str = "qwen3.7-text-rerank",
           top_n: int | None = None, return_documents: bool = False) -> dict:
    """对候选文档按与query的相关性排序，返回原索引和relevance_score；top_n控制数量，return_documents返回原文。
    所有模型（含qwen3-rerank）统一走原生text-rerank接口。
    分数用于本次请求内比较。按输入计费，模型及地域权限以服务端为准。
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
    """修复交付或续做（正常查进度用 get_job）：视频查原task_id；图片/设计音色试听只补下载、不重建音色；TTS跳过已合成分段并继续尚未提交的分段（这些分段仍会计费）。
    状态未知的同步请求不自动重试。校验完整文件后跳过；wait=0视频查一次，最多90秒。临时结果过期可能无法恢复。
    """
    if not 0 <= wait <= 90:
        return {"ok": False, "error": "wait范围0–90秒"}
    return products.recover(job_id, wait)


@mcp.tool()
def list_capabilities() -> dict:
    """列出百炼MCP工具和官方来源，不联网，不代表账号权限；各工具已于2026-10-13用北京地域账号做过小样本云端验证。"""
    return {"ok": True, "account_verified": False, "validation": "cloud_sampled", "validated_on": "2026-10-13",
            "tools": {"image": ["generate_image"], "language": ["chat", "list_models"],
                      "speech": ["text_to_speech", "speech_to_text"],
                      "voice": ["clone_voice", "design_voice", "list_voices", "get_voice"],
                      "video": ["generate_video", "edit_video", "animate_portrait"],
                      "retrieval": ["embed", "rerank"], "jobs": ["list_jobs", "get_job", "recover_job"]},
            "docs": products.DOCS,
            "limits": ["clone_voice/design_voice走voice-enrollment，默认target_model为qwen-audio-3.0-tts-flash；复刻只接受公网http(s)音频URL",
                       "TTS支持非实时qwen3-tts-flash（multimodal-generation）及Qwen-Audio-TTS/CosyVoice（SpeechSynthesizer，支持instruction）；实时/WebSocket模型尚未接入",
                       "Qwen-Audio-TTS/CosyVoice与voice-enrollment官方仅北京地域完整支持；本地按250字分段，官方未写单次文本上限",
                       "speech_to_text只放行qwen3-asr-flash，已下线日期快照本地拒绝", "恢复锁使用POSIX flock，面向macOS/Linux",
                       "云端验证只覆盖北京地域小样本；其他地域与服务开通状态以账号为准"]}


def main():
    mcp.run()
