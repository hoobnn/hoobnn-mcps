"""Bailian voice customization, video editing/portrait animation and retrieval APIs."""
import base64
import copy
import json
import re
from pathlib import Path

from .dashscope import encode_image, request
from .jobs import Store

STORE = Store("BAILIAN_JOB_DIR", "~/.local/share/ali-bailian-mcp/jobs")
CUSTOMIZATION = "/api/v1/services/audio/tts/customization"
DOCS = {
    "voice_clone": "https://help.aliyun.com/en/model-studio/voice-clone-design-http-api",
    "voice_design": "https://help.aliyun.com/zh/model-studio/voice-design-api-references",
    "video_edit": "https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference",
    "portrait": "https://help.aliyun.com/zh/model-studio/wan-s2v-api",
    "embedding": "https://help.aliyun.com/zh/model-studio/embedding",
    "multimodal_embedding": "https://help.aliyun.com/en/model-studio/multimodal-embedding-api-reference",
    "rerank": "https://help.aliyun.com/zh/model-studio/text-rerank-api",
}
VOICE_MODELS = {"clone": "qwen-voice-enrollment", "design": "qwen-voice-design", "cosyvoice": "voice-enrollment"}


def api(path, body, timeout=120):
    response, error = request(path, body, timeout=timeout)
    if not error and response.get("code"):
        error = f"{response['code']}: {response.get('message')}"
    return response, error


def voice_result(response, error):
    output = (response or {}).get("output") or {}
    return {"ok": not error, "voice": output.get("voice") or output.get("voice_id"),
            "target_model": output.get("target_model"), "output": output,
            "usage": (response or {}).get("usage"), "request_id": (response or {}).get("request_id"), "error": error}


def clone_voice(audio, target_model, preferred_name, text=None, language=None):
    try:
        if not target_model.startswith("qwen3-tts-vc-") or "realtime" in target_model:
            raise ValueError("请选择非实时 qwen3-tts-vc 模型，以便用本MCP的text_to_speech合成")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", preferred_name):
            raise ValueError("preferred_name 用1–16位英文字母、数字或下划线")
        src = audio
        if not src.startswith(("http://", "https://", "data:")):
            path = Path(src).expanduser()
            if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("参考音频不存在或超过10MB")
            mime = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}.get(path.suffix.lower())
            if not mime:
                raise ValueError("参考音频支持wav/mp3/m4a")
            src = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
        inp = {"action": "create", "target_model": target_model,
               "preferred_name": preferred_name, "audio": {"data": src}}
        if text:
            inp["text"] = text
        if language:
            inp["language"] = language
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    response, error = api(CUSTOMIZATION, {"model": "qwen-voice-enrollment", "input": inp})
    result = voice_result(response, error)
    if result["ok"] and not result["voice"]:
        result.update(ok=False, error="响应没有音色ID，不自动重新创建")
    result["target_model"] = result.get("target_model") or target_model
    return result


def design_voice(voice_prompt, preview_text, target_model, preferred_name, out_dir, mode):
    if not voice_prompt.strip() or len(voice_prompt) > 2048 or not preview_text.strip():
        return {"ok": False, "error": "声音描述须为1–2048字符，preview_text不能为空"}
    if not target_model.startswith("qwen3-tts-vd-") or "realtime" in target_model:
        return {"ok": False, "error": "请选择非实时qwen3-tts-vd模型"}
    if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", preferred_name):
        return {"ok": False, "error": "preferred_name 用1–16位英文字母、数字或下划线"}
    body = {"model": "qwen-voice-design", "input": {"action": "create", "target_model": target_model,
            "preferred_name": preferred_name, "voice_prompt": voice_prompt, "preview_text": preview_text},
            "parameters": {"sample_rate": 24000, "response_format": "wav"}}
    job = STORE.create("voice_preview", target_model, out_dir, mode,
                       summary={"preferred_name": preferred_name})
    response, error = api(CUSTOMIZATION, body)
    result = voice_result(response, error)
    result["target_model"] = result.get("target_model") or target_model
    # Store the voice ID before delivering preview audio; download errors must not create another voice.
    job.update(request_id=result["request_id"], usage=result["usage"], result={k: v for k, v in result.items() if k != "output"})
    STORE.save(job)
    if error or not result["voice"]:
        job.update(error=error or "响应缺少音色ID，不自动重新创建", state="unknown")
        STORE.save(job)
        return STORE.result(job)
    STORE.record_response(job, response)
    return deliver_preview(job, response)


def deliver_preview(job, response):
    output = response.get("output") or {}
    preview = output.get("preview_audio") or {}
    try:
        if preview.get("data"):
            STORE.add(job, "preview.wav", data=base64.b64decode(preview["data"], validate=True))
        elif preview.get("url"):
            STORE.add(job, "preview.wav", url=preview["url"])
    except (OSError, ValueError) as exc:
        job.update(state="unknown", error=f"音色已创建，试听音频留档失败：{exc}")
        STORE.save(job)
        return STORE.result(job)
    if job["artifacts"]:
        return STORE.deliver(job)
    job.update(state="delivered", error=None)
    STORE.save(job)
    return STORE.result(job)


def list_voices(kind, page_index=0, page_size=20, prefix=None):
    if kind not in VOICE_MODELS or page_index < 0 or not 1 <= page_size <= 100:
        return {"ok": False, "error": "kind=clone/design/cosyvoice，page_index>=0，page_size=1–100"}
    inp = {"action": "list_voice" if kind == "cosyvoice" else "list", "page_index": page_index, "page_size": page_size}
    if prefix:
        if kind != "cosyvoice":
            return {"ok": False, "error": "prefix过滤只支持cosyvoice"}
        inp["prefix"] = prefix
    response, error = api(CUSTOMIZATION, {"model": VOICE_MODELS[kind], "input": inp})
    output = (response or {}).get("output") or {}
    return {"ok": not error, "voices": output.get("voice_list") or [], "output": output,
            "request_id": (response or {}).get("request_id"), "usage": (response or {}).get("usage"), "error": error}


def get_voice(voice, kind, max_pages=10):
    if kind == "cosyvoice":
        response, error = api(CUSTOMIZATION, {"model": "voice-enrollment", "input": {"action": "query_voice", "voice_id": voice}})
        return voice_result(response, error)
    if kind not in ("clone", "design") or not 1 <= max_pages <= 100:
        return {"ok": False, "error": "kind=clone/design/cosyvoice，max_pages=1–100"}
    # Qwen has no query-details operation. Search the paginated list honestly.
    for page in range(max_pages):
        result = list_voices(kind, page, 100)
        if not result["ok"]:
            return result
        for item in result["voices"]:
            if (item.get("voice") or item.get("voice_id")) == voice:
                return {"ok": True, "voice": voice, "output": item, "source": "voice_list", "error": None}
        total = result["output"].get("total_count")
        if len(result["voices"]) < 100 or (total is not None and (page + 1) * 100 >= total):
            return {"ok": False, "error": "完整列表中未找到此音色", "voice": voice}
    return {"ok": False, "error": "达到max_pages，尚不能判断音色是否存在", "voice": voice}


def submit_video(body, out_dir, wait, mode, path="/api/v1/services/aigc/video-generation/video-synthesis", oss=False):
    from . import media
    if not 0 <= wait <= 90:
        return {"ok": False, "error": "wait范围为0–90秒"}
    job = STORE.create("video", body["model"], out_dir, mode, summary=body.get("parameters"))
    headers = {"X-DashScope-Async": "enable"}
    if oss:
        headers["X-DashScope-OssResourceResolve"] = "enable"
    response, error = api_with_headers(path, body, headers)
    if error:
        job.update(error=error, state="failed" if error.startswith(("HTTP 4", "未设置")) else "unknown")
        STORE.save(job)
        return STORE.result(job)
    output = response.get("output") or {}
    job.update(task_id=output.get("task_id"), request_id=response.get("request_id"))
    if not job["task_id"]:
        job["error"] = "响应缺少task_id，禁止自动重新提交"
        STORE.save(job)
        return STORE.result(job)
    job.update(state="running", result={"status": output.get("task_status") or "PENDING"})
    STORE.save(job)
    return STORE.result(job) if wait == 0 else media.poll_job(job, wait)


def api_with_headers(path, body, headers):
    response, error = request(path, body, timeout=60, headers=headers)
    if not error and response.get("code"):
        error = f"{response['code']}: {response.get('message')}"
    return response, error


def edit_video(video, prompt, images, resolution, audio_setting, watermark, seed, out_dir, wait, mode):
    from .media import is_remote, upload
    if not video or not prompt.strip() or len(images) > 5 or resolution not in ("720P", "1080P") or audio_setting not in ("auto", "origin"):
        return {"ok": False, "error": "需video和prompt；最多5张参考图；resolution=720P/1080P，audio_setting=auto/origin"}
    try:
        oss = not is_remote(video) or video.startswith("oss://")
        src = upload(video, "happyhorse-1.0-video-edit") if not is_remote(video) else video
        items = [{"type": "video", "url": src}]
        items += [{"type": "reference_image", "url": encode_image(image)} for image in images]
        oss = oss or any(item["url"].startswith("oss://") for item in items)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    params = {"resolution": resolution, "audio_setting": audio_setting, "watermark": watermark}
    if seed is not None:
        params["seed"] = seed
    return submit_video({"model": "happyhorse-1.0-video-edit", "input": {"prompt": prompt, "media": items},
                         "parameters": params}, out_dir, wait, mode, oss=oss)


def animate_portrait(image, audio, resolution, out_dir, wait, mode):
    from .media import is_remote, upload
    if resolution not in ("480P", "720P"):
        return {"ok": False, "error": "resolution=480P/720P"}
    try:
        sources = [upload(src, "wan2.2-s2v") if not is_remote(src) else src for src in (image, audio)]
        if any(src.startswith("data:") for src in sources):
            raise ValueError("数字人输入需URL或本地文件，不支持data URL")
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    body = {"model": "wan2.2-s2v", "input": {"image_url": sources[0], "audio_url": sources[1]},
            "parameters": {"resolution": resolution}}
    return submit_video(body, out_dir, wait, mode, path="/api/v1/services/aigc/image2video/video-synthesis",
                        oss=any(src.startswith("oss://") for src in sources))


def embed(model, texts=None, contents=None, dimensions=None, parameters=None):
    if bool(texts) == bool(contents):
        return {"ok": False, "error": "texts与contents必须且只能选一项"}
    try:
        options = copy.deepcopy(parameters or {})
        if dimensions is not None:
            options["dimension" if contents else "dimensions"] = dimensions
        if contents:
            items = copy.deepcopy(contents)
            for item in items:
                if item.get("image"):
                    item["image"] = encode_image(item["image"])
                if item.get("multi_images"):
                    item["multi_images"] = [encode_image(src) for src in item["multi_images"]]
                if item.get("video") and not item["video"].startswith(("http://", "https://")):
                    raise ValueError("多模态向量的视频需公网URL")
            body = {"model": model, "input": {"contents": items}, "parameters": options}
            path = "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
        else:
            if set(options) & {"model", "input"}:
                raise ValueError("parameters不能覆盖model/input")
            body = {"model": model, "input": texts, "encoding_format": "float", **options}
            path = "/compatible-mode/v1/embeddings"
    except (OSError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    response, error = api(path, body)
    return {"ok": not error, "model": model, "data": (response or {}).get("data") or (response or {}).get("output"),
            "usage": (response or {}).get("usage"), "request_id": (response or {}).get("request_id"), "response": response, "error": error}


def rerank(query, documents, model, top_n=None, return_documents=False):
    if not query.strip() or not documents or (top_n is not None and not 1 <= top_n <= len(documents)):
        return {"ok": False, "error": "需query与非空documents；top_n必须在1至文档数量之间"}
    params = {"return_documents": return_documents}
    if top_n is not None:
        params["top_n"] = top_n
    if model == "qwen3-rerank":
        body = {"model": model, "query": query, "documents": documents, **params}
        path = "/compatible-api/v1/reranks"
    else:
        body = {"model": model, "input": {"query": query, "documents": documents}, "parameters": params}
        path = "/api/v1/services/rerank/text-rerank/text-rerank"
    response, error = api(path, body)
    result = response or {}
    return {"ok": not error, "model": model, "results": result.get("results") or (result.get("output") or {}).get("results"),
            "usage": result.get("usage"), "request_id": result.get("request_id"), "response": response, "error": error}


def recover(job_id, wait=0):
    from . import media
    def handle(job):
        if job["kind"] == "video" and job["task_id"]:
            if job["artifacts"]:
                result = STORE.deliver(job)
                if result["ok"]:
                    return result
            return media.poll_job(job, wait)
        if job["kind"] == "tts":
            return media.resume_tts(job)
        if job["kind"] == "image" and job.get("response_file"):
            from .dashscope import deliver_image
            return deliver_image(json.loads(Path(job["response_file"]).read_text()), job)
        if job["kind"] == "voice_preview" and job.get("response_file"):
            return deliver_preview(job, json.loads(Path(job["response_file"]).read_text()))
        if job["state"] in ("unknown", "failed"):
            return {**STORE.result(job), "ok": False, "error": "缺少可恢复的完整生成结果，不会自动重新生成"}
        return STORE.deliver(job)
    return STORE.recover(job_id, handle)
