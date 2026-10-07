"""百炼语音合成、语音识别、视频生成，以及本地文件上传到百炼临时存储。只依赖标准库。"""

import base64
import re
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

from .dashscope import InputError, request

TTS_MODELS = {"flash": "qwen3-tts-flash", "instruct": "qwen3-tts-instruct-flash"}
VIDEO_MODELS = {"wan": "wan3.0-video", "wan-fast": "wan3.0-video-prime"}
AUDIO_MIME = {"mp3": "mpeg", "wav": "wav", "m4a": "mp4", "aac": "aac", "flac": "flac", "ogg": "ogg",
              "opus": "opus", "amr": "amr", "webm": "webm"}
TTS_CHUNK = 250  # qwen3-tts 单次上限 512 token，按字符保守切分
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN")


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
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)
    return str(path)


def upload(src, model):
    """把本地文件传到百炼临时存储（48 小时有效），返回 oss:// 地址。请求时要带 X-DashScope-OssResourceResolve。"""
    p = local_file(src, 1024)
    resp, err = request(f"/api/v1/uploads?action=getPolicy&model={model}", timeout=30)
    if err:
        raise InputError(f"获取上传凭证失败：{err}")
    d = resp["data"]
    key = f"{d['upload_dir']}/{p.name}"
    fields = {"OSSAccessKeyId": d["oss_access_key_id"], "Signature": d["signature"], "policy": d["policy"],
              "x-oss-object-acl": d["x_oss_object_acl"], "x-oss-forbid-overwrite": d["x_oss_forbid_overwrite"],
              "key": key, "success_action_status": "200"}
    boundary = uuid.uuid4().hex
    body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                    for k, v in fields.items())
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{p.name}"\r\n'
             f"Content-Type: application/octet-stream\r\n\r\n").encode() + p.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(d["upload_host"], data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=600).close()
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
    with wave.open(str(out), "wb") as w:
        for i, f in enumerate(files):
            with wave.open(str(f), "rb") as r:
                if i == 0:
                    w.setparams(r.getparams())
                w.writeframes(r.readframes(r.getnframes()))


def text_to_speech(o, out_dir, mode="local"):
    model = TTS_MODELS.get(o["model"] or ("instruct" if o["instructions"] else "flash"), o["model"])
    result = {"ok": False, "model": model, "files": [], "chunks": 0, "usage": None, "error": None}
    text = (o["text"] or "").strip()
    if not text:
        result["error"] = "缺少 text"
        return result
    if o["instructions"] and "instruct" not in model:
        result["error"] = "instructions 只有 qwen3-tts-instruct-flash 支持，去掉 model 参数或设 model=\"instruct\""
        return result
    chunks = split_text(text)
    if mode == "url" and len(chunks) > 1:
        result["error"] = f"文本约 {len(text)} 字，需要分 {len(chunks)} 段合成再拼接，url 交付方式下请分段调用（每段 {TTS_CHUNK} 字以内）"
        return result

    urls, chars = [], 0
    for c in chunks:
        inp = {"text": c, "voice": o["voice"]}
        if o["language"]:
            inp["language_type"] = o["language"]
        if o["instructions"]:
            inp["instructions"] = o["instructions"]
            inp["optimize_instructions"] = True
        resp, err = request("/api/v1/services/aigc/multimodal-generation/generation", {"model": model, "input": inp}, 120)
        if not err and resp.get("code"):
            err = f"{resp['code']}: {resp.get('message')}"
        if err:
            result["error"] = err if len(chunks) == 1 else f"第 {len(urls) + 1}/{len(chunks)} 段合成失败：{err}"
            return result
        urls.append(resp["output"]["audio"]["url"])
        chars += (resp.get("usage") or {}).get("characters", 0)
    result.update(chunks=len(chunks), usage={"characters": chars})

    if mode == "url":
        result.update(ok=True, files=urls)
        return result
    try:
        # 单段也重写一遍：接口返回的 wav 头是流式占位长度（0x7fffffff），播放器会算错时长
        parts = [download(u, out_dir / f"part-{i + 1:02d}.wav") for i, u in enumerate(urls)]
        concat_wav(parts, out_dir / "speech.wav")
        for f in parts:
            Path(f).unlink()
        result["files"] = [str(out_dir / "speech.wav")]
    except (urllib.error.URLError, TimeoutError, wave.Error) as e:
        result["error"] = f"下载或拼接音频失败：{e}"
        return result
    result["ok"] = True
    return result


# ---------- 语音识别 ----------

def speech_to_text(o):
    model = o["model"]
    result = {"ok": False, "model": model, "text": "", "language": None, "emotion": None, "usage": None, "error": None}
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
    resp, err = request("/compatible-mode/v1/chat/completions",
                        {"model": model, "messages": messages, "asr_options": asr}, 300)
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
              ("reference_audio", o["reference_audios"]), ("file", [o["file"]] if o["file"] else [])]
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
    return {"model": model, "input": inp, "parameters": params}, oss


def generate_video(o, out_dir, wait, mode="local"):
    model = VIDEO_MODELS.get(o["model"], o["model"])
    result = {"ok": False, "model": model, "task_id": None, "status": None, "files": [], "usage": None, "error": None}
    if not model.startswith("wan3"):
        result["error"] = "目前只支持万相 3.0：model=\"wan\"（wan3.0-video）或 \"wan-fast\"（wan3.0-video-prime）"
        return result
    if not o["prompt"] and not any(o[k] for k in ("first_frame", "reference_images", "reference_videos")):
        result["error"] = "prompt 和参考素材至少要给一个"
        return result
    if o["last_frame"] and not o["first_frame"]:
        result["error"] = "last_frame 要和 first_frame 一起传"
        return result
    try:
        body, oss = build_video_body(o, model)
    except InputError as e:
        result["error"] = str(e)
        return result
    headers = {"X-DashScope-Async": "enable"}
    if oss:
        headers["X-DashScope-OssResourceResolve"] = "enable"
    resp, err = request("/api/v1/services/aigc/video-generation/video-synthesis", body, 60, headers)
    if not err and resp.get("code"):
        err = f"{resp['code']}: {resp.get('message')}"
    if err:
        result["error"] = err
        return result
    result["task_id"] = resp["output"]["task_id"]
    return poll_video(result, out_dir, wait, mode)


def query_video(task_id, out_dir, wait, mode="local"):
    result = {"ok": False, "model": None, "task_id": task_id, "status": None, "files": [], "usage": None, "error": None}
    return poll_video(result, out_dir, wait, mode)


def poll_video(result, out_dir, wait, mode):
    deadline = time.monotonic() + max(wait, 0)
    while True:
        resp, err = request(f"/api/v1/tasks/{result['task_id']}", timeout=30)
        if err:
            result["error"] = err
            return result
        out = resp.get("output") or {}
        result.update(status=out.get("task_status"), usage=resp.get("usage"))
        if result["status"] in TERMINAL or time.monotonic() >= deadline:
            break
        time.sleep(min(10, max(deadline - time.monotonic(), 1)))

    if result["status"] == "SUCCEEDED":
        url = out.get("video_url")
        if mode == "url":
            result["files"] = [url]
        else:
            try:
                result["files"] = [download(url, out_dir / "video.mp4")]
            except (urllib.error.URLError, TimeoutError) as e:
                result["error"] = f"视频已生成但下载失败：{e}，24 小时内可用 query_video 重新获取"
                return result
        result["ok"] = True
    elif result["status"] in ("PENDING", "RUNNING"):
        result["error"] = f"视频还在生成（{result['status']}），稍后用 query_video(task_id=\"{result['task_id']}\") 继续等"
    else:
        result["error"] = f"{out.get('code', result['status'])}: {out.get('message', '任务失败')}"
    return result
