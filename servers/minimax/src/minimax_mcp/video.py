"""H3 V2 contracts and durable asynchronous jobs."""
import base64
import copy
import json
import time
from collections import Counter
from urllib.parse import urlsplit

from . import client, transport
from .jobs import Store

STORE = Store("MINIMAX_JOB_DIR", "~/.local/share/hoobnn-minimax-mcp/jobs")
MODELS = {"MiniMax-H3": {"resolutions": ["768P", "2K"], "min_duration": 4},
          "MiniMax-H3-Max": {"resolutions": ["480P", "768P"], "min_duration": 5}}
RATIOS = {"adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
ROLES = {"image_url": {"first_frame", "last_frame", "reference_image"},
         "video_url": {"reference_video"}, "audio_url": {"reference_audio"}}
ENDPOINTS = {"generation": "/v2/video_generation", "h3_context_ir": "/v2/h3_context_ir",
             "regeneration": "/v2/video_regeneration"}


def validate_url(value, kind):
    if not isinstance(value, str) or not value:
        raise ValueError("素材 URL / 路径不能为空")
    if value.startswith("mm_file://"):
        client.identifier(value.removeprefix("mm_file://"))
    elif value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("素材 URL 无效")
    elif value.startswith("data:"):
        head, separator, encoded = value.partition(",")
        formats = {"image": {"jpeg", "jpg", "png", "webp", "heic", "heif"},
                   "video": {"mp4"}, "audio": {"mpeg", "mp3", "wav", "x-wav"}}
        allowed = {f"data:{kind}/{fmt};base64" for fmt in formats[kind]}
        if not separator or head not in allowed:
            raise ValueError(f"无效的 {kind} Base64 data URI")
        if len(encoded) > client.LIMITS[kind] * 1024 * 1024 * 4 // 3 + 4:
            raise ValueError("Base64 素材超过单文件限制")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise ValueError("无效的 Base64 数据") from None
        if not 0 < len(decoded) <= client.LIMITS[kind] * 1024 * 1024:
            raise ValueError("Base64 素材为空或超过单文件限制")
    else:
        client.local_media(value, kind)


def make_content(prompt, content=None, first_frame=None, last_frame=None,
                 reference_images=None, reference_videos=None, reference_audios=None):
    shortcuts = [first_frame, last_frame, reference_images, reference_videos, reference_audios]
    if content is not None:
        if prompt or any(shortcuts):
            raise ValueError("content 与 prompt / 首尾帧 / reference_* 快捷参数互斥")
        return copy.deepcopy(content)
    result = [{"type": "text", "text": prompt}]
    for role, kind, values in (("first_frame", "image_url", [first_frame] if first_frame else []),
                               ("last_frame", "image_url", [last_frame] if last_frame else []),
                               ("reference_image", "image_url", reference_images or []),
                               ("reference_video", "video_url", reference_videos or []),
                               ("reference_audio", "audio_url", reference_audios or [])):
        result.extend({"type": kind, kind: {"url": value}, "role": role} for value in values)
    return result


def validate_content(content, regeneration=False):
    if not isinstance(content, list) or not content:
        raise ValueError("content 必须是非空数组")
    counts = Counter()
    for item in content:
        if not isinstance(item, dict):
            raise ValueError("content 每项须为 object")
        kind = item.get("type")
        counts[kind] += 1
        if kind == "text":
            text = item.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 7000:
                raise ValueError("text 须为 1–7000 字符非空提示词")
        elif kind in ROLES:
            role = item.get("role", "first_frame" if kind == "image_url" else None)
            allowed = ROLES[kind] | ({"base_video"} if regeneration and kind == "video_url" else set())
            if role not in allowed:
                raise ValueError(f"{kind} 不支持 role={role}")
            counts[role] += 1
            value = item.get(kind)
            if not isinstance(value, dict):
                raise ValueError(f"{kind} 须为包含 url 的对象")
            validate_url(value.get("url"), kind.removesuffix("_url"))
        else:
            raise ValueError(f"未知 content type: {kind}")
    if counts["text"] != 1:
        raise ValueError("content 必须且只能有一个非空 text 项")
    for role, maximum in {"first_frame": 1, "last_frame": 1, "reference_image": 9,
                          "reference_video": 3, "reference_audio": 3, "base_video": 1}.items():
        if counts[role] > maximum:
            raise ValueError(f"{role} 最多 {maximum} 项")
    frames = counts["first_frame"] + counts["last_frame"]
    references = sum(counts[role] for role in ("reference_image", "reference_video", "reference_audio"))
    if frames and references:
        raise ValueError("首尾帧与多模态参考素材互斥")
    if regeneration and counts["base_video"] != 1:
        raise ValueError("再生成必须且只能包含一个 role=base_video 的源视频")
    return "frames" if frames else "reference" if references else "text"


def build_request(task_type, *, prompt="", model="MiniMax-H3", content=None,
                  duration=5, resolution=None, ratio=None, first_frame=None, last_frame=None,
                  reference_images=None, reference_videos=None, reference_audios=None,
                  source_task_id=None, parameters=None):
    if task_type not in ENDPOINTS or model not in MODELS:
        raise ValueError("仅支持 H3 / H3-Max V2；旧 Hailuo V1 请使用原 MCP")
    if task_type != "generation" and model != "MiniMax-H3":
        raise ValueError("提示词增强和再生成仅支持 MiniMax-H3")
    options = copy.deepcopy(parameters or {})
    allowed = {"callback_url"} | ({"aigc_watermark"} if task_type != "h3_context_ir" else set())
    if task_type == "generation" and model == "MiniMax-H3-Max":
        allowed.add("extra")
    if not isinstance(options, dict) or set(options) - allowed:
        raise ValueError(f"parameters 仅支持 {sorted(allowed)}；不能覆盖模型或 content")
    if "aigc_watermark" in options and not isinstance(options["aigc_watermark"], bool):
        raise ValueError("aigc_watermark 必须是 boolean")
    if "callback_url" in options:
        parsed = urlsplit(options["callback_url"])
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("callback_url 须为 HTTP/HTTPS URL")
    if "extra" in options:
        extra = options["extra"]
        if (not isinstance(extra, dict) or set(extra) - {"prompt_expansion_mode"}
                or extra.get("prompt_expansion_mode", "balanced") not in {"disabled", "balanced", "quality"}):
            raise ValueError("extra.prompt_expansion_mode 须为 disabled / balanced / quality")
    body = {"model": model, **options}
    if task_type == "regeneration" and source_task_id is not None:
        if content is not None or prompt or any((first_frame, last_frame, reference_images, reference_videos, reference_audios)):
            raise ValueError("source_task_id 与 content / 素材互斥")
        body["source_task_id"] = client.identifier(source_task_id)
    else:
        body["content"] = make_content(prompt, content, first_frame, last_frame,
                                       reference_images, reference_videos, reference_audios)
        mode = validate_content(body["content"], task_type == "regeneration")
        if task_type != "regeneration":
            ratio = ratio or ("16:9" if mode == "text" else "adaptive")
            if ratio not in RATIOS or (mode == "text" and ratio == "adaptive"):
                raise ValueError("无效 ratio；纯文生视频不能使用 adaptive")
            body["ratio"] = "adaptive" if mode == "frames" else ratio
    if task_type != "regeneration":
        if type(duration) is not int or not MODELS[model]["min_duration"] <= duration <= 15:
            raise ValueError(f"{model} duration 须为 {MODELS[model]['min_duration']}–15 整数秒")
        body["duration"] = duration
    if task_type != "h3_context_ir":
        resolution = resolution or ("2K" if model == "MiniMax-H3" else "768P")
        if resolution not in MODELS[model]["resolutions"] or (task_type == "regeneration" and resolution != "2K"):
            raise ValueError("模型不支持该分辨率；H3-Max 不支持 2K，再生成仅支持 2K")
        body["resolution"] = resolution
    if len(json.dumps(body).encode()) > 64 * 1024 * 1024:
        raise ValueError("请求体超过 64 MB，改用公网 URL / mm_file://")
    return body


def result(job):
    payload = STORE.result(job)
    payload["ok"] = job["state"] == "delivered" and not job.get("error")
    payload["completed"] = job["state"] == "delivered"
    if job["state"] in {"queued", "running"} and not job.get("error"):
        payload["ok"] = True
    return payload


def failure(job, exc, submitting=False):
    if submitting:
        job["state"] = "failed" if isinstance(exc, client.APIError) and exc.definitive else "unknown"
    job["error"] = str(exc)
    if isinstance(exc, client.APIError):
        job["request_id"] = exc.request_id
        job["result"]["error_code"] = exc.code
    STORE.save(job)
    return {**result(job), "ok": False, "retryable": False}


def submit(body, task_type, out_dir, mode, wait=0):
    if type(wait) is not int or not 0 <= wait <= 90:
        raise ValueError("wait 范围0–90秒")
    client.configuration()  # Reject missing credentials before creating a job/uploading.
    job = STORE.create("video", body["model"], out_dir, mode,
                       summary={"task_type": task_type, "resolution": body.get("resolution"),
                                "duration": body.get("duration")})
    with STORE.processing(job):
        job["api_host"] = client.configuration()[0]
        job["result"]["task_type"] = task_type
        STORE.save(job)
        body = copy.deepcopy(body)
        # Persist upload receipts. All local inputs were validated before any network writes.
        try:
            for item in body.get("content", []):
                kind = item["type"]
                if kind == "text":
                    continue
                value = item[kind]["url"]
                if not value.startswith(("http://", "https://", "data:", "mm_file://")):
                    uploaded = client.upload(value)
                    item[kind]["url"] = uploaded["uri"]
                    job.setdefault("uploads", []).append(uploaded)
                    STORE.save(job)
            # Durable exact input enables reproducible base_video regeneration, no API key.
            job["resume"] = {"body": body, "task_type": task_type}
            STORE.save(job)
        except Exception as exc:
            job["state"] = "failed"  # No generation POST has been attempted.
            return failure(job, exc)
        try:
            response = client.request(ENDPOINTS[task_type], body)
            if not response.get("task_id"):
                raise ValueError("提交响应缺少 task_id；提交状态未知，不能自动重试")
            job.update(task_id=str(response["task_id"]), state="queued", error=None,
                       request_id=response.get("request_id"))
            STORE.save(job)  # Keep task ID even if saving the full response fails.
            STORE.record_response(job, response)
        except Exception as exc:
            return failure(job, exc, submitting=not bool(job["task_id"]))
        return poll(job, wait) if wait else result(job)


def poll(job, wait=0):
    if job.get("api_host") and job["api_host"] != client.configuration()[0]:
        return {**result(job), "ok": False, "error": "任务 API 域名与当前 MINIMAX_API_HOST 不一致"}
    deadline = time.monotonic() + wait
    try:
        while True:
            response = client.request("/v2/query/video_generation/" + client.identifier(job["task_id"]))
            task = response.get("task")
            if not isinstance(task, dict) or str(task.get("id")) != job["task_id"]:
                raise ValueError("查询响应缺少匹配的 task.id")
            status = task.get("status")
            if status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
                raise ValueError(f"未知任务状态: {status}")
            job["result"].update(status=status, task_type=task.get("task_type", job["result"].get("task_type")),
                                  resolution=task.get("resolution"), duration=task.get("duration"), ratio=task.get("ratio"))
            job.update(usage=task.get("usage"), error=None)
            STORE.record_response(job, response)
            if status in {"failed", "cancelled"}:
                job.update(state="failed", error=task.get("error") or f"任务 {status}")
                STORE.save(job)
                return result(job)
            if status == "succeeded":
                output = task.get("content") or {}
                if task.get("task_type") == "h3_context_ir":
                    if not isinstance(output.get("prompt"), str) or not output["prompt"].strip():
                        raise ValueError("成功的提示词增强任务缺少 content.prompt")
                    job["result"]["prompt"] = output["prompt"]
                    STORE.add(job, "prompt.txt", data=output["prompt"].encode())
                else:
                    url = output.get("url")
                    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                        raise ValueError("成功的视频任务缺少 content.url")
                    STORE.add(job, "video.mp4", url=url)
                STORE.deliver(job)
                return result(job)
            job["state"] = status
            STORE.save(job)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return result(job)
            transport.sleep(min(10, remaining))
    except Exception as exc:
        return failure(job, exc)


def get_job(job_id=None, task_id=None, wait=0, *, out_dir=None, mode="local", recover=False):
    if type(wait) is not int or not 0 <= wait <= 90:
        raise ValueError("wait 范围0–90秒")
    if not job_id and not task_id:
        raise ValueError("需要 job_id 或 task_id")
    if task_id:
        task_id = client.identifier(task_id)
    if not job_id:
        job_id = STORE.find_task(task_id, {"video"})
        if job_id is None:
            client.configuration()
            job = STORE.create("video", "MiniMax-H3", out_dir, mode, summary={"adopted": True})
            job.update(task_id=task_id, state="queued", api_host=client.configuration()[0])
            STORE.save(job)
            job_id = job["job_id"]
    with STORE.locked(job_id) as job:
        if task_id and job["task_id"] != task_id:
            raise ValueError("job_id 与 task_id 不属于同一任务")
        if job["kind"] == "video" and job["task_id"]:
            if recover or job["state"] in {"queued", "running", "unknown"}:
                return poll(job, wait)
        if recover:
            if job["state"] == "unknown":
                return {**result(job), "ok": False, "error": "提交状态未知且无 task_id；恢复不会重新生成"}
            if job["artifacts"]:
                STORE.deliver(job)
        return result(job)
