"""百炼语音合成、语音识别、视频生成，以及本地文件上传到百炼临时存储。通过共享 HTTP 连接池请求。"""

import base64
import re
import time
import urllib.error
import urllib.request

from . import transport
from .mcp_runtime import merge_parameters
import uuid
import wave
from pathlib import Path

from .dashscope import InputError, request
from .jobs import download as atomic_download

TTS_MODELS = {"flash": "qwen3-tts-flash", "instruct": "qwen3-tts-instruct-flash"}
VIDEO_MODELS = {"wan": "wan3.0-video", "wan-fast": "wan3.0-video-prime"}
AUDIO_MIME = {"mp3": "mpeg", "wav": "wav", "m4a": "mp4", "aac": "aac", "flac": "flac", "ogg": "ogg",
              "opus": "opus", "amr": "amr", "webm": "webm"}
TTS_CHUNK = 250  # qwen3-tts 单次上限 512 token，按字符保守切分


def is_remote(src):
    return src.startswith(("http://", "https://", "oss://", "data:"))


def local_file(src, limit_mb):
    p = Path(src).expanduser()
    if not p.is_file():
        raise InputError(f"文件不存在：{src}")
    if p.stat().st_size > limit_mb * 1024 * 1024:
        raise InputError(f"文件超过 {limit_mb}MB：{p.name}")
    return p


def download(url, path):
    return atomic_download(url, path)


def upload(src, model):
    """把本地文件传到百炼临时存储（48 小时有效），返回 oss:// 地址。请求时要带 X-DashScope-OssResourceResolve。"""
    p = local_file(src, 1024)
    resp, err = request(f"/api/v1/uploads?action=getPolicy&model={model}", timeout=30)
    if err:
        raise InputError(f"获取上传凭证失败：{err}")
    d = resp["data"]
    key = f"{d['upload_dir']}/{uuid.uuid4().hex}-{p.name}"
    fields = {"OSSAccessKeyId": d["oss_access_key_id"], "Signature": d["signature"], "policy": d["policy"],
              "x-oss-object-acl": d["x_oss_object_acl"], "x-oss-forbid-overwrite": d["x_oss_forbid_overwrite"],
              "key": key, "success_action_status": "200"}
    boundary = uuid.uuid4().hex
    body = transport.multipart(fields, p, boundary)
    req = urllib.request.Request(d["upload_host"], data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "Content-Length": str(transport.multipart_length(fields, p, boundary))})
    try:
        transport.urlopen(req, timeout=600).close()
    except urllib.error.HTTPError as e:
        raise InputError(f"上传 {p.name} 失败：HTTP {e.code} {e.read()[:300]!r}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise InputError(f"上传 {p.name} 失败：{e}")
    return f"oss://{key}"


# ---------- 语音合成 ----------

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


def concat_wav(files, out):
    expected = None
    with wave.open(str(out), "wb") as w:
        for i, f in enumerate(files):
            with wave.open(str(f), "rb") as r:
                if i == 0:
                    w.setparams(r.getparams())
                    expected = (r.getnchannels(), r.getsampwidth(), r.getframerate(), r.getcomptype())
                elif (r.getnchannels(), r.getsampwidth(), r.getframerate(), r.getcomptype()) != expected:
                    raise ValueError("分段WAV采样参数不一致，不能直接拼接")
                frames = r.readframes(r.getnframes())
                if not frames:
                    raise ValueError("分段WAV没有音频帧")
                w.writeframes(frames)


def text_to_speech(o, out_dir, mode="local"):
    from .products import STORE
    model = TTS_MODELS.get(o["model"] or ("instruct" if o["instructions"] else "flash"), o["model"])
    text = (o["text"] or "").strip()
    if not text:
        return {"ok": False, "error": "缺少text"}
    if not model or not model.startswith("qwen3-tts-") or "realtime" in model:
        return {"ok": False, "error": "此工具仅支持非实时qwen3-tts模型，其他模型使用不同接口"}
    if o["instructions"] and "instruct" not in model:
        return {"ok": False, "error": "instructions需qwen3-tts-instruct-flash"}
    chunks = split_text(text)
    if mode == "url" and len(chunks) > 1:
        return {"ok": False, "error": "url交付方式请分段调用，每段250字符以内"}
    resume = {"options": {**o, "model": model},
              "chunks": [{"text": text, "state": "unsubmitted", "usage": 0} for text in chunks]}
    job = STORE.create("tts", model, out_dir, mode, resume=resume,
                       summary={"voice": o["voice"], "chunks": len(chunks)})
    with STORE.processing(job):
        job["state"] = "partial"
        STORE.save(job)
        return resume_tts(job)


def resume_tts(job):
    """Continue only known, not-yet-submitted chunks; ambiguous requests are never retried."""
    from .products import STORE
    import tempfile
    plan = job["resume"]
    opts = plan["options"]
    final = job.get("result", {}).get("speech_file")
    if job["state"] == "delivered" and final:
        from .jobs import fingerprint
        if Path(final).is_file() and fingerprint(final) == job["result"].get("speech_integrity"):
            return STORE.result(job)
    for i, chunk in enumerate(plan["chunks"]):
        if chunk["state"] == "unknown":
            job.update(state="unknown", error=f"第{i + 1}段请求状态未知，禁止自动重复合成；已完成部分保留")
            STORE.save(job)
            return STORE.result(job)
        if chunk["state"] == "unsubmitted":
            inp = {"text": chunk["text"], "voice": opts["voice"]}
            if opts["language"]:
                inp["language_type"] = opts["language"]
            if opts["instructions"]:
                inp.update(instructions=opts["instructions"], optimize_instructions=True)
            body = {"model": job["model"], "input": inp}
            if opts.get("parameters"):
                body["parameters"] = dict(opts["parameters"])
            chunk["state"] = "unknown"
            STORE.save(job)  # Crash during request is ambiguous, not safe to resubmit.
            response, error = request("/api/v1/services/aigc/multimodal-generation/generation", body, 120)
            if not error and response.get("code"):
                error = f"{response['code']}: {response.get('message')}"
            if error:
                # Definitive rejection can be retried only by explicit recover_job.
                definitive = error.startswith(("HTTP 4", "未设置")) or bool(response and response.get("code"))
                chunk["state"] = "unsubmitted" if definitive else "unknown"
                job.update(state="partial" if definitive else "unknown", error=f"第{i + 1}段：{error}")
                STORE.save(job)
                return STORE.result(job)
            url = ((response.get("output") or {}).get("audio") or {}).get("url")
            if not url:
                job.update(state="unknown", error="合成响应缺少audio.url，不能自动重新合成")
                STORE.save(job)
                return STORE.result(job)
            chunk.update(state="generated", url=url, usage=(response.get("usage") or {}).get("characters", 0))
            job["request_id"] = response.get("request_id")
            chunk["request_id"] = response.get("request_id")
            STORE.save(job)
        STORE.add(job, f"part-{i + 1:02d}.wav", url=chunk["url"])
        job["usage"] = {"characters": sum(c["usage"] for c in plan["chunks"])}
        delivered = STORE.deliver(job)
        if delivered["job_state"] == "download_failed":
            job["result"]["chunks"] = sum(c["state"] == "generated" for c in plan["chunks"])
            STORE.save(job)
            return STORE.result(job)
        # Still partial until EVERY generation and the final merge have finished.
        job["state"] = "partial"
        STORE.save(job)
    job["result"]["chunks"] = len(plan["chunks"])
    if job["mode"] == "url":
        job.update(state="delivered", error=None)
        STORE.save(job)
        return STORE.result(job)
    target = Path(job["out_dir"]) / "speech.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".speech-", suffix=".wav", dir=target.parent)
    import os
    os.close(fd)
    try:
        parts = [str(target.parent / f"part-{i + 1:02d}.wav") for i in range(len(plan["chunks"]))]
        concat_wav(parts, tmp)
        os.replace(tmp, target)
        from .jobs import fingerprint
        job["result"]["speech_file"] = str(target)
        job["result"]["speech_integrity"] = fingerprint(target)
        with wave.open(str(target), "rb") as audio:
            job["result"]["duration"] = audio.getnframes() / audio.getframerate()
            job["result"]["sample_rate"] = audio.getframerate()
        job.update(state="delivered", error=None)
        STORE.save(job)
        result = STORE.result(job)
        result["files"] = [str(target)]
        return result
    except (OSError, ValueError, wave.Error) as exc:
        job.update(state="download_failed", error=f"拼接音频失败：{exc}")
        STORE.save(job)
        return STORE.result(job)
    finally:
        Path(tmp).unlink(missing_ok=True)


# ---------- 语音识别 ----------

def speech_to_text(o):
    model = o["model"]
    result = {"ok": False, "model": model, "text": "", "language": None, "emotion": None, "usage": None, "error": None}
    if not model.startswith("qwen3-asr-flash") or "realtime" in model or "filetrans" in model:
        result["error"] = "此工具仅支持qwen3-asr-flash及非实时快照；其他ASR模型采用不同协议"
        return result
    src = o["audio"]
    try:
        if is_remote(src):
            data = src
        else:
            p = local_file(src, 10)
            ext = p.suffix.lower().lstrip(".")
            if ext not in AUDIO_MIME:
                raise InputError(f"不支持的音频格式：{p.name}（支持 {', '.join(AUDIO_MIME)}）")
            data = f"data:audio/{AUDIO_MIME[ext]};base64," + base64.b64encode(p.read_bytes()).decode()
    except InputError as e:
        result["error"] = str(e)
        return result
    messages = []
    if o["context"]:
        messages.append({"role": "system", "content": [{"type": "text", "text": o["context"]}]})
    messages.append({"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": data}}]})
    asr = {"enable_itn": o["itn"]}
    if o["language"]:
        asr["language"] = o["language"]
    body = {"model": model, "messages": messages, "asr_options": asr}
    extra = o.get("parameters") or {}
    if set(extra) & {"model", "messages", "stream"}:
        result["error"] = "parameters 不能覆盖 model/messages/stream"
        return result
    merge_parameters(body, extra)
    resp, err = request("/compatible-mode/v1/chat/completions", body, 300)
    if err:
        result["error"] = err
        return result
    msg = resp["choices"][0]["message"]
    info = next((a for a in msg.get("annotations") or [] if a.get("type") == "audio_info"), {})
    result.update(ok=True, text=msg.get("content") or "", language=info.get("language"),
                  emotion=info.get("emotion"), usage=resp.get("usage"))
    return result


# ---------- 视频生成 ----------

def build_video_body(o, model):
    media, oss = [], False
    groups = [("first_frame", [o["first_frame"]] if o["first_frame"] else []),
              ("last_frame", [o["last_frame"]] if o["last_frame"] else []),
              ("reference_image", o["reference_images"]), ("reference_video", o["reference_videos"]),
              ("reference_audio", o["reference_audios"]), ("file", [o["file"]] if o["file"] else []),
              ("link", [o.get("link")] if o.get("link") else [])]
    for kind, srcs in groups:
        for s in srcs:
            if not is_remote(s):
                s, oss = upload(s, model), True
            elif s.startswith("oss://"):
                oss = True
            media.append({"type": kind, "url": s})
    inp = {}
    if o["prompt"]:
        inp["prompt"] = o["prompt"]
    if media:
        inp["media"] = media
    params = {"resolution": o["resolution"], "ratio": o["ratio"], "audio": o["audio"], "watermark": o["watermark"]}
    for k in ("duration", "prompt_extend", "seed"):
        if o[k] is not None:
            params[k] = o[k]
    merge_parameters(params, o.get("parameters"))
    return {"model": model, "input": inp, "parameters": params}, oss


def generate_video(o, out_dir, wait, mode="local"):
    model = VIDEO_MODELS.get(o["model"], o["model"])
    result = {"ok": False, "model": model, "task_id": None, "status": None, "files": [], "usage": None, "error": None}
    if model not in VIDEO_MODELS.values():
        result["error"] = "目前只支持万相 3.0：model=\"wan\"（wan3.0-video）或 \"wan-fast\"（wan3.0-video-prime）"
        return result
    if not o["prompt"] and not any(o.get(k) for k in ("first_frame", "reference_images", "reference_videos", "reference_audios", "file", "link")):
        result["error"] = "prompt 和参考素材至少要给一个"
        return result
    if o["last_frame"] and not o["first_frame"]:
        result["error"] = "last_frame 要和 first_frame 一起传"
        return result
    references = any(o.get(k) for k in ("reference_images", "reference_videos", "reference_audios", "file", "link"))
    if (o["first_frame"] or o["last_frame"]) and references:
        return {**result, "error": "首尾帧不能与参考素材、file或link混用"}
    if o["file"] and o.get("link"):
        return {**result, "error": "file与link不能同时输入"}
    if o.get("link") and not o["link"].startswith(("http://", "https://")):
        return {**result, "error": "link必须为公开HTTP/HTTPS网页"}
    if (o["file"] or o.get("link")) and o["prompt_extend"] is False:
        return {**result, "error": "file/link参考要求prompt_extend=true"}
    if o["resolution"] not in ("480P", "720P", "1080P") or o["ratio"] not in ("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"):
        return {**result, "error": "无效视频resolution或ratio"}
    if o["duration"] is not None and o["duration"] != -1 and not 2 <= o["duration"] <= 30:
        return {**result, "error": "duration必须为-1或2–30秒"}
    if o["seed"] is not None and o["seed"] != -1 and not 0 <= o["seed"] <= 2147483647:
        return {**result, "error": "seed必须为-1或0–2147483647"}
    if len(o["reference_images"]) > 10 or len(o["reference_videos"]) > 5 or len(o["reference_audios"]) > 5:
        return {**result, "error": "参考图片最多10张，视频/音频分别最多5段"}
    try:
        body, oss = build_video_body(o, model)
    except InputError as e:
        result["error"] = str(e)
        return result
    from .products import submit_video
    return submit_video(body, out_dir, wait, mode, oss=oss)


def poll_job(job, wait=0):
    from .products import STORE
    from urllib.parse import quote
    deadline = time.monotonic() + max(0, min(wait, 90))
    while True:
        response, error = request("/api/v1/tasks/" + quote(job["task_id"], safe=""),
                                  timeout=max(1, min(30, deadline - time.monotonic())) if wait else 30)
        if error:
            job["error"] = error
            STORE.save(job)
            return {**STORE.result(job), "ok": False, "query_failed": True}
        out = response.get("output") or {}
        status = out.get("task_status")
        job.update(usage=response.get("usage"), request_id=response.get("request_id"), error=None)
        job["result"] = {"status": status, "response": response}
        if status == "SUCCEEDED":
            url = out.get("video_url") or (out.get("results") or {}).get("video_url")
            if not url:
                job.update(state="unknown", error="任务成功但缺少video_url")
                STORE.save(job)
                return STORE.result(job)
            STORE.add(job, "video.mp4", url=url)
            return STORE.deliver(job)
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            job.update(state="failed" if status != "UNKNOWN" else "unknown",
                       error=f"{out.get('code', status)}: {out.get('message', '任务失败或未知')}")
            STORE.save(job)
            return STORE.result(job)
        job["state"] = "running" if status in ("PENDING", "RUNNING") else "unknown"
        STORE.save(job)
        if time.monotonic() >= deadline:
            return STORE.result(job)
        transport.sleep(min(5, max(0, deadline - time.monotonic())))
