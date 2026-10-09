"""Documented historical HTTP products using AppID / Access Token auth.

The allowlist is intentional: these endpoints do not use V3 API-Key auth.
"""

import copy
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import transport

from . import speech

DOC_ROOT = "https://docs.volcengine.com/docs/DoubaoVoice/"
OPERATIONS = {
    "subtitle_submit": ("POST", "/api/v1/vc/submit", "query", "Audiovideosubtitlegeneration"),
    "subtitle_query": ("GET", "/api/v1/vc/query", "query", "Audiovideosubtitlegeneration"),
    "alignment_submit": ("POST", "/api/v1/vc/ata/submit", "query", "Automaticsubtitletyping"),
    "alignment_query": ("GET", "/api/v1/vc/ata/query", "query", "Automaticsubtitletyping"),
    "tts": ("POST", "/api/v1/tts", "app", "HTTPinterfaceone-timecomposition-non-streaming"),
    "tts_async_submit": ("POST", "/api/v1/tts_async/submit", "flat", "APIinterfacedocumentation"),
    "tts_async_query": ("GET", "/api/v1/tts_async/query", "query", "APIinterfacedocumentation"),
    "tts_emotion_submit": ("POST", "/api/v1/tts_async_with_emotion/submit", "flat", "APIinterfacedocumentation"),
    "tts_emotion_query": ("GET", "/api/v1/tts_async_with_emotion/query", "query", "APIinterfacedocumentation"),
    "asr_submit": ("POST", "/api/v1/auc/submit", "app", "AudioFileRecognitionStandardEdition"),
    "asr_query": ("POST", "/api/v1/auc/query", "flat_token", "AudioFileRecognitionStandardEdition"),
}


def legacy_call(operation, request=None, parameters=None):
    """Submit/query once, preserving the full JSON body and query parameters.

    request is the HTTP JSON body, parameters the URL query. AppID defaults from
    VOLC_SPEECH_APP_ID and token from VOLC_SPEECH_ACCESS_TOKEN. Cluster IDs are
    deliberately supplied by the caller, as they depend on the enabled service.
    GET accepts request as query parameters as well for convenient task queries.
    Audio binary uploads are not synthesized; submit URL audio with {"url": ...}.
    """
    result = {"ok": False, "response": None, "error": None, "state": None,
              "task_id": None, "source": None, "logid": None}
    contract = OPERATIONS.get(operation)
    if not contract:
        result["error"] = "未知 legacy operation；可选：" + ", ".join(OPERATIONS)
        return result
    method, path, credential_shape, source = contract
    result["source"] = DOC_ROOT + source + "?lang=zh"
    if request is not None and not isinstance(request, dict) or parameters is not None and not isinstance(parameters, dict):
        result["error"] = "request 和 parameters 必须为 dict"
        return result
    body, query = copy.deepcopy(request or {}), copy.deepcopy(parameters or {})
    token = os.environ.get("VOLC_SPEECH_ACCESS_TOKEN")
    appid = os.environ.get("VOLC_SPEECH_APP_ID")
    if not token:
        result["error"] = "历史接口需要 VOLC_SPEECH_ACCESS_TOKEN（旧版控制台 Access Token）"
        return result
    if method == "GET":
        query = {**body, **query}
        body = {}
    if credential_shape == "query":
        if appid:
            query.setdefault("appid", appid)
        if not query.get("appid"):
            result["error"] = "缺少 appid 或 VOLC_SPEECH_APP_ID"
            return result
    elif credential_shape == "app":
        app = body.setdefault("app", {})
        if not isinstance(app, dict):
            result["error"] = "app 必须为 dict"
            return result
        if appid:
            app.setdefault("appid", appid)
        app.setdefault("token", token)
        if not app.get("appid") or not app.get("cluster"):
            result["error"] = "历史 TTS/ASR 必须提供 app.appid 和控制台的 app.cluster"
            return result
    else:
        if appid:
            body.setdefault("appid", appid)
        if not body.get("appid"):
            result["error"] = "缺少 appid 或 VOLC_SPEECH_APP_ID"
            return result
        if credential_shape == "flat_token":
            body.setdefault("token", token)
            if not body.get("cluster"):
                result["error"] = "历史 ASR query 必须提供控制台的 cluster"
                return result
    if operation.endswith("_query") and not (query.get("id") or query.get("task_id") or body.get("id")):
        result["error"] = "查询需要 id 或 task_id"
        return result
    if operation in ("subtitle_submit", "alignment_submit"):
        if not isinstance(body.get("url"), str) or not speech.is_remote(body["url"]):
            result["error"] = "字幕提交需要 request.url HTTP(S) 音频地址"
            return result
    if operation == "alignment_submit":
        if not (body.get("audio_text") or query.get("audio_text")):
            result["error"] = "字幕打轴需要 audio_text"
            return result
        if query.get("caption_type") not in ("speech", "singing"):
            result["error"] = "字幕打轴 parameters.caption_type 必须为 speech 或 singing"
            return result
        query.setdefault("caption_category", 2)
        query.setdefault("cluster", "ata_cluster")
    url = speech.HOST + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    payload = None if method == "GET" else json.dumps(body, ensure_ascii=False).encode()
    http_request = urllib.request.Request(url, data=payload, method=method,
        headers={"Authorization": "Bearer; " + token, "Content-Type": "application/json"})
    try:
        with transport.urlopen(http_request, timeout=60) as response:
            data = json.loads(response.read().decode())
            result["logid"] = response.headers.get("X-Tt-Logid")
        if not isinstance(data, dict):
            raise ValueError("JSON response 必须是 object")
        result["response"] = data
        detail = data.get("resp") or data
        if not isinstance(detail, dict):
            raise ValueError("resp 必须是 object")
        code = detail.get("code", 0)
        # Legacy ASR query and subtitles expose explicit pending statuses.
        pending = str(code) in ("2000", "2001")
        success_codes = ("3000",) if operation == "tts" else ("1000",) if operation.startswith("asr_") else ("0",)
        ok = str(code) in success_codes or pending
        task_status = data.get("task_status")
        if task_status == 2:
            ok = False
        task_id = detail.get("id") or data.get("task_id")
        submitted = ok and operation.endswith("_submit") and task_id and task_status != 1
        result.update(ok=ok, task_id=task_id,
                      state=("running" if pending or task_status == 0 or submitted else
                             "success" if ok else "failed"),
                      error=None if ok else detail.get("message") or f"业务错误 {code}")
    except urllib.error.HTTPError as error:
        result["error"] = speech.http_error(error)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        result["error"] = f"历史接口请求失败：{error}"
    return result
