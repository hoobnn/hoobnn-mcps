"""Bailian voice customization, video editing/portrait animation and retrieval APIs."""
import base64
import copy
import json
import re
from pathlib import Path

from .dashscope import InputError, encode_image, request
from .jobs import Store
from .mcp_runtime import merge_parameters

STORE = Store("BAILIAN_JOB_DIR", "~/.local/share/ali-bailian-mcp/jobs")
CUSTOMIZATION = "/api/v1/services/audio/tts/customization"
DOCS = {
    "image": "https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference",
    "wan_image": "https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference",
    "chat": "https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions",
    "tts": "https://help.aliyun.com/zh/model-studio/qwen-tts-api",
    "asr": "https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference",
    "video": "https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference",
    "models": "https://help.aliyun.com/zh/model-studio/list-models",
    "upload": "https://help.aliyun.com/zh/model-studio/get-temporary-file-url",
    "tts_models": "https://help.aliyun.com/zh/model-studio/tts-model",
    "regions": "https://help.aliyun.com/zh/model-studio/regions",
    "tts_realtime_access": "https://help.aliyun.com/zh/model-studio/qwen-audio-tts-model-access",
    "cosyvoice_realtime_access": "https://help.aliyun.com/zh/model-studio/cosyvoice-model-access",
    "minimax_chat": "https://help.aliyun.com/zh/model-studio/minimax-api-by-minimax",
    "tts_qwen_audio": "https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api",
    "tts_cosyvoice": "https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api",
    "tts_instruction": "https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide",
    "voice_clone": "https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api",
    "voice_clone_guide": "https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide",
    "voice_design": "https://help.aliyun.com/zh/model-studio/voice-design-api-references",
    "voice_design_guide": "https://help.aliyun.com/zh/model-studio/voice-design-user-guide",
    "video_edit": "https://help.aliyun.com/en/model-studio/happyhorse-video-edit-api-reference",
    "portrait": "https://help.aliyun.com/zh/model-studio/wan-s2v-api",
    "embedding": "https://help.aliyun.com/zh/model-studio/embedding",
    "multimodal_embedding": "https://help.aliyun.com/en/model-studio/multimodal-embedding-api-reference",
    "rerank": "https://help.aliyun.com/zh/model-studio/text-rerank-api",
}
ENROLLMENT = "voice-enrollment"
DEFAULT_VOICE_TARGET = "qwen-audio-3.0-tts-flash"
# 声音复刻/设计支持的 HTTP 非实时合成模型（voice-cloning-user-guide / voice-design-user-guide「支持的模型与地域」）。
CLONE_TARGETS = ("qwen-audio-3.1-tts-plus", "qwen-audio-3.0-tts-plus", "qwen-audio-3.1-tts-flash", "qwen-audio-3.0-tts-flash",
                 "cosyvoice-v3.5-plus", "cosyvoice-v3.5-flash", "cosyvoice-v3-plus", "cosyvoice-v3-flash", "cosyvoice-v2")
DESIGN_TARGETS = CLONE_TARGETS[:-1]
# language_hints 仅以下复刻模型支持，取值见复刻API正文。
CLONE_LANGUAGES = {
    **{m: {"zh", "en", "fr", "de", "ja", "ko", "ru", "pt", "th", "id", "vi", "it", "es", "ms", "fil", "ar"}
       for m in ("qwen-audio-3.1-tts-plus", "qwen-audio-3.1-tts-flash", "qwen-audio-3.0-tts-plus", "qwen-audio-3.0-tts-flash")},
    "cosyvoice-v3-plus": {"zh", "en", "fr", "de", "ja", "ko", "ru"},
    **{m: {"zh", "en", "fr", "de", "ja", "ko", "ru", "pt", "th", "id", "vi"}
       for m in ("cosyvoice-v3.5-plus", "cosyvoice-v3.5-flash", "cosyvoice-v3-flash")},
}
VOICE_KINDS = ("enrollment", "cosyvoice", "clone", "design")  # 后三个为旧值，统一映射到 voice-enrollment
CLONE_AUDIO_LIMIT = 10 * 1024 * 1024
CLONE_AUDIO_MIME = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4"}
CLONE_DATA_MIME = {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a", "audio/x-m4a"}


def api(path, body, timeout=120):
    response, error = request(path, body, timeout=timeout)
    if not error and response.get("code"):
        error = f"{response['code']}: {response.get('message')}"
    return response, error


def voice_result(response, error):
    output = (response or {}).get("output") or {}
    return {"ok": not error, "voice": output.get("voice_id") or output.get("voice"),
            "target_model": output.get("target_model"), "output": output,
            "usage": (response or {}).get("usage"), "request_id": (response or {}).get("request_id"), "error": error}


def check_prefix(prefix):
    if not re.fullmatch(r"[A-Za-z0-9]{1,10}", prefix or ""):
        return "prefix仅允许英文字母和数字，1–10个字符"
    return None


def clone_audio(audio=None, url=None):
    """Encode local reference audio for input.audio; never use model-bound OSS uploads."""
    if audio is not None and url is not None:
        raise InputError("audio与旧参数url只能传一项，不能互相覆盖")
    if url is not None and (not isinstance(url, str) or not url.startswith(("http://", "https://"))):
        raise InputError("旧参数url只接受公网http/https音频URL；本地文件或Base64 Data URI请用audio")
    source = audio if audio is not None else url
    if not isinstance(source, str) or not source:
        raise InputError("缺少audio（本地音频、http/https URL或Base64 Data URI）")
    if source.startswith(("http://", "https://")):
        return source
    if source.startswith("oss://"):
        raise InputError("voice-enrollment未说明支持oss://临时地址；请用本地音频、http/https URL或Base64 Data URI")
    if source.startswith("data:"):
        match = re.fullmatch(r"data:([^;,]+);base64,([A-Za-z0-9+/]*={0,2})", source)
        if not match or match[1].lower() not in CLONE_DATA_MIME:
            raise InputError("audio须为WAV/MP3/M4A的Base64 Data URI")
        # Bound encoded size before allocating a decoded copy.
        if len(match[2]) > ((CLONE_AUDIO_LIMIT + 2) // 3) * 4:
            raise InputError("复刻音频超过10MB")
        try:
            data = base64.b64decode(match[2], validate=True)
        except ValueError as exc:
            raise InputError("audio的Base64数据无效") from exc
        if not data or len(data) > CLONE_AUDIO_LIMIT:
            raise InputError("复刻音频不能为空且不能超过10MB")
        return source
    path = Path(source).expanduser()
    mime = CLONE_AUDIO_MIME.get(path.suffix.lower().lstrip("."))
    if mime is None:
        raise InputError("复刻本地音频仅支持WAV/MP3/M4A")
    if not path.is_file():
        raise InputError(f"音频不存在：{source}")
    if not 0 < path.stat().st_size <= CLONE_AUDIO_LIMIT:
        raise InputError("复刻音频不能为空且不能超过10MB")
    data = path.read_bytes()
    if not 0 < len(data) <= CLONE_AUDIO_LIMIT:
        raise InputError("复刻音频不能为空且不能超过10MB")
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def clone_voice(audio=None, target_model=DEFAULT_VOICE_TARGET, prefix="custom", language=None,
                enable_preprocess=None, max_prompt_audio_length=None, *, url=None):
    """voice-enrollment create_voice（复刻）：URL、Base64 Data URI或本地音频。"""
    if target_model not in CLONE_TARGETS:
        return {"ok": False, "error": "target_model须为支持声音复刻的HTTP合成模型：" + "、".join(CLONE_TARGETS)}
    error = check_prefix(prefix)
    advanced = target_model in CLONE_LANGUAGES  # language_hints/预处理/时长参数的支持范围一致
    if not error and language is not None:
        allowed = CLONE_LANGUAGES.get(target_model, set())
        if not advanced or (allowed is not None and language not in allowed):
            error = f"{target_model}不支持language={language}"
    if not error and (enable_preprocess is not None or max_prompt_audio_length is not None):
        if not advanced or target_model == "cosyvoice-v3-plus":
            error = f"{target_model}不支持enable_preprocess/max_prompt_audio_length"
        elif max_prompt_audio_length is not None and not 3.0 <= max_prompt_audio_length <= 30.0:
            error = "max_prompt_audio_length范围3.0–30.0秒"
    if error:
        return {"ok": False, "target_model": target_model, "error": error}
    try:
        reference = clone_audio(audio, url)
    except (InputError, OSError) as exc:
        return {"ok": False, "target_model": target_model, "error": str(exc)}
    inp = {"action": "create_voice", "target_model": target_model, "prefix": prefix, "audio": reference}
    if language:
        inp["language_hints"] = [language]
    if enable_preprocess is not None:
        inp["enable_preprocess"] = enable_preprocess
    if max_prompt_audio_length is not None:
        inp["max_prompt_audio_length"] = max_prompt_audio_length
    response, error = api(CUSTOMIZATION, {"model": ENROLLMENT, "input": inp})
    result = voice_result(response, error)
    if result["ok"] and not result["voice"]:
        result.update(ok=False, error="响应没有音色ID，不自动重新创建；请用list_voices按prefix核对")
    result["target_model"] = result.get("target_model") or target_model
    if result["ok"]:
        result["next"] = "音色需审核，get_voice的status为OK后再用text_to_speech（model须与target_model一致）"
    return result


def design_voice(voice_prompt, preview_text, target_model, prefix, out_dir, mode, language=None,
                 sample_rate=24000, response_format="wav"):
    """voice-enrollment create_voice（设计）：创建音色并交付试听音频。"""
    if not (voice_prompt or "").strip() or len(voice_prompt) > 500 or not 15 <= len((preview_text or "").strip()) <= 200:
        return {"ok": False, "error": "voice_prompt须为1–500字符，preview_text须为15–200字符（仅中英文）"}
    if target_model not in DESIGN_TARGETS:
        return {"ok": False, "error": "target_model须为支持声音设计的HTTP合成模型：" + "、".join(DESIGN_TARGETS)}
    error = check_prefix(prefix)
    if not error and language not in (None, "zh", "en"):
        error = "声音设计language只支持zh或en，且须与preview_text语种一致"
    if not error and (sample_rate not in (16000, 24000, 48000) or response_format not in ("pcm", "wav", "mp3")):
        error = "sample_rate=16000/24000/48000，response_format=pcm/wav/mp3"
    if error:
        return {"ok": False, "error": error}
    inp = {"action": "create_voice", "target_model": target_model, "voice_prompt": voice_prompt,
           "preview_text": preview_text, "prefix": prefix}
    if language:
        inp["language_hints"] = [language]
    body = {"model": ENROLLMENT, "input": inp,
            "parameters": {"sample_rate": sample_rate, "response_format": response_format}}
    job = STORE.create("voice_preview", target_model, out_dir, mode, summary={"prefix": prefix})
    with STORE.processing(job):
        response, error = api(CUSTOMIZATION, body)
        result = voice_result(response, error)
        result["target_model"] = result.get("target_model") or target_model
        # Store the voice ID before delivering preview audio; download errors must not create another voice.
        job.update(request_id=result["request_id"], usage=result["usage"], result={k: v for k, v in result.items() if k != "output"})
        STORE.save(job)
        if error or not result["voice"]:
            definitive = bool(error) and (error.startswith(("HTTP 4", "未设置")) or bool(response and response.get("code")))
            job.update(error=error or "响应缺少音色ID，不自动重新创建；请用list_voices按prefix核对",
                       state="failed" if definitive else "unknown")
            STORE.save(job)
            return STORE.result(job)
        STORE.record_response(job, response)
        return deliver_preview(job, response)


def deliver_preview(job, response):
    output = response.get("output") or {}
    preview = output.get("preview_audio") or {}
    ext = {"mp3": "mp3", "pcm": "pcm"}.get(preview.get("response_format"), "wav")
    try:
        if preview.get("data"):
            STORE.add(job, f"preview.{ext}", data=base64.b64decode(preview["data"], validate=True))
        elif preview.get("url"):
            STORE.add(job, f"preview.{ext}", url=preview["url"])
    except (OSError, ValueError) as exc:
        job.update(state="unknown", error=f"音色已创建，试听音频留档失败：{exc}")
        STORE.save(job)
        return STORE.result(job)
    if job["artifacts"]:
        return STORE.deliver(job)
    job.update(state="delivered", error=None)
    STORE.save(job)
    return STORE.result(job)


def list_voices(kind="enrollment", page_index=0, page_size=20, prefix=None):
    """clone/design/cosyvoice 旧值统一映射到 voice-enrollment list_voice（复刻与设计共用同一列表）。"""
    if kind not in VOICE_KINDS or page_index < 0 or not 1 <= page_size <= 100:
        return {"ok": False, "error": "kind=enrollment（旧值clone/design/cosyvoice等价），page_index>=0，page_size=1–100"}
    inp = {"action": "list_voice", "page_index": page_index, "page_size": page_size}
    if prefix:
        inp["prefix"] = prefix
    response, error = api(CUSTOMIZATION, {"model": ENROLLMENT, "input": inp})
    output = (response or {}).get("output") or {}
    return {"ok": not error, "voices": output.get("voice_list") or [], "output": output, "kind": "enrollment",
            "request_id": (response or {}).get("request_id"), "usage": (response or {}).get("usage"), "error": error}


def get_voice(voice, kind="enrollment"):
    if kind not in VOICE_KINDS or not voice:
        return {"ok": False, "error": "需voice；kind=enrollment（旧值clone/design/cosyvoice等价）"}
    response, error = api(CUSTOMIZATION, {"model": ENROLLMENT, "input": {"action": "query_voice", "voice_id": voice}})
    result = voice_result(response, error)
    result["voice"] = voice
    result["status"] = result["output"].get("status")
    return result


def submit_video(body, out_dir, wait, mode, path="/api/v1/services/aigc/video-generation/video-synthesis", oss=False):
    from . import media
    if not 0 <= wait <= 90:
        return {"ok": False, "error": "wait范围为0–90秒"}
    job = STORE.create("video", body["model"], out_dir, mode, summary=body.get("parameters"))
    with STORE.processing(job):
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


def edit_video(video, prompt, images, resolution, audio_setting, watermark, seed, out_dir, wait, mode, parameters=None):
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
    try:
        merge_parameters(params, parameters)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return submit_video({"model": "happyhorse-1.0-video-edit", "input": {"prompt": prompt, "media": items},
                         "parameters": params}, out_dir, wait, mode, oss=oss)


def animate_portrait(image, audio, resolution, out_dir, wait, mode, parameters=None):
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
    try:
        merge_parameters(body["parameters"], parameters)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
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
    # 官方文档现所有rerank模型（含qwen3-rerank）统一走原生接口，input/parameters嵌套。
    body = {"model": model, "input": {"query": query, "documents": documents}, "parameters": params}
    response, error = api("/api/v1/services/rerank/text-rerank/text-rerank", body)
    result = response or {}
    return {"ok": not error, "model": model, "results": result.get("results") or (result.get("output") or {}).get("results"),
            "usage": result.get("usage"), "request_id": result.get("request_id"), "response": response, "error": error}


def get_job(job_id=None, task_id=None, wait=0, out_dir=None, mode="local"):
    """Local record; pending video tasks are polled and delivered without resubmission."""
    from . import media
    def adopt(task_id, wait):
        job = STORE.create("video", None, out_dir, mode)
        with STORE.processing(job):
            job.update(task_id=task_id, state="running")
            STORE.save(job)
            return media.poll_job(job, wait)
    return STORE.lookup(job_id, task_id, wait, {"video": media.poll_job}, adopt)


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
