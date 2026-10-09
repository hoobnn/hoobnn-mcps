"""stdio MCP server：豆包语音云产品、流式协议、实时会话及管理接口。

环境变量：VOLC_SPEECH_API_KEY（必需）、DOUBAO_SPEECH_OUT_DIR（默认 ~/Downloads/doubao-speech）、
VOLC_SPEECH_BASE_URL（可选）。
"""

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import speech
from . import products, management, ws_products, streaming_asr, interpretation, realtime, legacy

OUT_ROOT = Path(os.environ.get("DOUBAO_SPEECH_OUT_DIR", "~/Downloads/doubao-speech")).expanduser()

@asynccontextmanager
async def lifespan(server):
    try:
        yield {}
    finally:
        await realtime.sessions.close_all()


mcp = MCPServer("doubao-speech", lifespan=lifespan)


def target_dir(out_dir):
    return Path(out_dir).expanduser() if out_dir else OUT_ROOT / time.strftime("%Y%m%d-%H%M%S")


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
    out_dir: str | None = None,
) -> dict:
    """用豆包语音合成大模型 2.0 把文字合成语音，保存到本地，返回文件路径。

    - text：要朗读的文字，Markdown 符号会自动过滤不念。长文本自动按句切段（每段 1000 字以内）合成再拼接。
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
    - format：mp3（默认）或 wav。sample_rate：8000、16000、22050、24000（默认）、32000、44100、48000。
    - subtitles：同时生成 speech.srt 字幕（句级时间戳，只支持中英文），返回值 subtitles 里也有。长文本分段时要用 wav。
    - pronunciations：修正读音或替换文本，每条「原词/(拼音)」或「原词/替换文本」，如 ["重庆/(chong2)(qing4)",
      "omg/oh my god"]，原词不超过 9 个字符。
    - model：只对复刻音色有效，seed-tts-2.0-standard（默认）或 seed-tts-2.0-expressive，指定后不能用 instructions。
    - resource_id：一般不用传，按音色自动选择。
    - out_dir：输出目录，默认 DOUBAO_SPEECH_OUT_DIR 下按时间戳新建。

    按字数计费。返回 ok、resource_id、files、chunks（分了几段）、usage（text_words 计费字数）、subtitles、error。
    """
    opts = dict(text=text, voice=voice, instructions=instructions, dialect=dialect, language=language,
                speech_rate=speech_rate, loudness_rate=loudness_rate, pitch=pitch, format=format.lower(),
                sample_rate=sample_rate, subtitles=subtitles, pronunciations=pronunciations or [], model=model,
                resource_id=resource_id)
    return speech.text_to_speech(opts, target_dir(out_dir))


@mcp.tool()
def speech_to_text(
    audio: str,
    language: str | None = None,
    hotwords: list[str] | None = None,
    context: str | None = None,
    utterances: bool = False,
    itn: bool = True,
    punc: bool = True,
    ddc: bool = False,
    format: str | None = None,
) -> dict:
    """用豆包录音文件识别大模型（极速版）把音频转成文字，同步返回结果。

    - audio：本地绝对路径或 http(s) URL。支持 wav、mp3、ogg（opus）、m4a、aac、amr、spx，不超过 100MB、2 小时。
      识别一小时的音频通常只要十几秒到一分钟。
    - language：已知语种时指定，如 zh-CN、en-US、ja-JP、ko-KR、yue-CN（粤语）、fr-FR、de-DE；不传时自动识别中文、
      英文、粤语和上海话、闽南话、四川话、陕西话等方言。
    - hotwords：热词列表，提高人名、品牌、术语的识别率，如 ["Kubernetes", "火山引擎"]。
    - context：背景文字，如「这是一段关于 Rust 异步运行时的技术分享」，最多约 500 token。
    - utterances：返回分句（起止毫秒、文本、说话人编号），做字幕或区分说话人时打开。
    - itn：口语数字转阿拉伯数字（「一九七零年」→「1970 年」），默认开。punc：加标点，默认开。
      ddc：语义顺滑，去掉「嗯」「那个」等口头禅和重复，默认关。
    - format：URL 或文件没有扩展名时手动指定格式。

    按音频时长计费。返回 ok、text、duration_ms、utterances、error。
    """
    opts = dict(audio=audio, language=language, hotwords=hotwords or [], context=context, utterances=utterances,
                itn=itn, punc=punc, ddc=ddc, format=format)
    return speech.speech_to_text(opts)


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
) -> dict:
    """用豆包音频生成模型 seed-audio-1.0 按描述生成一段完整音频：音效、环境声、配乐、多角色对白可以混在一起，
    单次最长 120 秒。适合有声书片段、广播剧、影视和游戏配音、音效。只要朗读一段文字时用 text_to_speech，更便宜。

    - prompt：最多 3000 字。按时间顺序写清楚声音和台词，角色写明性别、年龄、口音、嗓音和语气，台词用引号，如
      「先是一声手机震动，环境里有持续的鸟鸣。男子1（中年男性，嗓音低沉）严肃地说：“你什么时候被收买的？”然后是
      两声高跟鞋的脚步声。」也可以写总时长和某句话出现的时间点。支持中、英、日、韩、西、德、法、葡、泰、越、意、
      俄等语种。
    - speaker：指定人声音色，可用豆包语音合成 2.0 音色或声音复刻音色（ID 见 text_to_speech 的说明）。
    - reference_audios：参考音频（最多 3 段，每段不超过 30 秒、10MB，wav / mp3 / pcm / ogg_opus），本地绝对路径或
      URL；prompt 里按顺序用 @音频1、@音频2 引用，如「用 @音频1 的声音说……」。
    - reference_image：参考图片（jpeg / png / webp，10MB 内），按画面生成配音或音效，此时 prompt 可以只写要说的
      台词。不能和 speaker、reference_audios 同时用。
    - format：mp3（默认）、wav、ogg_opus。sample_rate：不传用默认值（mp3 44100，wav 40000）。
    - speech_rate / loudness_rate：-50～100，默认 0。pitch_rate：-12～12，默认 0。
    - subtitles：返回句级和词级字幕时间戳。
    - out_dir：输出目录，默认 DOUBAO_SPEECH_OUT_DIR 下按时间戳新建。

    同步调用，通常要几十秒到两分钟，客户端的工具调用超时要设到 300 秒左右。按生成音频的秒数计费，长音频先和用户
    确认。返回 ok、model、files、url（2 小时内有效）、duration（计费秒数）、subtitle、error。
    """
    opts = dict(prompt=prompt, speaker=speaker, reference_audios=reference_audios or [],
                reference_image=reference_image, format=format.lower(), sample_rate=sample_rate,
                speech_rate=speech_rate, loudness_rate=loudness_rate, pitch_rate=pitch_rate, subtitles=subtitles,
                model=model)
    return speech.generate_audio(opts, target_dir(out_dir))


@mcp.tool()
def submit_long_text_speech(request: dict, resource_id: str = "seed-tts-2.0") -> dict:
    """异步长文本合成，最多100000字符。request={req_params:{text,speaker,audio_params:{format:'mp3'},additions:'JSON字符串'},unique_id?:'20–64字符'}。
    返回 task_id 等原始字段；用 query_long_text_speech 查询。复刻音色用 seed-icl-2.0。按合成文本计费。
    """
    return products.tts_submit(request, resource_id)


@mcp.tool()
def query_long_text_speech(task_id: str, resource_id: str = "seed-tts-2.0", request: dict | None = None) -> dict:
    """查询长文本合成任务一次，保留状态、进度、音频URL和字幕。resource_id须与提交一致。request可传官方额外字段。"""
    return products.tts_query(task_id, resource_id, request)


@mcp.tool()
def clone_voice(request: dict, audio_file: str | None = None) -> dict:
    """注册/重新训练复刻音色。request={speaker_id:'已分配的S_音色ID',audio:{data:'base64',format:'wav'},text?:'录音文本',language?:'zh',extra_params?:{demo_text:'试听文本'}}。
    audio_file可传本地音频替代audio.data，10MB以内。speaker_id='custom_speaker_id'时还需custom_speaker_id字段。会消耗训练次数；开通音色后调用。
    """
    return products.voice_clone(request, audio_file)


@mcp.tool()
def query_voice(request: dict) -> dict:
    """查询复刻音色状态、训练次数等。request={speaker_id:'S_...'}，支持官方全部字段。"""
    return products.voice_query(request)


@mcp.tool()
def upgrade_voice(request: dict) -> dict:
    """升级已有复刻音色。request={speaker_id:'S_...'}，可传官方升级参数。升级后用query_voice查状态。"""
    return products.voice_upgrade(request)


@mcp.tool()
def design_voice(request: dict, image_file: str | None = None) -> dict:
    """文本/图片设计音色。request={speaker_id:'已分配音色ID',text:'4–300字试听文本',prompt:{text_prompt:'最多200字符声音描述'}}。
    图片改用prompt.image_prompt:{image_url:'URL'}或image_bytes:'base64'，image_file可自动填本地图（10MB）。完整官方参数透传，返回音色和试听信息。
    """
    return products.voice_design(request, image_file)


@mcp.tool()
def submit_transcription(request: dict, mode: str = "standard", resource_id: str | None = None, task_id: str | None = None) -> dict:
    """提交标准/闲时录音识别。request={user:{uid:'mcp'},audio:{url:'可下载音频URL'},request:{model_name:'bigmodel',enable_itn:true,enable_punc:true,show_utterances:true}}。
    mode=standard（默认2.0资源volc.seedasr.auc）或idle（volc.bigasr.auc_idle）；完整请求支持视觉上下文、说话人、词表等官方参数。
    返回task_id，后续query_transcription；不自动重复提交。按音频时长计费。
    """
    return products.asr_submit(request, mode, resource_id, task_id)


@mcp.tool()
def query_transcription(task_id: str, mode: str = "standard", resource_id: str | None = None, request: dict | None = None, logid: str | None = None) -> dict:
    """查询录音识别一次，mode/resource_id同提交。返回queued/running/succeeded/silent/failed及完整识别文本、分句、时间戳。"""
    return products.asr_query(task_id, mode, resource_id, request, logid)


@mcp.tool()
def translate_text(text_list: list[str], target_language: str, source_language: str = "", corpus: dict | None = None, request: dict | None = None) -> dict:
    """Seed-X机器翻译。一次1–16条文本，每条最多1024 tokens（服务端校验）。target_language例如en/zh，source_language不传自动检测。
    corpus={glossary_list:{'原词':'译词'},glossary_table_id?:'ID',glossary_table_name?:'名称'}；request可传完整官方高级参数。
    返回translation_list、自动检测语种、token用量。按token计费。
    """
    return management.translate_text(text_list, target_language, source_language, corpus, request)


@mcp.tool()
def submit_minutes(request: dict, request_id: str | None = None) -> dict:
    """语音妙记：转写、翻译、总结、章节、信息提取。request={Input:{Offline:{FileURL:'URL',FileType:'audio'}},Params:{AllActivate:false,SourceLang:'zh_cn',AudioTranscriptionEnable:true,AudioTranscriptionParams:{SpeakerIdentification:true},SummarizationEnabled:true}}。
    Params.AllActivate须显式传bool（计费选择，不自动启用功能），至少开TranslationEnable/InformationExtractionEnabled/SummarizationEnabled/ChapterEnabled之一。返回task_id/request_id供query_minutes。
    """
    return management.minutes_submit(request, request_id)


@mcp.tool()
def query_minutes(task_id: str, request_id: str | None = None) -> dict:
    """查询妙记任务一次。返回running/success/failed和转写、摘要、章节等JSON结果URL；临时链接请及时保存。"""
    return management.minutes_query(task_id, request_id)


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


@mcp.tool()
async def websocket_text_to_speech(request: dict, mode: str = "bidirectional", text_chunks: list[str] | None = None, resource_id: str | None = None, out_dir: str | None = None) -> dict:
    """WebSocket单向/双向合成。request={req_params:{speaker:'音色ID',text:'文本',audio_params:{format:'mp3',sample_rate:24000},additions:'JSON字符串'}}。
    mode=unidirectional一次输入；bidirectional可传text_chunks按顺序流式输入文本。保留字幕、usage等事件并保存本地音频。支持SSML、语音指令、水印、上下文等官方全部参数。按文本计费。
    """
    return await ws_products.synthesize(request, target_dir(out_dir), mode, text_chunks, resource_id)


@mcp.tool()
async def generate_podcast(request: dict, out_dir: str | None = None) -> dict:
    """双人播客。request={action:0,input_text:'文章',audio_config:{format:'mp3'}}；也可input_info.input_url传网页/PDF/doc/txt链接。
    action=3传nlp_texts:[{speaker:'音色ID',text:'每轮<=300字'}]直接演绎；action=4传prompt_text联网总结。
    speaker_info.speakers指定两个音色；input_info.only_nlp_text仅生成脚本。高级选项完整透传。
    返回音频路径、轮次时间、usage、task_id、last_finished_round_id；断线音频标partial，显式retry_info可续传。按官方播客计费，可能超过300秒。
    """
    return await ws_products.podcast(request, target_dir(out_dir))


@mcp.tool()
async def streaming_speech_to_text(audio: str, request: dict | None = None, mode: str = "realtime", resource_id: str | None = None) -> dict:
    """一句话/实时流式识别本地WAV或PCM（16bit单声道，PCM默认16kHz）。mode=realtime或sentence（具体可选值见能力目录）。
    request为官方完整user/audio/request配置，支持热词、上下文、标点、说话人等。自动分包并发收发，返回最终文本、分句及服务端事件。按音频时长计费。
    """
    return await streaming_asr.streaming_recognize(audio, request, mode, resource_id)


@mcp.tool()
async def interpret_audio(audio: str, source_language: str, target_language: str, mode: str = "s2t", request: dict | None = None, out_dir: str | None = None) -> dict:
    """同声传译2.0，输入本地16kHz/16bit/单声道WAV或PCM。source_language/target_language例如zh/en，mode=s2t字幕或s2s语音。
    request是官方完整TranslateRequest字典：request.corpus支持hot_words_list/correct_words/glossary_list和词表ID；target_audio设置pcm/ogg_opus；request.speaker_id可指定音色。
    自动Protobuf分包、并发收发，返回原文/译文字幕、usage和本地音频；此工具处理文件，实时麦克风需客户端采集。按同传服务计费。
    """
    return await interpretation.interpret_audio(audio, source_language, target_language, mode, request, target_dir(out_dir))


@mcp.tool()
async def open_realtime_session(session: dict, extension: dict | None = None, out_dir: str | None = None, timeout: float = 30) -> dict:
    """打开豆包实时语音3.0持久会话。最简session={audio:{output:{voice:'zh_female_vv_jupiter_bigtts'}}}，默认model=1.2.6.1、输入pcm16k/输出pcm_s16le24k。
    可传instructions、tools（function定义）、audio配置；extension顶层支持asr/tts/dialog、热词、联网搜索、唱歌等。
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


@mcp.tool()
def list_speech_capabilities() -> dict:
    """列出豆包语音产品、工具、管理Action、官方链接和接入边界；不联网、不计费。"""
    return {
        "products": {
            "tts": ["text_to_speech", "websocket_text_to_speech", "submit_long_text_speech", "query_long_text_speech", "speech_http_request"],
            "voice": ["clone_voice", "query_voice", "upgrade_voice", "design_voice"],
            "asr": ["speech_to_text", "submit_transcription", "query_transcription", "streaming_speech_to_text"],
            "audio": ["generate_audio", "generate_podcast"],
            "translation": ["translate_text", "interpret_audio"],
            "minutes": ["submit_minutes", "query_minutes"],
            "realtime": ["open_realtime_session", "send_realtime_event", "receive_realtime_events", "close_realtime_session"],
            "management": ["manage_word_table", "speech_console"],
            "legacy": ["legacy_speech_request"],
        },
        "word_table_actions": sorted(management.HOTWORD_ACTIONS | management.CORRECT_ACTIONS),
        "console_action_versions": management.CONSOLE_VERSIONS,
        "legacy_operations": sorted(legacy.OPERATIONS),
        "docs": {**products.DOCS,
                 "index": "https://docs.volcengine.com/docs/DoubaoVoice/list?lang=zh",
                 "realtime": "https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh",
                 "podcast": "https://docs.volcengine.com/docs/DoubaoVoice/PodcastAPI-websocket-v3protocol?lang=zh",
                 "interpretation": "https://docs.volcengine.com/docs/DoubaoVoice/SimultaneousInterpretation20APIAccessDocumentation?lang=zh"},
        "limits": ["Speech SDK端侧离线能力需原生应用集成；MCP提供云API。",
                   "术语词表CRUD官方仅提供控制台；使用支持corpus.glossary_list/table_id/table_name。",
                   "同传官方示例protobuf尚未声明detected_language，不能显式返回该字段。",
                   "历史版本API未等同于当前产品全部通过线上验证；实际服务开通和权限以账号为准。"],
    }


@mcp.tool()
def speech_http_request(product: str, request: dict, resource_id: str | None = None, out_dir: str | None = None) -> dict:
    """高级HTTP参数入口，product=tts/asr_flash/audio；request完全按官方请求体透传，支持SSML、bit_rate、水印、视觉上下文、说话人、词表及新增模型参数。
    tts={req_params:{speaker,text,audio_params:{format:'mp3'},additions:'JSON字符串'}}；asr_flash={audio:{url:'URL'},request:{model_name:'bigmodel'}}；audio={model:'seed-audio-1.0',text_prompt:'描述',audio_config:{format:'mp3'}}。
    返回全部响应（音频base64替换为本地文件路径），保留usage、字幕、URL。服务端校验高级参数，按对应服务计费。端点固定，不接收任意URL。
    """
    return products.raw_http(product, request, target_dir(out_dir), resource_id)


@mcp.tool()
def legacy_speech_request(operation: str, request: dict | None = None, parameters: dict | None = None) -> dict:
    """历史HTTP产品入口。operation=subtitle_submit/query（字幕生成）、alignment_submit/query（字幕打轴）、tts、tts_async_submit/query、tts_emotion_submit/query、asr_submit/query。
    字幕submit request={url:'URL'}，打轴增加audio_text；parameters传language/caption_type等官方query字段，query需id。
    旧TTS/ASR request按官方app/user/audio/request或audio/request结构，cluster须显式指定。需要VOLC_SPEECH_APP_ID和VOLC_SPEECH_ACCESS_TOKEN。
    保留完整响应及官方source链接，不自动轮询；旧版与新版服务开通、鉴权、计费分别处理，不支持任意endpoint。
    """
    return legacy.legacy_call(operation, request, parameters)


def main():
    mcp.run()
