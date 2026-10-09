"""豆包语音 V3 接口：单向流式语音合成（HTTP）、录音文件识别极速版、音频生成。只依赖标准库。"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

HOST = os.environ.get("VOLC_SPEECH_BASE_URL", "https://openspeech.bytedance.com").rstrip("/")
TTS_CHUNK = 1000  # 接口未写单次上限，过长会合成超时，按字符保守切分
ASR_FORMATS = {"wav", "mp3", "ogg", "spx", "amr", "aac", "m4a"}
IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
OK_CODES = (0, 20000000)


class InputError(ValueError):
    pass


def is_remote(src):
    return src.startswith(("http://", "https://"))


def local_file(src, limit_mb):
    p = Path(src).expanduser()
    if not p.is_file():
        raise InputError(f"文件不存在：{src}")
    if p.stat().st_size > limit_mb * 1024 * 1024:
        raise InputError(f"文件超过 {limit_mb}MB：{p.name}")
    return p


def b64(p):
    return base64.b64encode(p.read_bytes()).decode()


def post(path, body, resource=None, headers=None, timeout=300):
    """返回 (status 头, 响应原文, error)。"""
    key = os.environ.get("VOLC_SPEECH_API_KEY")
    if not key:
        return None, None, "未设置环境变量 VOLC_SPEECH_API_KEY（豆包语音控制台 → API Key 管理）"
    h = {"Content-Type": "application/json", "X-Api-Key": key, "X-Api-Request-Id": str(uuid.uuid4()),
         **(headers or {})}
    if resource:
        h["X-Api-Resource-Id"] = resource
    req = urllib.request.Request(HOST + path, data=json.dumps(body, ensure_ascii=False).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.headers, r.read().decode(), None
    except urllib.error.HTTPError as e:
        return None, None, http_error(e)
    except (urllib.error.URLError, TimeoutError) as e:
        return None, None, f"请求失败：{e}"


def http_error(e):
    raw = e.read().decode(errors="replace")
    logid = e.headers.get("X-Tt-Logid", "")
    code, msg = e.headers.get("X-Api-Status-Code"), e.headers.get("X-Api-Message")
    try:
        d = json.loads(raw)
        d = d.get("header") or d  # 合成接口的错误包在 header 里
        code, msg = d.get("code", code), d.get("message", msg)
    except json.JSONDecodeError:
        msg = msg or raw[:500]
    return f"HTTP {e.code} {code or ''}: {msg}（logid {logid}）"


def json_stream(raw):
    """流式接口返回多个首尾相接的 JSON 对象，有无换行分隔都能解析。"""
    dec, i, n = json.JSONDecoder(), 0, len(raw)
    while i < n:
        while i < n and raw[i].isspace():
            i += 1
        if i >= n:
            break
        obj, i = dec.raw_decode(raw, i)
        yield obj


# ---------- 语音合成 ----------

def tts_resource(speaker):
    if speaker.startswith("S_"):
        return "seed-icl-2.0"
    if speaker.endswith(("_moon_bigtts", "_mars_bigtts")) or speaker.startswith("BV"):
        return "seed-tts-1.0"
    return "seed-tts-2.0"


def split_text(text, limit=TTS_CHUNK):
    """按句末标点切成不超过 limit 字的段，单句过长时硬切。"""
    parts, buf = [], ""
    for sent in re.findall(r"[^。！？!?；;\n]+[。！？!?；;\n]*", text):
        while len(sent) > limit:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(sent[:limit])
            sent = sent[limit:]
        if len(buf) + len(sent) > limit:
            parts.append(buf)
            buf = ""
        buf += sent
    if buf.strip():
        parts.append(buf)
    return [p for p in parts if p.strip()]


def build_tts_body(text, o, fmt):
    audio = {"format": fmt, "sample_rate": o["sample_rate"]}
    if o["speech_rate"]:
        audio["speech_rate"] = o["speech_rate"]
    if o["loudness_rate"]:
        audio["loudness_rate"] = o["loudness_rate"]
    if o["subtitles"]:
        audio["enable_subtitle"] = True
    # 默认去掉 Markdown 符号：模型写的文本常带 **、#，不过滤会被念出来
    additions = {"disable_markdown_filter": True}
    if o["instructions"]:
        additions["context_texts"] = [o["instructions"]]
    if o["dialect"]:
        additions["explicit_dialect"] = o["dialect"]
    if o["language"]:
        additions["explicit_language"] = o["language"]
    if o["pitch"]:
        additions["post_process"] = {"pitch": o["pitch"]}
    if o["pronunciations"]:
        additions["pronunciation_dict"] = {"tone": o["pronunciations"]}
    params = {"text": text, "speaker": o["voice"], "audio_params": audio,
              "additions": json.dumps(additions, ensure_ascii=False)}
    if o["model"]:
        params["model"] = o["model"]
    return {"req_params": params}


def synth_chunk(text, o, resource, fmt):
    """返回 (音频字节, 句子列表, 计费字数)。"""
    headers = {"X-Control-Require-Usage-Tokens-Return": "*"}
    _, raw, err = post("/api/v3/tts/unidirectional", build_tts_body(text, o, fmt), resource, headers, 300)
    if err:
        raise InputError(err)
    audio, sentences, words = bytearray(), [], 0
    for d in json_stream(raw):
        code = d.get("code", 0)
        if code not in OK_CODES:
            raise InputError(f"{code}: {d.get('message')}")
        if d.get("data"):
            audio += base64.b64decode(d["data"])
        s = d.get("sentence") or {}
        if s.get("words"):
            sentences.append({"text": s.get("text") or "".join(w["word"] for w in s["words"]),
                              "start": s["words"][0]["startTime"], "end": s["words"][-1]["endTime"]})
        words += (d.get("usage") or {}).get("text_words", 0)
    if not audio:
        raise InputError("没有返回音频")
    return bytes(audio), sentences, words


def srt_time(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(sentences, path):
    path.write_text("".join(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text'].strip()}\n\n"
                            for i, s in enumerate(sentences, 1)), encoding="utf-8")


def text_to_speech(o, out_dir):
    resource = o["resource_id"] or tts_resource(o["voice"])
    result = {"ok": False, "resource_id": resource, "files": [], "chunks": 0, "usage": None,
              "subtitles": None, "error": None}
    text = (o["text"] or "").strip()
    fmt = o["format"]
    if not text:
        result["error"] = "缺少 text"
        return result
    if fmt not in ("mp3", "wav"):
        result["error"] = "format 只能是 mp3 或 wav"
        return result
    chunks = split_text(text)
    if o["subtitles"] and fmt == "mp3" and len(chunks) > 1:
        result["error"] = f"文本需要分 {len(chunks)} 段合成，分段拼接时只有 wav 能算准字幕时间，请设 format=\"wav\""
        return result

    audio, sentences, words, offset = bytearray(), [], 0, 0.0
    for i, c in enumerate(chunks):
        try:
            data, sents, n = synth_chunk(c, o, resource, "pcm" if fmt == "wav" else "mp3")
        except InputError as e:
            result["error"] = str(e) if len(chunks) == 1 else f"第 {i + 1}/{len(chunks)} 段合成失败：{e}"
            return result
        audio += data
        sentences += [{**s, "start": s["start"] + offset, "end": s["end"] + offset} for s in sents]
        words += n
        if fmt == "wav":
            offset += len(data) / (2 * o["sample_rate"])  # 16bit 单声道

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"speech.{fmt}"
    if fmt == "wav":
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(o["sample_rate"])
            w.writeframes(bytes(audio))
    else:
        path.write_bytes(bytes(audio))
    result["files"].append(str(path))
    if o["subtitles"]:
        write_srt(sentences, out_dir / "speech.srt")
        result["files"].append(str(out_dir / "speech.srt"))
        result["subtitles"] = sentences
    result.update(ok=True, chunks=len(chunks), usage={"text_words": words})
    return result


# ---------- 语音识别 ----------

def asr_audio(src, fmt, language):
    if is_remote(src):
        audio = {"url": src}
        ext = Path(src.split("?")[0]).suffix.lower().lstrip(".")
    else:
        p = local_file(src, 100)
        audio = {"data": b64(p)}
        ext = p.suffix.lower().lstrip(".")
    fmt = (fmt or {"opus": "ogg"}.get(ext, ext)).lower()
    if fmt not in ASR_FORMATS:
        raise InputError(f"无法确定音频格式（{ext or '无扩展名'}），用 format 指定：{', '.join(sorted(ASR_FORMATS))}")
    audio["format"] = fmt
    if fmt == "ogg":
        audio["codec"] = "opus"
    if language:
        audio["language"] = language
    return audio


def speech_to_text(o):
    result = {"ok": False, "text": "", "duration_ms": None, "utterances": None, "error": None}
    try:
        audio = asr_audio(o["audio"], o["format"], o["language"])
    except InputError as e:
        result["error"] = str(e)
        return result
    req = {"model_name": "bigmodel", "enable_itn": o["itn"], "enable_punc": o["punc"], "enable_ddc": o["ddc"],
           "show_utterances": o["utterances"]}
    corpus = {}
    if o["hotwords"] or o["context"]:
        ctx = {}
        if o["hotwords"]:
            ctx["hotwords"] = [{"word": w} for w in o["hotwords"]]
        if o["context"]:
            ctx.update(context_type="dialog_ctx", context_data=[{"text": o["context"]}])
        corpus["context"] = json.dumps(ctx, ensure_ascii=False)
    if corpus:
        req["corpus"] = corpus
    headers, raw, err = post("/api/v3/auc/bigmodel/recognize/flash", {"audio": audio, "request": req},
                             "volc.bigasr.auc_turbo", {"X-Api-Sequence": "-1"}, 600)
    if err:
        result["error"] = err
        return result
    status = headers.get("X-Api-Status-Code", "20000000")
    body = json.loads(raw) if raw.strip() else {}
    result["duration_ms"] = (body.get("audio_info") or {}).get("duration")
    if status == "20000003":  # 静音音频
        result["ok"] = True
        return result
    if status != "20000000":
        result["error"] = f"{status}: {headers.get('X-Api-Message')}（logid {headers.get('X-Tt-Logid', '')}）"
        return result
    r = body.get("result") or {}
    result.update(ok=True, text=r.get("text") or "")
    if o["utterances"]:
        result["utterances"] = [{"start_ms": u.get("start_time"), "end_ms": u.get("end_time"), "text": u.get("text"),
                                 "speaker": (u.get("additions") or {}).get("speaker")}
                                for u in r.get("utterances") or []]
    return result


# ---------- 音频生成 ----------

def build_audio_refs(o):
    refs = []
    if o["speaker"]:
        refs.append({"speaker": o["speaker"]})
    for s in o["reference_audios"]:
        refs.append({"audio_url": s} if is_remote(s) else {"audio_data": b64(local_file(s, 10))})
    if o["reference_image"]:
        s = o["reference_image"]
        if is_remote(s):
            refs.append({"image_url": s})
        else:
            p = local_file(s, 10)
            if p.suffix.lower().lstrip(".") not in IMAGE_EXT:
                raise InputError(f"参考图片只支持 jpeg / png / webp：{p.name}")
            refs.append({"image_data": b64(p)})
    return refs


def generate_audio(o, out_dir):
    result = {"ok": False, "model": o["model"], "files": [], "url": None, "duration": None, "subtitle": None,
              "error": None}
    prompt = (o["prompt"] or "").strip()
    fmt = o["format"]
    err = None
    if not prompt:
        err = "缺少 prompt"
    elif len(prompt) > 3000:
        err = f"prompt 最多 3000 字，当前 {len(prompt)} 字"
    elif len(o["reference_audios"]) > 3:
        err = "最多 3 段参考音频"
    elif o["reference_image"] and (o["reference_audios"] or o["speaker"]):
        err = "参考图片不能和参考音频或 speaker 同时使用"
    elif fmt not in ("mp3", "wav", "ogg_opus"):
        err = "format 只能是 mp3、wav 或 ogg_opus"
    if err:
        result["error"] = err
        return result
    try:
        refs = build_audio_refs(o)
    except InputError as e:
        result["error"] = str(e)
        return result
    config = {"format": fmt}
    for k in ("sample_rate", "speech_rate", "loudness_rate", "pitch_rate"):
        if o[k]:
            config[k] = o[k]
    if o["subtitles"]:
        config["enable_subtitle"] = True
    body = {"model": o["model"], "text_prompt": prompt, "audio_config": config}
    if refs:
        body["references"] = refs
    _, raw, err = post("/api/v3/tts/create", body, timeout=300)
    if err:
        result["error"] = err
        return result
    d = json.loads(raw)
    if d.get("code", 0) not in OK_CODES:
        result["error"] = f"{d['code']}: {d.get('message')}"
        return result
    if not d.get("audio"):
        result["error"] = "没有返回音频"
        return result
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"audio.{'ogg' if fmt == 'ogg_opus' else fmt}"
    path.write_bytes(base64.b64decode(d["audio"]))
    result.update(ok=True, files=[str(path)], url=d.get("url"), subtitle=d.get("subtitle"),
                  duration=d.get("original_duration", d.get("duration")))
    return result
