"""Additional Ark APIs: Seedance, Chat/Responses, text and multimodal embedding."""
import copy
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from . import transport
from pathlib import Path

from . import ark
from .jobs import Store

STORE = Store("ARK_JOB_DIR", "~/.local/share/volcengine-ark-mcp/jobs")
VIDEO_MODELS = {"seedance": "doubao-seedance-2-5-260628", "seedance-2": "doubao-seedance-2-0-260128",
                "seedance-fast": "doubao-seedance-2-0-fast-260128", "seedance-mini": "doubao-seedance-2-0-mini-260615"}
CHAT_MODELS = {"pro": "doubao-seed-2-1-pro-260628"}
DOCS = {
    "video": "https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh",
    "video_query": "https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh",
    "chat": "https://docs.volcengine.com/docs/ark/chat-api?lang=zh",
    "responses": "https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh",
    "search": "https://docs.volcengine.com/docs/ark/web-search?lang=zh",
    "embedding": "https://docs.volcengine.com/docs/ark/vectorization?lang=zh",
    "multimodal_embedding": "https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh",
}


def request(path, body=None, timeout=60):
    key = os.environ.get("ARK_API_KEY")
    if not key:
        return None, "未设置环境变量 ARK_API_KEY"
    req = urllib.request.Request(ark.BASE_URL.rstrip("/") + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with transport.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
            if not isinstance(data, dict):
                return None, "服务端返回非对象 JSON"
            if data.get("error"):
                return data, str(data["error"])
            data.setdefault("request_id", response.headers.get("X-Request-Id"))
            return data, None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:1000]}"
    except (OSError, ValueError) as exc:
        return None, f"请求状态未知：{exc}；不会自动重试生成"


def local_media(src, kind):
    if src.startswith(("http://", "https://", "data:", "asset://")):
        return src
    if kind == "image":
        return ark.encode_image(src)
    # Large media must be a downloadable URL or an explicitly provisioned asset.
    raise ValueError("视频/音频参考请传公网 URL 或 asset://素材ID；不自动上传本地视频/音频")


def validate_video(body):
    """Known model constraints from the official creation API, before billing.

    Validate the final body, including parameters overrides. Unknown Endpoint IDs
    remain provider-validated rather than assuming a model family.
    """
    model = body["model"]
    series = "2.5" if "doubao-seedance-2-5-" in model else "2.0" if "doubao-seedance-2-0-" in model else None
    content = body["content"]
    roles = [item.get("role") for item in content]
    first = "first_frame" in roles
    references = any(role in ("reference_image", "reference_video", "reference_audio") for role in roles)
    if first and references:
        raise ValueError("首帧/首尾帧和全模态参考为互斥场景，不可混用")
    if series is None:
        return
    if "seed" in body or "frames" in body:
        raise ValueError("seed/frames 仅支持 Seedance 1.0 系列，当前 2.0/2.5 不支持")
    duration = body.get("duration")
    maximum = 30 if series == "2.5" else 15
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int)
                                or duration != -1 and not 4 <= duration <= maximum):
        raise ValueError(f"Seedance {series} duration 设 -1 或 4–{maximum} 秒")
    resolution = body["resolution"]
    supported = {"480p", "720p", "1080p"} if series == "2.5" else {"480p", "720p", "1080p", "4k"}
    if "-fast-" in model or "-mini-" in model:
        supported = {"480p", "720p"}
    if resolution not in supported:
        raise ValueError("所选 Seedance 模型不支持该 resolution")
    if body["ratio"] not in {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"}:
        raise ValueError("ratio 不在官方支持的宽高比枚举内")
    if series == "2.5" and first and body["ratio"] != "adaptive":
        raise ValueError("Seedance 2.5 首帧/首尾帧任务 ratio 必须为 adaptive")
    limits = (30, 10, 10) if series == "2.5" else (9, 3, 3)
    for role, limit in zip(("reference_image", "reference_video", "reference_audio"), limits):
        if roles.count(role) > limit:
            raise ValueError(f"Seedance {series} {role} 最多 {limit} 项")
    if series == "2.0" and "reference_audio" in roles and not any(role in ("reference_image", "reference_video") for role in roles):
        raise ValueError("Seedance 2.0 系列不可仅输入音频参考，须搭配参考图片或视频")
    if body.get("draft") and (series != "2.5" or resolution != "480p"):
        raise ValueError("draft 仅支持 Seedance 2.5 的 480p 输出")
    task_type = body.get("omni_reference_task_type", "auto")
    if task_type not in {"auto", "reference", "edit", "extend"}:
        raise ValueError("omni_reference_task_type 必须为 auto/reference/edit/extend")
    if task_type != "auto" and series != "2.5":
        raise ValueError("omni_reference_task_type 仅支持 Seedance 2.5")
    if task_type in ("edit", "extend"):
        if "reference_video" not in roles or body["ratio"] != "adaptive":
            raise ValueError("视频编辑/延长需 reference_video 和 ratio=adaptive")
        if task_type == "edit" and duration not in (None, -1):
            raise ValueError("Seedance 2.5 视频编辑 duration 必须为 -1 或省略")
    if body.get("output_format", "mp4") not in {"mp4", "mov"}:
        raise ValueError("output_format 必须为 mp4 或 mov")
    if body.get("output_format") == "mov" and series != "2.5":
        raise ValueError("mov 输出仅支持 Seedance 2.5")


def submit_video(opts, out_dir, wait, mode):
    model = VIDEO_MODELS.get(opts["model"], opts["model"])
    content = []
    if opts["prompt"]:
        content.append({"type": "text", "text": opts["prompt"]})
    groups = [("image", "first_frame", [opts["first_frame"]] if opts["first_frame"] else []),
              ("image", "last_frame", [opts["last_frame"]] if opts["last_frame"] else []),
              ("image", "reference_image", opts["reference_images"]),
              ("video", "reference_video", opts["reference_videos"]),
              ("audio", "reference_audio", opts["reference_audios"])]
    try:
        if not 0 <= wait <= 90:
            raise ValueError("wait 范围为 0–90 秒")
        if opts["last_frame"] and not opts["first_frame"]:
            raise ValueError("last_frame 必须配合 first_frame")
        for kind, role, sources in groups:
            for src in sources:
                content.append({"type": kind + "_url", kind + "_url": {"url": local_media(src, kind)}, "role": role})
        if not content:
            raise ValueError("prompt 或参考素材至少传一项")
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    body = {"model": model, "content": content, "resolution": opts["resolution"],
            "ratio": opts["ratio"], "generate_audio": opts["audio"], "watermark": opts["watermark"]}
    for name in ("duration", "seed"):
        if opts[name] is not None:
            body[name] = opts[name]
    if opts.get("parameters"):
        if set(opts["parameters"]) & {"model", "content", "stream"}:
            return {"ok": False, "error": "parameters 不能覆盖 model/content/stream"}
        body.update(opts["parameters"])
    try:
        validate_video(body)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job = STORE.create("video", model, out_dir, mode, summary={"resolution": body["resolution"], "duration": body.get("duration")})
    with STORE.processing(job):
        response, error = request("/contents/generations/tasks", body)
        if error:
            job.update(error=error, state="failed" if error.startswith(("HTTP 4", "未设置")) else "unknown")
            STORE.save(job)
            return STORE.result(job)
        job.update(task_id=response.get("id"), request_id=response.get("request_id"))
        if not job["task_id"]:
            job["error"] = "响应缺少任务 ID；不会自动重新提交"
            STORE.save(job)
            return STORE.result(job)
        job["state"] = "running"
        STORE.save(job)
        if wait == 0:
            job["result"]["status"] = "submitted"
            STORE.save(job)
            return STORE.result(job)
        return poll_video(job, wait)


def poll_video(job, wait=0):
    deadline = time.monotonic() + max(0, min(wait, 90))
    while True:
        response, error = request("/contents/generations/tasks/" + urllib.parse.quote(job["task_id"], safe=""),
                                  timeout=max(1, min(30, deadline - time.monotonic())) if wait else 30)
        if error:
            job["error"] = error
            STORE.save(job)
            return {**STORE.result(job), "ok": False, "query_failed": True}
        status = response.get("status")
        job.update(usage=response.get("usage"), request_id=response.get("request_id"), error=None)
        job["result"] = {"status": status, "duration": response.get("duration"), "resolution": response.get("resolution"),
                         "ratio": response.get("ratio"), "seed": response.get("seed"), "response": response}
        if status == "succeeded":
            content = response.get("content") or {}
            url = content.get("video_url")
            if not url:
                job.update(state="unknown", error="任务成功但缺少 video_url")
                STORE.save(job)
                return STORE.result(job)
            STORE.add(job, "video.mov" if response.get("output_format") == "mov" else "video.mp4", url=url)
            if content.get("last_frame_url"):
                STORE.add(job, "last-frame.jpg", url=content["last_frame_url"])
            return STORE.deliver(job)
        if status in ("failed", "cancelled", "expired"):
            job.update(state="failed", error=str(response.get("error") or status))
            STORE.save(job)
            return STORE.result(job)
        job["state"] = "running" if status in ("queued", "running") else "unknown"
        STORE.save(job)
        if time.monotonic() >= deadline:
            return STORE.result(job)
        transport.sleep(min(5, max(0, deadline - time.monotonic())))


def get_job(job_id=None, task_id=None, wait=0, out_dir=None, mode="local"):
    """Local record; pending video tasks are polled and delivered without resubmission."""
    def adopt(task_id, wait):
        # A task submitted elsewhere gets a fresh local record for delivery.
        job = STORE.create("video", None, out_dir, mode)
        with STORE.processing(job):
            job.update(task_id=task_id, state="running")
            STORE.save(job)
            return poll_video(job, wait)
    return STORE.lookup(job_id, task_id, wait, {"video": poll_video}, adopt)


def recover(job_id, wait=0):
    def handle(job):
        if job["kind"] == "video" and job["task_id"]:
            if job["artifacts"]:
                result = STORE.deliver(job)
                if result["ok"]:
                    return result
            # Polling can refresh an expired result URL without a new generation.
            return poll_video(job, wait)
        if job["kind"] == "image" and job.get("response_file"):
            return ark.deliver_image(json.loads(Path(job["response_file"]).read_text()), job)
        if job["state"] in ("unknown", "failed"):
            return {**STORE.result(job), "ok": False, "error": "没有可恢复的完整响应，不能自动重新生成"}
        return STORE.deliver(job)
    return STORE.recover(job_id, handle)


def chat(prompt, model, system=None, history=None, images=None, videos=None, thinking=None,
         max_tokens=None, temperature=None, json_mode=False, web_search=False, previous_response_id=None, parameters=None):
    model = CHAT_MODELS.get(model, model)
    if not prompt:
        return {"ok": False, "error": "缺少 prompt"}
    try:
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {"url": ark.encode_image(src)}} for src in images or []]
        content += [{"type": "video_url", "video_url": {"url": local_media(src, "video")}} for src in videos or []]
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    messages = ([{"role": "system", "content": system}] if system else []) + (history or [])
    messages.append({"role": "user", "content": content})
    use_responses = web_search or previous_response_id is not None
    if use_responses:
        # Responses uses input_text/input_image/input_video content, not Chat names.
        inputs = copy.deepcopy(messages)
        for message in inputs:
            if isinstance(message.get("content"), list):
                for item in message["content"]:
                    kind = item["type"]
                    if kind == "text":
                        item["type"] = "output_text" if message.get("role") == "assistant" else "input_text"
                    elif kind in ("image_url", "video_url"):
                        item["type"] = "input_image" if kind == "image_url" else "input_video"
                        item[kind] = item[kind]["url"]
        body = {"model": model, "input": inputs, "stream": False}
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        if web_search:
            body["tools"] = [{"type": "web_search"}]
        if max_tokens is not None:
            body["max_output_tokens"] = max_tokens
        if json_mode:
            body["text"] = {"format": {"type": "json_object"}}
        path = "/responses"
    else:
        body = {"model": model, "messages": messages, "stream": False}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        path = "/chat/completions"
    if thinking is not None:
        body["thinking"] = {"type": "enabled" if thinking else "disabled"}
    if temperature is not None:
        body["temperature"] = temperature
    if parameters:
        if set(parameters) & {"model", "input", "messages", "stream", "tools", "previous_response_id"}:
            return {"ok": False, "error": "parameters 不能覆盖 model/input/messages/stream"}
        body.update(parameters)
    response, error = request(path, body, timeout=300)
    if error:
        return {"ok": False, "model": model, "error": error}
    if use_responses:
        chunks, reasoning, sources = [], [], []
        for item in response.get("output") or []:
            if item.get("type") == "reasoning":
                reasoning.extend(x.get("text", "") for x in item.get("summary") or [])
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    chunks.append(part.get("text", ""))
                    sources.extend(part.get("annotations") or [])
        return {"ok": response.get("status") == "completed", "model": model,
                "content": "".join(chunks), "reasoning": "\n".join(reasoning) or None,
                "sources": sources, "response_id": response.get("id"), "status": response.get("status"),
                "usage": response.get("usage"), "response": response, "error": response.get("error")}
    choices = response.get("choices") or []
    if not choices:
        return {"ok": False, "error": "响应缺少 choices", "response": response}
    message = choices[0].get("message") or {}
    return {"ok": True, "model": model, "content": message.get("content"), "reasoning": message.get("reasoning_content"),
            "finish_reason": choices[0].get("finish_reason"), "usage": response.get("usage"),
            "request_id": response.get("request_id"), "response": response, "error": None}


def embed(model, texts=None, contents=None, dimensions=None, parameters=None):
    if bool(texts) == bool(contents):
        return {"ok": False, "error": "texts 和 contents 必须且只能传一项"}
    try:
        items = copy.deepcopy(contents)
        for item in items or []:
            if item.get("type") == "image_url":
                item["image_url"]["url"] = ark.encode_image(item["image_url"]["url"])
            elif item.get("type") == "video_url":
                item["video_url"]["url"] = local_media(item["video_url"]["url"], "video")
        body = {"model": model, "input": items if contents else texts}
        if dimensions is not None:
            body["dimensions"] = dimensions
        if parameters:
            if set(parameters) & {"model", "input"}:
                raise ValueError("parameters 不能覆盖 model/input")
            body.update(parameters)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    response, error = request("/embeddings/multimodal" if contents else "/embeddings", body)
    return {"ok": not error, "model": model, "data": (response or {}).get("data"),
            "usage": (response or {}).get("usage"), "response": response, "error": error}
