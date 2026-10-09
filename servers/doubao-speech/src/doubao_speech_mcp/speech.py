"""豆包语音 V3 接口：单向流式语音合成（HTTP）、录音文件识别极速版、音频生成。通过共享 HTTP 连接池请求。"""

import base64
import json
import math
import tempfile
import os
import re
import urllib.error
import urllib.request

from . import transport
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
        with transport.urlopen(req, timeout=timeout) as r:
            return r.headers, r.read().decode(), None
    except urllib.error.HTTPError as e:
        return None, None, http_error(e)
    except transport.PartialReadError as e:
        return e.headers, e.partial.decode(errors="replace"), f"响应中途断开：{e}"
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError) as e:
        return None, None, f"请求失败：{e}"


def http_error(e):
    raw = e.read().decode(errors="replace")
    logid = e.headers.get("X-Tt-Logid", "")
    code, msg = e.headers.get("X-Api-Status-Code"), e.headers.get("X-Api-Message")
    try:
        d = json.loads(raw)
        if not isinstance(d, dict):
            raise ValueError("error response 必须是对象")
        d = d.get("header") or d  # 合成接口的错误包在 header 里
        if not isinstance(d, dict):
            raise ValueError("error header 必须是对象")
        code, msg = d.get("code", code), d.get("message", msg)
    except (ValueError, TypeError):
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
        if not isinstance(obj, dict):
            raise InputError("服务返回的 JSON 必须是对象")
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
    if err and not raw:
        raise InputError(err)
    audio, sentences, words = bytearray(), [], 0
    try:
        completed = False
        for d in json_stream(raw):
            completed = completed or d.get("code") == 20000000
            code = d.get("code", 0)
            if code not in OK_CODES:
                raise InputError(f"{code}: {d.get('message')}")
            if d.get("data"):
                audio += base64.b64decode(d["data"], validate=True)
            s = d.get("sentence") or {}
            if not isinstance(s, dict):
                raise InputError("sentence 必须是对象")
            if s.get("words"):
                sentences.append({"text": s.get("text") or "".join(w["word"] for w in s["words"]),
                                  "start": s["words"][0]["startTime"], "end": s["words"][-1]["endTime"]})
            usage = d.get("usage") or {}
            if not isinstance(usage, dict):
                raise InputError("usage 必须是对象")
            billed = usage.get("text_words", 0)
            if isinstance(billed, bool) or not isinstance(billed, (int, float)) or not math.isfinite(billed) or billed < 0:
                raise InputError("usage.text_words 必须为非负有限数")
            words += billed
        if not audio:
            raise InputError("没有返回音频")
        if err:
            raise InputError(err)
        if not completed:
            raise InputError("TTS 响应缺少结束标记，可能已中断")
    except Exception as exc:
        if audio:
            partial = InputError(str(exc) or type(exc).__name__)
            partial.audio = bytes(audio)
            partial.sentences = sentences
            partial.usage = words
            raise partial from exc
        raise
    return bytes(audio), sentences, words


def srt_time(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _atomic_write(path, writer):
    """Publish only complete files; clean up temporary files on any failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_bytes(path, data):
    _atomic_write(path, lambda handle: handle.write(data))


def _atomic_json(path, value):
    _atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def _write_audio(path, data, fmt, sample_rate):
    if fmt != "wav":
        _atomic_bytes(path, data)
        return
    if len(data) % 2:
        raise InputError("服务返回的 PCM 字节数不是 16bit 采样的整数倍")
    def write(handle):
        with wave.open(handle, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(data)
    _atomic_write(path, write)


def _merge_audio(paths, destination, fmt, sample_rate):
    def write(handle):
        if fmt == "wav":
            with wave.open(handle, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                for path in paths:
                    with wave.open(str(path), "rb") as source:
                        output.writeframes(source.readframes(source.getnframes()))
        else:
            for path in paths:
                with path.open("rb") as source:
                    while block := source.read(1024 * 1024):
                        handle.write(block)
    _atomic_write(destination, write)


def _validate_audio_options(o, optional_rate=False):
    if not isinstance(o.get("subtitles"), bool):
        raise InputError("subtitles 必须为 boolean")
    rate = o.get("sample_rate")
    if optional_rate and rate is None:
        return
    if isinstance(rate, bool) or not isinstance(rate, int) or not 8000 <= rate <= 192000:
        raise InputError("sample_rate 必须为 8000..192000 的整数")
    if optional_rate:
        supported = {"wav": {8000, 16000, 24000, 32000, 40000, 44100, 48000},
                     "pcm": {8000, 16000, 24000, 32000, 40000, 44100, 48000},
                     "mp3": {8000, 16000, 24000, 32000, 44100, 48000},
                     "ogg_opus": {48000}}
        if rate not in supported.get(o.get("format"), set()):
            raise InputError("音频生成 sample_rate 不符合该 format 的官方支持范围")
    if not optional_rate and rate not in {8000, 16000, 22050, 24000, 32000, 44100, 48000}:
        raise InputError("不支持该 TTS sample_rate")


def write_srt(sentences, path):
    text = "".join(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text'].strip()}\n\n"
                   for i, s in enumerate(sentences, 1))
    _atomic_bytes(path, text.encode("utf-8"))


def text_to_speech(o, out_dir):
    result = {"ok": False, "resource_id": None, "files": [], "chunk_files": [], "chunks": 0,
              "usage": None, "subtitles": None, "error": None, "partial": False, "manifest": None}
    manifest = None
    manifest_path = None
    try:
        _validate_audio_options(o)
        resource = o["resource_id"] or tts_resource(o["voice"])
        result["resource_id"] = resource
        text = (o["text"] or "").strip()
        fmt = o["format"]
        if not text:
            raise InputError("缺少 text")
        if fmt not in ("mp3", "wav"):
            raise InputError("format 只能是 mp3 或 wav")
        chunks = split_text(text)
        if not chunks:
            raise InputError("text 没有可合成内容")
        if o["subtitles"] and fmt == "mp3" and len(chunks) > 1:
            raise InputError(f"文本需要分 {len(chunks)} 段合成，分段拼接时只有 wav 能算准字幕时间，请设 format=\"wav\"")
        out_dir = Path(out_dir)
        prefix = f"speech-{uuid.uuid4().hex}"
        manifest_path = out_dir / f"{prefix}.json"
        manifest = {"status": "running", "request_options": {key: value for key, value in o.items() if key != "text"},
                    "resource_id": resource, "format": fmt,
                    "sample_rate": o["sample_rate"], "completed_chunks": [], "remaining_input": chunks,
                    "usage": {"text_words": 0}, "error": None}
        _atomic_json(manifest_path, manifest)  # Verify delivery storage before a paid call.
        result["manifest"] = str(manifest_path)
        sentences, offset = [], 0.0
        paths = []
        current = None
        for index, chunk in enumerate(chunks):
            current = {"index": index + 1, "text": chunk, "status": "submitted_outcome_unknown"}
            manifest["incomplete_chunk"] = {**current, "automatic_retry_safe": False}
            _atomic_json(manifest_path, manifest)  # Persist ambiguity BEFORE submitting this paid chunk.
            data, sents, billed = synth_chunk(chunk, o, resource, "pcm" if fmt == "wav" else "mp3")
            current.update(status="synthesized_not_saved", usage={"text_words": billed})
            manifest["usage"]["text_words"] += billed
            result["usage"] = dict(manifest["usage"])
            result["partial"] = True
            path = out_dir / f"{prefix}-chunk-{index + 1:04d}.{fmt}"
            _write_audio(path, data, fmt, o["sample_rate"])
            paths.append(path)
            result["chunk_files"].append(str(path))
            result["files"].append(str(path))
            result["chunks"] += 1
            shifted = [{**s, "start": s["start"] + offset, "end": s["end"] + offset} for s in sents]
            sentences.extend(shifted)
            if fmt == "wav":
                offset += len(data) / (2 * o["sample_rate"])
            manifest["completed_chunks"].append({"index": index + 1, "text": chunk, "file": str(path),
                                                  "audio_bytes": len(data), "usage": {"text_words": billed},
                                                  "subtitles": shifted})
            manifest["remaining_input"] = chunks[index + 1:]
            manifest.pop("incomplete_chunk", None)
            _atomic_json(manifest_path, manifest)
            current = None
        if len(paths) == 1:
            final_path = paths[0]
        else:
            final_path = out_dir / f"{prefix}.{fmt}"
            _merge_audio(paths, final_path, fmt, o["sample_rate"])
        final_files = [str(final_path)]
        result["files"] = list(final_files)
        if o["subtitles"]:
            subtitle_path = out_dir / f"{prefix}.srt"
            write_srt(sentences, subtitle_path)
            final_files.append(str(subtitle_path))
            result["files"] = list(final_files)
            result["subtitles"] = sentences
        manifest.update(status="complete", files=final_files)
        _atomic_json(manifest_path, manifest)
        result.update(ok=True, partial=False, files=final_files)
    except Exception as exc:
        result["error"] = str(exc) or type(exc).__name__
        if manifest is not None and result["manifest"]:
            if current is not None:
                manifest["incomplete_chunk"] = current
                manifest["incomplete_chunk"]["automatic_retry_safe"] = False
            if getattr(exc, "audio", None):
                result["partial"] = True
                manifest["usage"]["text_words"] += exc.usage
                result["usage"] = dict(manifest["usage"])
                incomplete_path = out_dir / f"{prefix}-incomplete-{current['index']:04d}.{fmt}"
                try:
                    _write_audio(incomplete_path, exc.audio, fmt, o["sample_rate"])
                    result["files"].append(str(incomplete_path))
                    manifest["incomplete_chunk"].update(status="partial_audio", file=str(incomplete_path),
                                                         audio_bytes=len(exc.audio), usage={"text_words": exc.usage},
                                                         subtitles=exc.sentences)
                except Exception as storage_error:
                    result["artifact_error"] = str(storage_error)
            manifest.update(status="partial" if result["partial"] else "failed", error=result["error"])
            try:
                _atomic_json(manifest_path, manifest)
            except Exception as storage_error:
                result["manifest_error"] = str(storage_error)
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
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise InputError("服务返回的 JSON 必须是对象")
        if not isinstance(body.get("audio_info") or {}, dict) or not isinstance(body.get("result") or {}, dict):
            raise InputError("audio_info / result 必须是对象")
    except (ValueError, TypeError) as exc:
        result["error"] = f"无效识别响应：{exc}"
        return result
    result["duration_ms"] = (body.get("audio_info") or {}).get("duration")
    if status == "20000003":  # 静音音频
        result["ok"] = True
        return result
    if status != "20000000":
        result["error"] = f"{status}: {headers.get('X-Api-Message')}（logid {headers.get('X-Tt-Logid', '')}）"
        return result
    r = body.get("result") or {}
    try:
        if not isinstance(r.get("text", ""), str):
            raise InputError("result.text 必须为字符串")
        if o["utterances"]:
            result["utterances"] = [{"start_ms": u.get("start_time"), "end_ms": u.get("end_time"), "text": u.get("text"),
                                     "speaker": (u.get("additions") or {}).get("speaker")}
                                    for u in r.get("utterances") or []]
        result.update(ok=True, text=r.get("text") or "")
    except (ValueError, TypeError, AttributeError) as exc:
        result["error"] = f"无效识别响应：{exc}"
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
    try:
        _validate_audio_options(o, optional_rate=True)
    except InputError as exc:
        result["error"] = str(exc)
        return result
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
    elif fmt not in ("mp3", "wav", "pcm", "ogg_opus"):
        err = "format 只能是 mp3、wav、pcm 或 ogg_opus"
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
    try:
        d = json.loads(raw)
        if not isinstance(d, dict):
            raise InputError("服务返回的 JSON 必须是对象")
        if d.get("code", 0) not in OK_CODES:
            raise InputError(f"{d['code']}: {d.get('message')}")
        if not d.get("audio"):
            raise InputError("没有返回音频")
        data = base64.b64decode(d["audio"], validate=True)
        if not data:
            raise InputError("返回音频为空")
        path = Path(out_dir) / f"audio-{uuid.uuid4().hex}.{'ogg' if fmt == 'ogg_opus' else fmt}"
        _atomic_bytes(path, data)
        result.update(ok=True, files=[str(path)], url=d.get("url"), subtitle=d.get("subtitle"),
                      duration=d.get("original_duration", d.get("duration")))
    except Exception as exc:
        result["error"] = str(exc) or type(exc).__name__
    return result
