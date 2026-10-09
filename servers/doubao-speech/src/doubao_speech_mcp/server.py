"""stdio MCP server：语音合成、语音识别、音频生成。

环境变量：VOLC_SPEECH_API_KEY（必需）、DOUBAO_SPEECH_OUT_DIR（默认 ~/Downloads/doubao-speech）、
VOLC_SPEECH_BASE_URL（可选）。
"""

import os
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import speech

OUT_ROOT = Path(os.environ.get("DOUBAO_SPEECH_OUT_DIR", "~/Downloads/doubao-speech")).expanduser()

mcp = MCPServer("doubao-speech")


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


def main():
    mcp.run()
