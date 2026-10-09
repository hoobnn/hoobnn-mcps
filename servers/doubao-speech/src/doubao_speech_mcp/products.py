"""Doubao HTTP products; contracts verified against the official docs, 2026-10-09.

Request dictionaries preserve every documented optional field. Calls submit once
or query once: no hidden polling, retries, or purchases.
"""

import base64
import copy
import json
import uuid
from pathlib import Path

from . import speech

DOCS = {
    "tts_submit": "https://docs.volcengine.com/docs/DoubaoVoice/Tasksubmission?lang=zh",
    "tts_query": "https://docs.volcengine.com/docs/DoubaoVoice/Resultquery?lang=zh",
    "voice_clone": "https://docs.volcengine.com/docs/DoubaoVoice/tone-training-http?lang=zh",
    "voice_query": "https://docs.volcengine.com/docs/DoubaoVoice/tone-query-http?lang=zh",
    "voice_upgrade": "https://docs.volcengine.com/docs/DoubaoVoice/tone-upgrade-http?lang=zh",
    "voice_design": "https://docs.volcengine.com/docs/DoubaoVoice/SoundDesignAPI?lang=zh",
    "asr_standard": "https://docs.volcengine.com/docs/DoubaoVoice/LargemodelrecordingfilerecognitionstandardversionAPI?lang=zh",
    "asr_idle": "https://www.volcengine.com/docs/6561/1840838?lang=zh",
}
ASR_MODES = {
    "standard": ("/api/v3/auc/bigmodel", "volc.seedasr.auc"),
    "idle": ("/api/v3/auc/bigmodel/idle", "volc.bigasr.auc_idle"),
}


def raw_http(product, request, out_dir, resource_id=None):
    """Allowlisted raw contracts for the original three products; strip large audio blobs."""
    try:
        body = _body(request)
        if product == "tts":
            _required(body, "req_params.speaker", "req_params.text")
            path = "/api/v3/tts/unidirectional"
            resource_id = resource_id or speech.tts_resource(body["req_params"]["speaker"])
            config = body["req_params"].get("audio_params", {})
        elif product == "asr_flash":
            if not isinstance(body.get("audio"), dict) or not (body["audio"].get("url") or body["audio"].get("data")):
                raise speech.InputError("缺少 audio.url 或 audio.data")
            return _call("/api/v3/auc/bigmodel/recognize/flash", body,
                         resource_id or "volc.bigasr.auc_turbo", {"X-Api-Sequence": "-1"}, pending=True)
        elif product == "audio":
            _required(body, "model", "text_prompt")
            path, config = "/api/v3/tts/create", body.get("audio_config", {})
        else:
            raise speech.InputError("product 只能是 tts/asr_flash/audio")
        fmt = config.get("format", "mp3" if product == "tts" else "wav")
        if fmt not in {"mp3", "wav", "pcm", "ogg_opus"}:
            raise speech.InputError("不支持的音频 format")
        response_headers, raw, error = speech.post(path, body, resource_id,
                                                   {"X-Control-Require-Usage-Tokens-Return": "*"})
        if error:
            return _error(error)
        events = list(speech.json_stream(raw))
        audio = bytearray()
        for event in events:
            if event.get("code", 0) not in speech.OK_CODES:
                return _error(f"{event.get('code')}: {event.get('message')}")
            field = "data" if product == "tts" else "audio"
            if event.get(field):
                audio.extend(base64.b64decode(event.pop(field), validate=True))
        if not audio:
            return _error("没有返回音频")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / f"{product}-{uuid.uuid4().hex[:8]}.{'ogg' if fmt == 'ogg_opus' else fmt}"
        output.write_bytes(audio)
        return {"ok": True, "files": [str(output)], "audio_config": config,
                "response": events, "logid": (response_headers or {}).get("X-Tt-Logid"), "error": None}
    except (speech.InputError, ValueError, TypeError, OSError) as exc:
        return _error(exc)


def _body(request):
    if not isinstance(request, dict):
        raise speech.InputError("request 必须是 JSON object")
    return copy.deepcopy(request)


def _required(body, *paths):
    for path in paths:
        value = body
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise speech.InputError(f"缺少字符串字段 {path}")


def _speaker(body):
    _required(body, "speaker_id")
    if body["speaker_id"] == "custom_speaker_id":
        _required(body, "custom_speaker_id")


def _encoded_size(value, label, limit_mb=10):
    if not isinstance(value, str) or not value:
        raise speech.InputError(f"缺少 {label}")
    # Check the encoded length before allocating the decoded bytes.
    if len(value) > ((limit_mb * 1024 * 1024 + 2) // 3) * 4:
        raise speech.InputError(f"{label} 超过 {limit_mb}MB")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise speech.InputError(f"{label} 必须是纯 base64 编码") from exc
    if not data or len(data) > limit_mb * 1024 * 1024:
        raise speech.InputError(f"{label} 为空或超过 {limit_mb}MB")


def _error(exc):
    return {"ok": False, "error": str(exc), "data": None}


def _call(path, body, resource_id=None, headers=None, pending=False):
    response_headers, raw, error = speech.post(path, body, resource_id, headers)
    if error:
        return _error(error)
    response_headers = response_headers or {}
    try:
        data = json.loads(raw) if raw and raw.strip() else {}
        if not isinstance(data, dict):
            return _error("服务端返回的 JSON 不是 object")
    except (ValueError, TypeError):
        return _error("服务端返回了无效 JSON")
    code = response_headers.get("X-Api-Status-Code", data.get("code"))
    code = str(code) if code is not None else None
    message = response_headers.get("X-Api-Message", data.get("message", ""))
    accepted = {None, "0", "20000000"}
    if pending:
        # ASR status is conveyed in headers, including when its body is empty.
        accepted = {"20000000", "20000001", "20000002", "20000003"}
    ok = code in accepted
    result = {"ok": ok, "data": data, "code": code, "message": message,
              "logid": response_headers.get("X-Tt-Logid"),
              "error": None if ok else f"{code}: {message}"}
    if pending:
        result["status"] = {"20000000": "succeeded", "20000001": "running",
                            "20000002": "queued", "20000003": "silent"}.get(code, "failed")
    return result


def tts_submit(request, resource_id="seed-tts-2.0"):
    """Submit asynchronous long-text synthesis (up to 100000 characters)."""
    try:
        body = _body(request)
        _required(body, "req_params.text", "req_params.speaker", "req_params.audio_params.format")
        if len(body["req_params"]["text"]) > 100000:
            raise speech.InputError("长文本合成最多支持 100000 字符")
        if "unique_id" in body and (not isinstance(body["unique_id"], str)
                                    or not 20 <= len(body["unique_id"]) <= 64):
            raise speech.InputError("unique_id 长度必须在 20–64 字符之间")
        if resource_id not in {"seed-tts-2.0", "seed-icl-2.0"}:
            raise speech.InputError("长文本 resource_id 只能是 seed-tts-2.0 或 seed-icl-2.0")
        return _call("/api/v3/tts/submit", body, resource_id)
    except speech.InputError as exc:
        return _error(exc)


def tts_query(task_id, resource_id="seed-tts-2.0", request=None):
    """Query once; preserves audio URL, expiry, progress and word timestamps."""
    try:
        body = _body(request if request is not None else {})
        body["task_id"] = task_id
        _required(body, "task_id")
        if resource_id not in {"seed-tts-2.0", "seed-icl-2.0"}:
            raise speech.InputError("长文本 resource_id 只能是 seed-tts-2.0 或 seed-icl-2.0")
        return _call("/api/v3/tts/query", body, resource_id)
    except speech.InputError as exc:
        return _error(exc)


def voice_clone(request, audio_file=None):
    """Register/retrain a voice; audio_file optionally builds audio.data/format."""
    try:
        body = _body(request)
        _speaker(body)
        if audio_file:
            path = speech.local_file(audio_file, 10)
            audio = body.setdefault("audio", {})
            if not isinstance(audio, dict):
                raise speech.InputError("audio 必须是 object")
            audio.update(data=speech.b64(path))
            audio.setdefault("format", path.suffix.lower().lstrip("."))
        _required(body, "audio.data")
        audio = body["audio"]
        _encoded_size(audio["data"], "audio.data")
        if "format" in audio and audio["format"] not in {"wav", "mp3", "ogg", "m4a", "aac", "pcm"}:
            raise speech.InputError("audio.format 只支持 wav/mp3/ogg/m4a/aac/pcm")
        extra = body.get("extra_params", {})
        if not isinstance(extra, dict):
            raise speech.InputError("extra_params 必须是 object")
        demo = extra.get("demo_text")
        if demo is not None and (not isinstance(demo, str) or not 4 <= len(demo) <= 300):
            raise speech.InputError("extra_params.demo_text 必须是 4–300 字符")
        return _call("/api/v3/tts/voice_clone", body)
    except (speech.InputError, OSError) as exc:
        return _error(exc)


def voice_query(request):
    """Query registered voice state and available training count."""
    try:
        body = _body(request)
        _speaker(body)
        return _call("/api/v3/tts/get_voice", body)
    except speech.InputError as exc:
        return _error(exc)


def voice_upgrade(request):
    """Upgrade an existing registered voice using the documented V3 endpoint."""
    try:
        body = _body(request)
        _speaker(body)
        return _call("/api/v3/tts/upgrade_voice", body)
    except speech.InputError as exc:
        return _error(exc)


def voice_design(request, image_file=None):
    """Design a voice using text/image prompts and return its preview URL."""
    try:
        body = _body(request)
        _speaker(body)
        _required(body, "text")
        if len(body["text"]) > 300:
            raise speech.InputError("试听 text 最多支持 300 字符")
        prompt = body.setdefault("prompt", {})
        if not isinstance(prompt, dict):
            raise speech.InputError("prompt 必须是 object")
        if image_file:
            path = speech.local_file(image_file, 10)
            image = prompt.setdefault("image_prompt", {})
            if not isinstance(image, dict):
                raise speech.InputError("prompt.image_prompt 必须是 object")
            image["image_bytes"] = speech.b64(path)
        text = prompt.get("text_prompt", "")
        image = prompt.get("image_prompt", {})
        if not isinstance(text, str) or len(text) > 200:
            raise speech.InputError("prompt.text_prompt 必须是最多 200 字符的字符串")
        if not isinstance(image, dict):
            raise speech.InputError("prompt.image_prompt 必须是 object")
        if image.get("image_bytes"):
            _encoded_size(image["image_bytes"], "prompt.image_prompt.image_bytes")
        if image.get("image_url") and (not isinstance(image["image_url"], str)
                                       or not speech.is_remote(image["image_url"])):
            raise speech.InputError("prompt.image_prompt.image_url 必须是 HTTP(S) URL")
        if not (text.strip() or image.get("image_bytes") or image.get("image_url")):
            raise speech.InputError("prompt 需要 text_prompt 或 image_prompt")
        return _call("/api/v3/tts/voice_design", body)
    except (speech.InputError, OSError) as exc:
        return _error(exc)


def _asr_mode(mode, resource_id):
    if mode not in ASR_MODES:
        raise speech.InputError("mode 只能是 standard 或 idle")
    path, default = ASR_MODES[mode]
    return path, resource_id or default


def asr_submit(request, mode="standard", resource_id=None, task_id=None):
    """Submit URL-based standard/idle recognition; returns client task ID."""
    try:
        body = _body(request)
        _required(body, "audio.url", "request.model_name")
        if not speech.is_remote(body["audio"]["url"]):
            raise speech.InputError("异步 ASR audio.url 必须是可下载的 HTTP(S) URL")
        if body["request"]["model_name"] != "bigmodel":
            raise speech.InputError("request.model_name 必须是 bigmodel")
        path, resource = _asr_mode(mode, resource_id)
        task_id = task_id or str(uuid.uuid4())
        _required({"task_id": task_id}, "task_id")
        result = _call(path + "/submit", body, resource,
                       {"X-Api-Request-Id": task_id, "X-Api-Sequence": "-1"}, pending=True)
        result.update(task_id=task_id, mode=mode, resource_id=resource)
        if result.get("ok"):
            result["status"] = "submitted"
        return result
    except speech.InputError as exc:
        return _error(exc)


def asr_query(task_id, mode="standard", resource_id=None, request=None, logid=None):
    """Query once using the original task ID and resource, preserving pending states."""
    try:
        _required({"task_id": task_id}, "task_id")
        path, resource = _asr_mode(mode, resource_id)
        body = _body(request if request is not None else {})
        headers = {"X-Api-Request-Id": task_id}
        if logid:
            headers["X-Tt-Logid"] = logid
        result = _call(path + "/query", body, resource, headers, pending=True)
        result.update(task_id=task_id, mode=mode, resource_id=resource)
        return result
    except speech.InputError as exc:
        return _error(exc)
