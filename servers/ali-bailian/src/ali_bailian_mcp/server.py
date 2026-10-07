"""stdio MCP server：生图、对话、语音合成、语音识别、视频生成和模型列表。

环境变量：DASHSCOPE_API_KEY（必需）、BAILIAN_OUT_DIR（默认 ~/Downloads/ali-bailian）、
BAILIAN_RESOURCE_MODE（local 下载到本地，url 只返回链接；默认 local）、DASHSCOPE_BASE_URL（可选）。
"""

import os
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import dashscope, media

OUT_ROOT = Path(os.environ.get("BAILIAN_OUT_DIR", "~/Downloads/ali-bailian")).expanduser()
MODE = os.environ.get("BAILIAN_RESOURCE_MODE", "local").strip().lower()
if MODE not in ("local", "url"):
    raise SystemExit(f"BAILIAN_RESOURCE_MODE 只能是 local 或 url，当前是 {MODE!r}")

mcp = MCPServer("ali-bailian")


def target_dir(out_dir):
    return Path(out_dir).expanduser() if out_dir else OUT_ROOT / time.strftime("%Y%m%d-%H%M%S")


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

    按成功生成的张数计费，n 和 group 越大越贵，批量生成前先和用户确认数量。同步调用，单张通常十几秒到一分钟。
    返回 ok、model、files、text（模型改写后的提示词，有的话）、usage、error。交付方式由 BAILIAN_RESOURCE_MODE
    决定：local 时 files 是本地路径，url 时 files 是 24 小时内有效的图片链接，需要长期保存要及时下载。
    """
    opts = dict(prompt=prompt, model=model, images=images or [], size=size, n=n, group=group,
                negative_prompt=negative_prompt, prompt_extend=prompt_extend, seed=seed, thinking=thinking,
                watermark=watermark)
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

    返回 ok、model、content（回答）、reasoning（思考过程，有的话）、finish_reason（length 表示被 max_tokens 截断）、
    usage、error。
    """
    opts = dict(prompt=prompt, model=model, system=system, history=history, images=images or [],
                thinking=thinking, thinking_budget=thinking_budget, max_tokens=max_tokens,
                temperature=temperature, json_mode=json_mode, web_search=web_search)
    return dashscope.chat(opts)


@mcp.tool()
def text_to_speech(
    text: str,
    voice: str = "Cherry",
    instructions: str | None = None,
    language: str | None = None,
    model: str | None = None,
    out_dir: str | None = None,
) -> dict:
    """用千问 TTS 把文字合成语音，保存为 wav（24kHz 单声道），返回文件路径。

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
    - model：不传时按是否有 instructions 自动选 qwen3-tts-flash / qwen3-tts-instruct-flash。
    - out_dir：输出目录，默认 BAILIAN_OUT_DIR 下按时间戳新建。

    按字符计费。返回 ok、model、files、chunks（分了几段）、usage、error。url 交付方式下 files 是 24 小时内有效的链接。
    """
    opts = dict(text=text, voice=voice, instructions=instructions, language=language, model=model)
    return media.text_to_speech(opts, target_dir(out_dir), mode=MODE)


@mcp.tool()
def speech_to_text(
    audio: str,
    context: str | None = None,
    language: str | None = None,
    itn: bool = False,
    model: str = "qwen3-asr-flash",
) -> dict:
    """用千问 ASR 把一段音频转成文字，同时返回识别出的语种和情绪。

    - audio：本地绝对路径或 URL。本地文件支持 mp3、wav、m4a、aac、flac、ogg、opus、amr、webm，不超过 10MB，
      时长不超过 5 分钟。更长的音频先切段再分别识别。
    - context：背景文字，提高专有名词、人名、术语的识别准确率，如「这是一段关于 Kubernetes 和 Istio 的技术分享」。
    - language：已知语种时指定（zh、en、ja、ko、yue 等），能提高准确率；不传自动识别。
    - itn：是否把口语数字转成阿拉伯数字（如「二零二六年」→「2026年」），默认不转。
    - model：默认 qwen3-asr-flash，也可写 fun-asr-flash-2026-06-15 等其他 ASR 模型 ID。

    按音频时长计费。返回 ok、model、text、language、emotion、usage、error。
    """
    return media.speech_to_text(dict(audio=audio, context=context, language=language, itn=itn, model=model))


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
    resolution: str = "1080P",
    ratio: str = "adaptive",
    duration: int | None = None,
    audio: bool = True,
    prompt_extend: bool | None = None,
    seed: int | None = None,
    watermark: bool = False,
    wait: int = 90,
    out_dir: str | None = None,
) -> dict:
    """用万相 3.0 生成视频（mp4，30fps，默认带同步音频）。异步任务：提交后最多等 wait 秒，没完成就返回 task_id，
    之后用 query_video 继续等。生成通常要一到几分钟，分辨率越高、时长越长越慢。

    模型：model="wan"（默认）→ wan3.0-video；"wan-fast" → wan3.0-video-prime，能力相同、速度明显更快。

    按传入的素材决定玩法（素材都可以是本地绝对路径或 URL，本地文件会自动上传到百炼临时存储）：
    - 文生视频：只给 prompt。
    - 首帧生视频：first_frame；首尾帧生视频：first_frame + last_frame。
    - 多主体参考：reference_images（最多 10 张）、reference_videos（最多 5 段）、reference_audios（最多 5 段，
      如指定配音或音乐），prompt 里用「图1」「视频1」「音频1」按各自顺序指代。
    - 视频续写：只传 1 段 reference_videos，prompt 写「将视频1向后延长……」，输入加输出总长不超过 30 秒。
    - file：参考文档（如产品资料 pptx / pdf），让模型据此做宣传视频。
    prompt 最多 2 万字，可以写分镜、镜头运动、台词和音效。

    参数：
    - resolution：1080P（默认）/ 720P / 480P。ratio：adaptive（默认，跟随素材或由模型决定）、16:9、9:16、
      1:1、4:3、3:4、21:9。
    - duration：2–30 秒，-1 让模型自己决定；不传用模型默认值。
    - audio：是否生成音轨（人声、音效、配乐），默认生成。
    - prompt_extend：是否让模型改写扩充提示词，默认开。seed：随机种子。watermark：是否加水印，默认不加。
    - wait：本次调用最多等多少秒，默认 90；设 0 只提交不等。部分客户端的工具调用超时在 2 分钟左右，不要设太大。
    - out_dir：输出目录，默认 BAILIAN_OUT_DIR 下按时间戳新建。

    按输出视频的秒数计费，分辨率越高越贵，生成前先和用户确认时长和分辨率。
    返回 ok、model、task_id、status（PENDING / RUNNING / SUCCEEDED / FAILED）、files、usage、error。
    """
    opts = dict(prompt=prompt, model=model, first_frame=first_frame, last_frame=last_frame,
                reference_images=reference_images or [], reference_videos=reference_videos or [],
                reference_audios=reference_audios or [], file=file, resolution=resolution, ratio=ratio,
                duration=duration, audio=audio, prompt_extend=prompt_extend, seed=seed, watermark=watermark)
    return media.generate_video(opts, target_dir(out_dir), wait, mode=MODE)


@mcp.tool()
def query_video(task_id: str, wait: int = 90, out_dir: str | None = None) -> dict:
    """查询 generate_video 的任务，最多等 wait 秒（默认 90，设 0 只查一次）。完成后下载视频，返回文件路径。

    任务结果保留 24 小时。返回字段同 generate_video。
    """
    return media.query_video(task_id, target_dir(out_dir), wait, mode=MODE)


@mcp.tool()
def list_models(keyword: str | None = None) -> dict:
    """列出当前 API Key 能调用的百炼模型 ID，可按关键字过滤（不区分大小写），如 "image"、"qwen3.8"、"deepseek"。

    列表包含语言、生图、语音、向量等走 OpenAI 兼容接口的模型；视频模型（万相 3.0）不在其中。返回 ok、models、error。
    """
    return dashscope.list_models(keyword)


def main():
    mcp.run()
