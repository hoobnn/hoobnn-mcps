"""stdio MCP server：豆包语音合成、识别、音频生成、播客、翻译、妙记、音色，以及按需启用的实时会话和管理接口。

环境变量：VOLC_SPEECH_API_KEY（必需）、DOUBAO_SPEECH_OUT_DIR（默认 ~/Downloads/doubao-speech）、
DOUBAO_SPEECH_JOB_DIR（异步任务记录）、VOLC_SPEECH_BASE_URL（可选）。
"""

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from .mcp_runtime import ReliableMCPServer, merge_parameters

from . import speech
from . import usage
from . import products, management, ws_products, streaming_asr, interpretation, realtime, legacy, tasks

OUT_ROOT = Path(os.environ.get("DOUBAO_SPEECH_OUT_DIR", "~/Downloads/doubao-speech")).expanduser()
LONG_TEXT_AUTO = 5000  # 超过此字数的同步分段合成可能超出单次调用预算，自动改走异步长文本接口
CLONE_LANGUAGES = {"zh": 0, "cn": 0, "en": 1, "ja": 2, "es": 3, "id": 4, "pt": 5, "de": 6, "fr": 7, "ko": 8,
                   "it": 9, "th": 10, "vi": 11, "ru": 12, "fil": 13, "ms": 14, "ar": 15, "mx": 16, "pt-br": 17,
                   "pl": 19, "tr": 20, "sv": 21}


@asynccontextmanager
async def lifespan(server):
    try:
        await realtime.sessions.start()
        yield {}
    finally:
        await realtime.sessions.close_all()


mcp = ReliableMCPServer("doubao-speech", lifespan=lifespan, groups={
    "speech": {"text_to_speech", "speech_to_text", "generate_audio", "generate_podcast", "translate_text",
               "interpret_audio", "summarize_meeting", "speech_raw_request"},
    "voice": {"clone_voice", "design_voice", "get_voice", "upgrade_voice"},
    "jobs": {"list_jobs", "get_job", "recover_job"},
    "realtime": {"open_realtime_session", "send_realtime_event", "receive_realtime_events", "close_realtime_session"},
    "admin": {"manage_word_table", "speech_console"},
    "help": {"list_speech_capabilities", "get_speech_usage_examples", "get_tool_help"}},
    optional_groups={"realtime", "admin"})


def target_dir(out_dir):
    return Path(out_dir).expanduser() if out_dir else OUT_ROOT / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])


def failure(exc):
    return {"ok": False, "error": str(exc)}


def merged(body, parameters):
    try:
        return merge_parameters(body, parameters)
    except ValueError as exc:
        raise speech.InputError(str(exc)) from exc


# ---------- 合成与生成 ----------

@mcp.tool()
def text_to_speech(
    text: str,
    voice: str = "zh_female_vv_uranus_bigtts",
    instructions: str | None = None,
    dialect: str | None = None,
    language: str | None = None,
    speech_rate: int = 0,
    loudness_rate: int = 0,
    pitch: int = 0,
    format: str = "mp3",
    sample_rate: int = 24000,
    subtitles: bool = False,
    pronunciations: list[str] | None = None,
    model: str | None = None,
    resource_id: str | None = None,
    long_text: bool | None = None,
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """用豆包语音合成大模型 2.0 把文字合成语音，保存到本地，返回文件路径。

    - text：要朗读的文字，Markdown 符号会自动过滤不念。同步模式按句切段（每段 1000 字以内）合成再拼接。
    - long_text：不传时自动选择：超过 5000 字且是 2.0 / 复刻音色时改走异步长文本接口（最多 10 万字），立即返回
      job_id，之后用 get_job 查进度，完成后自动下载；true 强制异步，false 强制同步。异步模式 format 只能是
      mp3 / pcm / ogg_opus，subtitles 输出 sentences.json 时间戳而不是 SRT。
    - voice：音色 ID，默认 Vivi（zh_female_vv_uranus_bigtts）。常用 2.0 音色（ID 都是 <前缀>_uranus_bigtts）：
      女声 zh_female_vv（Vivi，通用，支持多语种和方言）、zh_female_xiaohe（小何）、zh_female_sophie（魅力苏菲）、
      zh_female_qingxinnvsheng（清新女声）、zh_female_cancan（知性灿灿）、zh_female_sajiaoxuemei（撒娇学妹）、
      zh_female_tianmeitaozi（甜美桃子）、zh_female_shuangkuaisisi（爽快思思）、zh_female_linjianvhai（邻家女孩）、
      zh_female_wenroumama（温柔妈妈）、zh_female_gaolengyujie（高冷御姐）、zh_female_kefunvsheng（客服）、
      zh_female_xiaoxue（儿童绘本）、zh_female_yingyujiaoxue（Tina 老师，英语教学）；
      男声 zh_male_m191（云舟，通用）、zh_male_taocheng（小天）、zh_male_liufei（刘飞）、zh_male_shaonianzixin
      （少年梓辛）、zh_male_ruyayichen（儒雅逸辰）、zh_male_jieshuoxiaoming（解说小明）、zh_male_dayi（大壹，视频配音）、
      zh_male_yizhipiannan（译制片男）、zh_male_aojiaobazong（傲娇霸总）；英文 en_male_tim、en_female_dacey、
      en_female_stokie。完整列表：https://docs.volcengine.com/docs/6561/1257544
      声音复刻音色（S_ 开头）会自动改用 seed-icl-2.0，1.0 音色（_moon_bigtts / _mars_bigtts）自动用 seed-tts-1.0。
    - instructions：语音指令，用自然语言控制情绪、语气、语速，如「用特别痛心的语气说」「像深夜电台主持人一样低沉
      缓慢」。只有 2.0 音色支持，不计费。
    - dialect：方言 beijing、dongbei、henan、shaanxi、shanghai、sichuan、tianjin、yue（粤语），需要支持方言的音色
      （如 Vivi、小何、云舟、小天）。
    - language：指定语种 zh-cn（中英混读）、en、ja、ko、es-mx、fr、de、ru 等，不传按中英处理。
    - speech_rate / loudness_rate：-50～100，-50 是 0.5 倍，100 是 2 倍，默认 0。pitch：音调 -12～12，默认 0。
    - format：同步 mp3（默认）或 wav。sample_rate：8000、16000、22050、24000（默认）、32000、44100、48000。
    - subtitles：同步模式生成独立命名的 .srt 字幕（句级时间戳，只支持中英文）。同步长文本分段时要用 wav。
    - pronunciations：修正读音或替换文本，每条「原词/(拼音)」或「原词/替换文本」，如 ["重庆/(chong2)(qing4)",
      "omg/oh my god"]，原词不超过 9 个字符。
    - model：只对复刻音色有效，seed-tts-2.0-standard（默认）或 seed-tts-2.0-expressive，指定后不能用 instructions。
    - resource_id：一般不用传，按音色自动选择。
    - out_dir：输出目录，默认 DOUBAO_SPEECH_OUT_DIR 下按时间戳新建。
    - parameters：官方请求体里本工具没列出的字段（SSML、bit_rate、水印、上下文等），深度合并；
      req_params.additions 可直接写成对象，如 {"req_params":{"additions":{"aigc_watermark":true}}}。

    使用示例与引用上文技巧：get_speech_usage_examples(product='tts')。
    按字数计费。同步返回 files、chunks、usage、subtitles；异步返回 job_id、job_state。
    """
    opts = dict(text=text, voice=voice, instructions=instructions, dialect=dialect, language=language,
                speech_rate=speech_rate, loudness_rate=loudness_rate, pitch=pitch, format=format.lower(),
                sample_rate=sample_rate, subtitles=subtitles, pronunciations=pronunciations or [], model=model,
                resource_id=resource_id, parameters=parameters)
    resource = resource_id or speech.tts_resource(voice)
    if long_text is None:
        long_text = len(text) > LONG_TEXT_AUTO and resource in speech.LONG_TTS_RESOURCES
    if not long_text:
        return speech.text_to_speech(opts, target_dir(out_dir))
    if resource not in speech.LONG_TTS_RESOURCES:
        return failure("长文本异步合成只支持 seed-tts-2.0 / seed-icl-2.0 音色")
    try:
        body = speech.build_long_tts_body(opts)
    except (speech.InputError, ValueError) as exc:
        return failure(exc)
    return tasks.submit_tts(body, resource, target_dir(out_dir))


@mcp.tool()
def generate_audio(
    prompt: str,
    speaker: str | None = None,
    reference_audios: list[str] | None = None,
    reference_image: str | None = None,
    format: str = "mp3",
    sample_rate: int | None = None,
    speech_rate: int = 0,
    loudness_rate: int = 0,
    pitch_rate: int = 0,
    subtitles: bool = False,
    model: str = "seed-audio-1.0",
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """用豆包音频生成模型 seed-audio-1.0 按描述生成一段完整音频：音效、环境声、配乐、多角色对白可以混在一起，
    单次最长 120 秒。适合有声书片段、广播剧、影视和游戏配音、音效。只要朗读一段文字时用 text_to_speech，更便宜。

    官方体验中心的四大类用法（以下为改写示例，可组合使用）：
    1. 文本生成：按顺序描述角色的性别、年龄、口音、嗓音、情绪，以及台词、环境声、音效、配乐与转场。
       示例参数：{"prompt":"雨声持续。青年女子嗓音清亮，紧张地说：‘有人来了。’随后响起三声敲门声，低音弦乐渐强。"}。
    2. 参考生成：用 reference_audios 提供样音，在 prompt 用 @音频1、@音频2 按列表顺序绑定角色，
       描述希望参考的音色、情感、风格或节奏；可用于多人对白、声音克隆与风格迁移。
       示例参数：{"prompt":"主持人甲参考@音频1的音色，热情地说：‘欢迎。’主持人乙参考@音频2的音色，轻笑着说：‘你好。’",
       "reference_audios":["/absolute/path/host_a.wav","/absolute/path/host_b.wav"]}。路径须换成真实文件。
    3. 时间控制：在 prompt 写总时长，并在台词或声音事件前写 [开始秒s:结束秒s]，支持小数秒。
       示例参数：{"prompt":"总长10秒，雨声持续。女子轻声说道：[2.7s:5.7s]‘你终于回来了。’[6s:7s]响起敲门声，最后雨声渐弱。",
       "subtitles":true}。控制音效卡点、情绪递进、叙事转场与旁白推进。标记是提示词文本，原样传给官方 text_prompt，
       无独立 timeline 参数，也不由 MCP 后期裁切。实际落点需检查生成音频；subtitles 仅返回人声字幕，不标注全部音效。
    4. 多语种：直接写目标语言台词，并说明角色、语言/口音、情绪与节奏；如标准美式英语、英音或印度英语。
       示例参数：{"prompt":"A young woman speaks warm, clear American English: ‘Welcome home.’ Soft piano continues underneath."}。
       支持中、英、日、韩、西、德、法、葡、泰、越、意、俄等语种，具体清单以官方 API 文档为准。
    - prompt：最多 3000 字，映射为官方 text_prompt。时间区间单位为秒，例如 [2s:5s]、[2.7s:5.7s]。
    - speaker：指定人声音色，可用豆包语音合成 2.0 音色或声音复刻音色（ID 见 text_to_speech 的说明）。
    - reference_audios：参考音频（最多 3 段，每段不超过 30 秒、10MB，wav / mp3 / pcm / ogg_opus），本地绝对路径或
      URL；prompt 里按顺序用 @音频1、@音频2 引用，如「用 @音频1 的声音说……」。
    - reference_image：参考图片（jpeg / png / webp，10MB 内），按画面生成配音或音效，此时 prompt 可以只写要说的
      台词。不能和 speaker、reference_audios 同时用。
    - format：mp3（默认）、wav、pcm、ogg_opus。sample_rate：不传用默认值（mp3 44100，wav/pcm 40000，ogg_opus 48000）。
    - speech_rate / loudness_rate：-50～100，默认 0。pitch_rate：-12～12，默认 0。
    - subtitles：返回句级和词级字幕时间戳；subtitle 中 start_time/end_time 为距音频开始的毫秒偏移。
    - out_dir：输出目录，默认 DOUBAO_SPEECH_OUT_DIR 下按时间戳新建。
    - parameters：官方请求体里本工具没列出的字段，深度合并。

    同步调用，通常要几十秒到两分钟，客户端的工具调用超时要设到 300 秒左右。按生成音频的秒数计费，长音频先和用户
    确认。返回 ok、model、files、url（2 小时内有效）、duration（计费秒数）、subtitle、error。
    官方分类与时间区间写法来源：https://console.volcengine.com/speech/new/experience/audio?projectName=default
    API参数来源：https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh
    """
    opts = dict(prompt=prompt, speaker=speaker, reference_audios=reference_audios or [],
                reference_image=reference_image, format=format.lower(), sample_rate=sample_rate,
                speech_rate=speech_rate, loudness_rate=loudness_rate, pitch_rate=pitch_rate, subtitles=subtitles,
                model=model, parameters=parameters)
    return speech.generate_audio(opts, target_dir(out_dir))


@mcp.tool()
async def generate_podcast(
    text: str | None = None,
    url: str | None = None,
    topic: str | None = None,
    dialogue: list[dict[str, str]] | None = None,
    speakers: list[str] | None = None,
    script_only: bool = False,
    format: str = "mp3",
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """生成双人对谈播客。输入四选一：
    - text：一篇文章，模型改写成对谈（推荐 12000 字以内，超出会截断）。
    - url：网页 / PDF / doc / txt 的公开链接，内容同 text。
    - topic：一个话题，模型联网搜索后生成；它只是话题，不能写格式要求。
    - dialogue：逐轮脚本直接演绎，如 [{"speaker":"音色ID","text":"本轮台词"}]，每轮最多 300 字、总共 1 万字。
    speakers：两个播客音色 ID（按给出的顺序），不传用官方默认。script_only=true 只生成脚本不合成音频（text/url 适用）。
    format：mp3（默认）、pcm、aac、ogg_opus。parameters：官方请求里其余字段（如 retry_info 续传、input_text_max_length），深度合并。
    返回音频路径、rounds（各轮文本与时间）、usage、task_id、last_finished_round_id；断线时音频标 partial，可用
    parameters.retry_info 显式续传。按官方播客计费，可能超过 300 秒。技巧见 get_speech_usage_examples(product='podcast')。
    """
    sources = [name for name, value in (("text", text), ("url", url), ("topic", topic), ("dialogue", dialogue)) if value]
    if len(sources) != 1:
        return failure("text、url、topic、dialogue 必须且只能给一个")
    body = {"action": {"text": 0, "url": 0, "topic": 4, "dialogue": 3}[sources[0]],
            "audio_config": {"format": format.lower(), "sample_rate": 24000}}
    info = {}
    if text:
        body["input_text"] = text
    if url:
        info["input_url"] = url
    if topic:
        body["prompt_text"] = topic
    if dialogue:
        body["nlp_texts"] = dialogue
    if script_only:
        if not (text or url):
            return failure("script_only 只适用于 text 或 url 输入")
        info["only_nlp_text"] = True
    if info:
        body["input_info"] = info
    if speakers:
        body["speaker_info"] = {"speakers": speakers, "random_order": False}
    try:
        merged(body, parameters)
    except speech.InputError as exc:
        return failure(exc)
    return await ws_products.podcast(body, target_dir(out_dir))


# ---------- 识别、翻译、妙记 ----------

@mcp.tool()
def speech_to_text(
    audio: str,
    mode: str = "auto",
    language: str | None = None,
    hotwords: list[str] | None = None,
    context: str | None = None,
    utterances: bool = False,
    speakers: bool = False,
    itn: bool = True,
    punc: bool = True,
    ddc: bool = False,
    format: str | None = None,
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """用豆包录音文件识别大模型把音频转成文字。返回情绪和语种标签的千问 ASR 用 ali-bailian。

    - audio：本地绝对路径或 http(s) URL。支持 wav、mp3、ogg（opus）、m4a、aac、amr、spx。
    - mode：
      auto（默认）：要 speakers 时用 standard，否则用 flash。
      flash：极速版，同步返回，本地文件或 URL，不超过 100MB、2 小时；一小时音频通常十几秒到一分钟出结果。
      standard：标准版异步，只接受可下载 URL，最大 512MB、5 小时；立即返回 job_id，用 get_job 查结果，
      完成后保存 transcript.txt 和完整 result.json。idle：闲时版，同 standard，更便宜但更慢。
    - language：已知语种时指定，如 zh-CN、en-US、ja-JP、ko-KR、yue-CN（粤语）；不传自动识别中英粤和多种方言。
    - hotwords：热词，提高人名、品牌、术语识别率，如 ["Kubernetes", "火山引擎"]。
    - context：背景文字，如「这是一段关于 Rust 异步运行时的技术分享」，最多约 500 token。
    - utterances：返回分句（起止毫秒、文本、说话人）。speakers：区分说话人（10 人以内效果较好），需 standard/idle。
    - itn：口语数字转阿拉伯数字，默认开；punc：加标点，默认开；ddc：去掉「嗯」「那个」等口头禅，默认关。
    - format：URL 或文件没有扩展名时手动指定格式。
    - parameters：官方请求体（{"audio":{...},"request":{...}}）里其余字段，深度合并，如
      {"request":{"ssd_version":"300"}}（长会议说话人分离）。

    按音频时长计费。flash 返回 text、duration_ms、utterances；standard/idle 返回 job_id、job_state。
    实时流式识别和一句话识别用 speech_raw_request(product='asr_stream')。
    """
    if mode == "auto":
        mode = "standard" if speakers else "flash"
    opts = dict(audio=audio, language=language, hotwords=hotwords or [], context=context,
                utterances=utterances or speakers, itn=itn, punc=punc, ddc=ddc, format=format, parameters=parameters)
    if mode == "flash":
        if speakers:
            return failure("说话人分离需要 mode=standard 或 idle（要求音频是可下载 URL）")
        return speech.speech_to_text(opts)
    if mode not in products.ASR_MODES:
        return failure("mode 只能是 auto、flash、standard 或 idle")
    if not speech.is_remote(audio):
        return failure("standard / idle 只接受可下载的 http(s) URL；本地文件请用 mode=flash")
    try:
        request = speech.asr_request(opts)
        if speakers:
            request.update(enable_speaker_info=True, ssd_version="200")
        body = merged({"user": {"uid": "doubao_speech_mcp"}, "audio": speech.asr_audio(audio, format, language),
                       "request": request}, parameters)
    except speech.InputError as exc:
        return failure(exc)
    return tasks.submit_asr(body, mode, target_dir(out_dir))


@mcp.tool()
def translate_text(texts: list[str], target_language: str, source_language: str = "",
                   glossary: dict[str, str] | None = None, glossary_table_id: str | None = None,
                   parameters: dict | None = None) -> dict:
    """Seed-X 机器翻译。texts 一次 1–16 条，每条最多 1024 tokens（服务端校验），按原顺序返回。
    target_language 如 en / zh / ja；source_language 不传自动检测。
    glossary 指定术语译法，如 {"火山引擎":"Volcengine"}，优先于术语表；glossary_table_id 使用控制台建好的术语表。
    parameters：官方请求体其余字段，深度合并。返回 translation_list、检测到的语种、token 用量。按 token 计费。
    """
    corpus = {}
    if glossary:
        corpus["glossary_list"] = glossary
    if glossary_table_id:
        corpus["glossary_table_id"] = glossary_table_id
    return management.translate_text(texts, target_language, source_language, corpus or None, parameters)


@mcp.tool()
async def interpret_audio(audio: str, source_language: str, target_language: str, mode: str = "s2t",
                          hotwords: list[str] | None = None, glossary: dict[str, str] | None = None,
                          voice: str | None = None, output_format: str = "pcm",
                          out_dir: str | None = None, parameters: dict | None = None) -> dict:
    """同声传译 2.0，处理本地 16kHz / 16bit / 单声道 WAV 或 PCM 文件。source_language / target_language 如 zh / en。
    mode=s2t 只出原文和译文字幕；s2s 另外合成目标语音，output_format=pcm（16kHz）或 ogg_opus（48kHz），voice 指定音色。
    hotwords 提高识别率；glossary 固定术语译法，如 {"火山引擎":"Volcengine"}。
    parameters：官方 TranslateRequest 其余字段，深度合并，如 {"request":{"enable_source_language_detect":true}}。
    返回原文/译文字幕、usage 和本地音频。实时麦克风需客户端采集，本工具只处理文件。按同传服务计费。
    """
    request = {"request": {}}
    corpus = {}
    if hotwords:
        corpus["hot_words_list"] = hotwords
    if glossary:
        corpus["glossary_list"] = glossary
    if corpus:
        request["request"]["corpus"] = corpus
    if voice:
        request["request"]["speaker_id"] = voice
    if mode == "s2s":
        request["target_audio"] = {"format": output_format}
    try:
        merged(request, parameters)
    except speech.InputError as exc:
        return failure(exc)
    return await interpretation.interpret_audio(audio, source_language, target_language, mode, request, target_dir(out_dir))


@mcp.tool()
def summarize_meeting(
    file_url: str,
    language: str = "zh_cn",
    file_type: str = "audio",
    summary: bool = True,
    chapters: bool = False,
    todos: bool = False,
    qa: bool = False,
    translate_to: str | None = None,
    speakers: bool = True,
    speaker_count: int = 0,
    hotwords: list[str] | None = None,
    word_timestamps: bool = False,
    bundle_billing: bool = False,
    out_dir: str | None = None,
    parameters: dict | None = None,
) -> dict:
    """豆包语音妙记：会议 / 课程录音或视频的转写，加全文总结、章节、待办、问答提取、翻译。异步：立即返回 job_id，
    之后用 get_job 查进度，完成后把各项结果 JSON 下载到本地（官方链接 24 小时有效）。

    - file_url：可下载的 http(s) 链接。file_type=audio（MP3/WAV/AAC/FLAC/OGG）或 video（MP4/AVI/MKV/MOV/FLV/WMV）。
    - language：原始语种 zh_cn 或 en_us。
    - summary 全文总结（默认开）、chapters 章节总结、todos 待办提取、qa 问答提取；translate_to=zh_cn / en_us 翻译转写文本。
      至少开一项；只要转写文字请用 speech_to_text。
    - speakers 区分说话人（默认开），speaker_count 已知人数时填写，0 自动识别。hotwords 热词。word_timestamps 词级时间。
    - bundle_billing：官方 AllActivate，选择打包计费；它只决定计费方式，不会自动打开任何功能。
    - parameters：官方请求体（Input / Params）其余字段，深度合并。
    按妙记服务计费。
    """
    transcription = {"SpeakerIdentification": speakers, "NumberOfSpeaker": speaker_count,
                     "NeedWordTimeSeries": word_timestamps}
    if hotwords:
        import json
        transcription["HotWords"] = json.dumps([{"word": w} for w in hotwords], ensure_ascii=False)
    params = {"AllActivate": bundle_billing, "SourceLang": language, "AudioTranscriptionEnable": True,
              "AudioTranscriptionParams": transcription}
    if summary:
        params.update(SummarizationEnabled=True, SummarizationParams={"Types": ["summary"]})
    if chapters:
        params["ChapterEnabled"] = True
    extraction = [name for name, enabled in (("todo_list", todos), ("question_answer", qa)) if enabled]
    if extraction:
        params.update(InformationExtractionEnabled=True, InformationExtractionParams={"Types": extraction})
    if translate_to:
        params.update(TranslationEnable=True, TranslationParams={"TargetLang": translate_to})
    try:
        request = merged({"Input": {"Offline": {"FileURL": file_url, "FileType": file_type}}, "Params": params},
                         parameters)
    except speech.InputError as exc:
        return failure(exc)
    if not speech.is_remote(file_url):
        return failure("file_url 必须是可下载的 http(s) 链接")
    if not any(params.get(k) for k in ("SummarizationEnabled", "ChapterEnabled", "InformationExtractionEnabled",
                                       "TranslationEnable")):
        return failure("至少开启 summary、chapters、todos、qa、translate_to 之一；只要转写请用 speech_to_text")
    return tasks.submit_minutes(request, target_dir(out_dir))


# ---------- 音色 ----------

def voice_body(speaker_id, custom_speaker_id=None, parameters=None):
    body = {"speaker_id": speaker_id}
    if custom_speaker_id:
        body["custom_speaker_id"] = custom_speaker_id
    return merged(body, parameters)


@mcp.tool()
def clone_voice(speaker_id: str, audio_file: str, text: str | None = None, language: str | None = None,
                demo_text: str | None = None, custom_speaker_id: str | None = None,
                parameters: dict | None = None) -> dict:
    """声音复刻：用一段录音注册或重新训练音色。speaker_id 是控制台已分配的 S_ 音色 ID（用自定义 ID 时传
    speaker_id='custom_speaker_id' 并填 custom_speaker_id）。audio_file：本地录音（wav/mp3/ogg/m4a/aac/pcm，10MB 内），
    清晰单人、少噪音。text：录音对应文本，服务会比对，差异过大会失败。language：zh（默认）、en、ja、es、de、fr、ko、
    it、ru、pt、pt-br 等。demo_text：试听文本 4–300 字。parameters：官方请求其余字段（如 extra_params、model_type），深度合并。
    会消耗训练次数，不自动重试。之后用 get_voice 查训练状态，合成时把 speaker_id 作为 text_to_speech 的 voice；复刻的音色只能用于豆包合成。
    录音技巧见 get_speech_usage_examples(product='voice')。
    """
    try:
        body = voice_body(speaker_id, custom_speaker_id)
        body["audio"] = {}
        if text:
            body["text"] = text
        if language:
            if language.lower() not in CLONE_LANGUAGES:
                raise speech.InputError(f"不支持的 language：{language}")
            body["language"] = CLONE_LANGUAGES[language.lower()]
        if demo_text:
            body["extra_params"] = {"demo_text": demo_text}
        merged(body, parameters)
    except speech.InputError as exc:
        return failure(exc)
    return products.voice_clone(body, audio_file)


@mcp.tool()
def design_voice(speaker_id: str, preview_text: str, description: str | None = None, image: str | None = None,
                 parameters: dict | None = None) -> dict:
    """音色设计：用文字描述或一张图片生成新音色。speaker_id 是控制台已分配的音色 ID。preview_text：试听台词，最多 300 字。
    description：声音描述，最多 200 字，如「三十岁左右的男声，低沉温和，语速偏慢」；image：本地图片或 URL（10MB 内），
    按画面人物生成声音。两者至少给一个，都给时图片优先。parameters：官方请求其余字段，深度合并。
    会消耗训练次数。返回音色和试听信息。声线描述技巧见 get_speech_usage_examples(product='voice')。
    """
    try:
        body = voice_body(speaker_id)
        body["text"] = preview_text
        prompt = body["prompt"] = {}
        if description:
            prompt["text_prompt"] = description
        image_file = None
        if image and speech.is_remote(image):
            prompt["image_prompt"] = {"image_url": image}
        elif image:
            image_file = image
        merged(body, parameters)
    except speech.InputError as exc:
        return failure(exc)
    return products.voice_design(body, image_file)


@mcp.tool()
def get_voice(speaker_id: str, custom_speaker_id: str | None = None, parameters: dict | None = None) -> dict:
    """查询复刻 / 设计音色的训练状态、剩余训练次数和试听信息。不计费。"""
    try:
        body = voice_body(speaker_id, custom_speaker_id, parameters)
    except speech.InputError as exc:
        return failure(exc)
    return products.voice_query(body)


@mcp.tool()
def upgrade_voice(speaker_id: str, custom_speaker_id: str | None = None, parameters: dict | None = None) -> dict:
    """把已有复刻音色升级到新版模型（不可撤回）。parameters：官方升级参数，深度合并。之后用 get_voice 查状态。"""
    try:
        body = voice_body(speaker_id, custom_speaker_id, parameters)
    except speech.InputError as exc:
        return failure(exc)
    return products.voice_upgrade(body)


# ---------- 异步任务 ----------

@mcp.tool()
def list_jobs(limit: int = 20, kind: str | None = None) -> dict:
    """列出最近的异步任务（长文本合成 tts_long、录音识别 asr、妙记 minutes），不联网。调用超时没拿到 job_id 时用它找回。"""
    return tasks.STORE.list(limit, kind)


@mcp.tool()
def get_job(job_id: str | None = None, task_id: str | None = None, wait: int = 0) -> dict:
    """查异步任务的进度和结果，job_id 或 task_id 二选一。任务还在进行时查询豆包一次（wait 1–90 秒可轮询），
    完成即把结果保存到原输出目录；已结束的任务只读本地记录。不会重新提交。
    返回 job_state（running/delivered/failed/download_failed）、completed、files、text（识别）、error。
    """
    return tasks.get_job(job_id, task_id, wait)


@mcp.tool()
def recover_job(job_id: str) -> dict:
    """修复交付：结果下载失败或本地文件丢失时重新保存，链接过期则重新查询一次。正常查进度用 get_job。不会重新提交。"""
    return tasks.recover(job_id)


# ---------- 帮助与兜底 ----------

@mcp.tool()
def get_speech_usage_examples(product: str = "audio", category: str | None = None) -> dict:
    """查询官方示例的归纳、改写的MCP调用参数、使用技巧和来源；纯本地，无鉴权，不调用云服务。
    product=audio/tts/voice/podcast/asr/translation/minutes/realtime。
    audio支持category=text/reference/timing/multilingual；不传category返回该产品全部示例。
    示例包括参考绑定、时间戳卡点、多语种、引用上文、音色设计/复刻、播客四种输入、热词/上下文/说话人分离等。
    路径、URL、音色ID和会话ID占位符需替换；示例未经真实云端生成验证。
    """
    return usage.get_examples(product, category)


@mcp.tool()
def list_speech_capabilities() -> dict:
    """列出豆包语音产品、工具、未启用的工具组及启用方法、管理 Action、官方链接和接入边界；不联网、不计费。"""
    return {
        "products": {
            "tts": ["text_to_speech"],
            "audio": ["generate_audio", "generate_podcast"],
            "asr": ["speech_to_text"],
            "translation": ["translate_text", "interpret_audio"],
            "minutes": ["summarize_meeting"],
            "voice": ["clone_voice", "design_voice", "get_voice", "upgrade_voice"],
            "jobs": ["list_jobs", "get_job", "recover_job"],
            "raw": ["speech_raw_request"],
            "realtime": ["open_realtime_session", "send_realtime_event", "receive_realtime_events", "close_realtime_session"],
            "admin": ["manage_word_table", "speech_console"],
        },
        "raw_products": sorted(RAW_PRODUCTS),
        "usage_examples": {"tool": "get_speech_usage_examples", "products": list(usage.GUIDES),
                           "audio_categories": list(usage.GUIDES["audio"]["categories"])},
        "word_table_actions": sorted(management.HOTWORD_ACTIONS | management.CORRECT_ACTIONS),
        "console_action_versions": management.CONSOLE_VERSIONS,
        "legacy_operations": sorted(legacy.OPERATIONS),
        "docs": {**products.DOCS,
                 "index": "https://docs.volcengine.com/docs/DoubaoVoice/list?lang=zh",
                 "realtime": "https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh",
                 "podcast": "https://docs.volcengine.com/docs/DoubaoVoice/PodcastAPI-websocket-v3protocol?lang=zh",
                 "interpretation": "https://docs.volcengine.com/docs/DoubaoVoice/SimultaneousInterpretation20APIAccessDocumentation?lang=zh"},
        "limits": ["Speech SDK端侧离线能力需原生应用集成；MCP提供云API。",
                   "realtime（持久实时语音会话）和 admin（热词/替换词表、控制台 OpenAPI，需 AK/SK，可下单和删除）默认不启用。",
                   "术语词表CRUD官方仅提供控制台；使用支持glossary / glossary_table_id。",
                   "历史版本API未等同于当前产品全部通过线上验证；实际服务开通和权限以账号为准。"],
    }


RAW_PRODUCTS = {"tts", "asr_flash", "audio", "tts_websocket", "asr_stream", "legacy"}


@mcp.tool()
async def speech_raw_request(product: str, request: dict | None = None, operation: str | None = None,
                             query: dict | None = None, audio: str | None = None, mode: str | None = None,
                             text_chunks: list[str] | None = None, resource_id: str | None = None,
                             out_dir: str | None = None) -> dict:
    """兜底入口：按官方请求体原样调用，其他工具覆盖不到时才用。端点固定，不接收任意 URL。
    - product=tts / asr_flash / audio：HTTP 合成、极速识别、音频生成，request 为官方完整请求体；音频 base64 换成本地文件。
    - product=tts_websocket：WebSocket 合成，mode=unidirectional 或 bidirectional（text_chunks 按顺序流式输入）。
    - product=asr_stream：一句话 / 实时流式识别本地 16bit 单声道 WAV/PCM，audio 为文件路径，mode=realtime 或 sentence。
    - product=legacy：历史 HTTP 产品（字幕生成、打轴、旧 TTS/ASR），operation 见 list_speech_capabilities，
      request 为 JSON 体、query 为 URL 参数；需要 VOLC_SPEECH_APP_ID / VOLC_SPEECH_ACCESS_TOKEN。
    返回完整官方响应。按对应服务计费，提交类请求不自动轮询或重试。
    """
    if product not in RAW_PRODUCTS:
        return failure(f"product 只能是 {', '.join(sorted(RAW_PRODUCTS))}")
    if product == "tts_websocket":
        return await ws_products.synthesize(request or {}, target_dir(out_dir), mode or "bidirectional",
                                            text_chunks, resource_id)
    if product == "asr_stream":
        if not audio:
            return failure("asr_stream 需要 audio 文件路径")
        return await streaming_asr.streaming_recognize(audio, request, mode or "realtime", resource_id)
    if product == "legacy":
        if not operation:
            return failure("legacy 需要 operation")
        return await asyncio.to_thread(legacy.legacy_call, operation, request, query)
    return await asyncio.to_thread(products.raw_http, product, request or {}, target_dir(out_dir), resource_id)


# ---------- 按需启用：实时会话（MCP_TOOL_GROUPS 含 realtime） ----------

@mcp.tool()
async def open_realtime_session(session: dict, extension: dict | None = None, out_dir: str | None = None, timeout: float = 30) -> dict:
    """打开豆包实时语音3.0持久会话。最简session={audio:{output:{voice:'zh_female_vv_jupiter_bigtts'}}}，默认model=1.2.6.1、输入pcm16k/输出pcm_s16le24k。
    可传instructions、tools（function定义）、audio配置；输入格式支持pcm/speech_opus（opus别名自动规范化），extension顶层支持asr/tts/dialog、热词、联网搜索、唱歌等。
    返回客户端session_id，后续send/receive/close；会话只在本MCP进程内有效。创建后持续收包，生成音频写本地文件。按实时服务计费。
    """
    return await realtime.sessions.open(session, target_dir(out_dir), extension, timeout)


@mcp.tool()
async def send_realtime_event(session_id: str, event: dict, audio_file: str | None = None, timeout: float = 30) -> dict:
    """向持久实时会话发送官方JSON事件。event须有type：input_audio_buffer.append + audio(base64)，input_audio_buffer.commit强制判停；response.cancel打断；session.update更新配置。
    conversation.item.create/retrieve/delete管理上下文，role=tool+call_id回传Function Calling结果；input_audio_mute.commit/unmute.commit处理静音。
    audio_file可传16kHz/mono/int16裸.pcm，自动20ms分包，仅用于append；文件结束后再发送commit。会话开闭使用专用工具。
    """
    return await realtime.sessions.send(session_id, event, audio_file or "", timeout)


@mcp.tool()
async def receive_realtime_events(session_id: str, max_events: int = 100, timeout: float = 10) -> dict:
    """接收实时会话事件（等待最多timeout秒，<=60秒），返回ASR、回复文本、Function Calling、上下文、usage等。
    音频delta会转换为audio_file/chunk_bytes/audio_format/sample_rate，不返回巨大base64。收到工具调用后执行本地工具，再send_realtime_event回传call_id结果。
    """
    return await realtime.sessions.receive(session_id, max_events, timeout)


@mcp.tool()
async def close_realtime_session(session_id: str, timeout: float = 10) -> dict:
    """优雅关闭实时会话，等待session.closed，释放连接。退出MCP也会清理会话；历史session.id可用于后续官方会话接续。"""
    return await realtime.sessions.close(session_id, timeout)


# ---------- 按需启用：管理接口（MCP_TOOL_GROUPS 含 admin） ----------

@mcp.tool()
def manage_word_table(action: str, parameters: dict, content: str | None = None, auth: str = "api_key") -> dict:
    """热词/替换词词表管理。action取Create/Update/Delete/Get/ListBoostingTable，或对应CorrectTable（具体支持列表见list_speech_capabilities）。
    parameters按官方字段传入BoostingTableID/BoostingTableName或TableID/TableName；创建/更新时content为词表文本，自动multipart上传。
    热词默认API Key，替换词用auth='aksk'，需要VOLC_ACCESS_KEY_ID/VOLC_SECRET_ACCESS_KEY。术语表通过翻译/同传corpus使用，官方未公开术语CRUD API。
    """
    return management.word_table(action, parameters, content, auth)


@mcp.tool()
def speech_console(action: str, parameters: dict, version: str | None = None) -> dict:
    """控制台OpenAPI：音色、API Key、服务开停、资源包/声音复刻订单、用量、配额、项目标签管理。action和parameters按官方契约；list_speech_capabilities给出支持动作。
    需要VOLC_ACCESS_KEY_ID/VOLC_SECRET_ACCESS_KEY（IAM AK/SK，区别于语音API Key）。version默认按动作选择。会执行指定动作，包括创建、删除、下单；查询优先使用List/Get/QuotaMonitoring/UsageMonitoring。
    """
    return management.console_action(action, parameters, version)


def main():
    mcp.run()
