"""Translation, Minutes, learning tables and signed speech console APIs.

Contracts: DoubaoVoice/MachineTranslationLargeModel-APIAccessDocumentation,
DoubaoVoice/DoubaoVoiceMinutes-APIAccessDocumentation,
DoubaoVoice/HotWordManagementAPIv10, DoubaoVoice/ReplacementWordAPIv11.
Console: api.volcengine.com (speech_saas_prod). No third-party signing dependency.
"""

import datetime
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import speech


def _failure(message):
    return {"ok": False, "response": None, "error": str(message)}


def _response(headers, raw, error, pending=False):
    if error:
        return _failure(error)
    try:
        data = json.loads(raw) if raw and raw.strip() else {}
    except (ValueError, TypeError):
        return _failure("服务返回了无效 JSON")
    if not isinstance(data, dict):
        return _failure("服务返回的 JSON 不是 object")
    status = (headers or {}).get("X-Api-Status-Code")
    code = data.get("code", data.get("Code", 0))
    top_error = (data.get("ResponseMetadata") or {}).get("Error")
    good_status = status in (None, "20000000", 20000000)
    if pending and status in ("20000001", "20000002"):
        good_status = True
    ok = good_status and code in speech.OK_CODES and not top_error and data.get("status", "success") != "error" and data.get("status", "success") != "failed"
    message = None if ok else (top_error or data.get("message") or data.get("Message")
                              or (headers or {}).get("X-Api-Message") or f"业务状态码 {status or code}")
    return {"ok": ok, "response": data, "error": message,
            "status_code": status or code, "logid": (headers or {}).get("X-Tt-Logid")}


def translate_text(text_list, target_language, source_language="", corpus=None, request=None):
    """Seed-X text translation; request preserves additional official fields."""
    body = dict(request or {})
    body.update(text_list=text_list, target_language=target_language)
    if source_language:
        body["source_language"] = source_language
    if corpus is not None:
        body["corpus"] = corpus
    if not isinstance(text_list, list) or not 1 <= len(text_list) <= 16:
        return _failure("text_list 必须包含 1 到 16 条文本")
    if not all(isinstance(t, str) and t.strip() for t in text_list) or not target_language:
        return _failure("待翻译文本和 target_language 不能为空")
    return _response(*speech.post("/api/v3/machine_translation/matx_translate", body, "volc.speech.mt"))


def minutes_submit(request, request_id=None):
    """Submit the complete documented Input/Params payload. Does not silently enable billing options."""
    try:
        offline = request["Input"]["Offline"]
        params = request["Params"]
        if not speech.is_remote(offline["FileURL"]):
            return _failure("妙记 FileURL 必须是 HTTP(S) URL")
        if offline["FileType"] not in ("audio", "video"):
            return _failure("FileType 只能是 audio 或 video")
        if params.get("AudioTranscriptionEnable") is not True:
            return _failure("妙记 AudioTranscriptionEnable 必须为 true")
        if not isinstance(params.get("AllActivate"), bool):
            return _failure("妙记必须明确指定 AllActivate 为 true 或 false（打包或按功能计费）")
        # AllActivate selects billing only; it does not turn on any feature.
        if not any(params.get(k) for k in ("TranslationEnable", "InformationExtractionEnabled",
                                          "SummarizationEnabled", "ChapterEnabled")):
            return _failure("妙记必须启用至少一个附加功能")
    except (KeyError, TypeError):
        return _failure("缺少妙记 Input.Offline 或 Params 参数")
    rid = request_id or str(uuid.uuid4())
    result = _response(*speech.post("/api/v3/auc/lark/submit", request, "volc.lark.minutes",
                                   {"X-Api-Request-Id": rid, "X-Api-Sequence": "-1"}, 5))
    result["request_id"] = rid
    result["task_id"] = ((result.get("response") or {}).get("Data") or {}).get("TaskID")
    return result


def minutes_query(task_id, request_id=None):
    if not task_id:
        return _failure("缺少 task_id")
    rid = request_id or task_id
    result = _response(*speech.post("/api/v3/auc/lark/query", {"TaskID": task_id}, "volc.lark.minutes",
                                   {"X-Api-Request-Id": rid}, 5), pending=True)
    data = ((result.get("response") or {}).get("Data") or {})
    result["state"] = data.get("Status")
    if data.get("Status") == "failed" or data.get("ErrCode", 0):
        result.update(ok=False, error=data.get("ErrMessage") or f"任务错误 {data.get('ErrCode')}")
    return result


HOTWORD_ACTIONS = {"ListBoostingTableLimits", "CreateBoostingTable", "CheckBoostingTableName",
                   "UpdateBoostingTable", "DeleteBoostingTable", "ListBoostingTable", "GetBoostingTable"}
CORRECT_ACTIONS = {"CreateCorrectTable", "CheckCorrectTableName", "UpdateCorrectTable",
                   "DeleteCorrectTable", "ListCorrectTable", "GetCorrectTable"}

# Known official versions. Explicit version is required for any other speech console action.
CONSOLE_VERSIONS = {action: "2025-05-20" for action in (
    "ListSpeakers", "ListBigModelTTSTimbres", "ListAPIKeys", "CreateAPIKey", "UpdateAPIKey", "DeleteAPIKey",
    "ServiceStatus", "PauseService", "ResumeService", "ActivateService", "TerminateService",
    "FormalizeResourcePacks", "ResourcePacksStatus", "AliasResourcePack", "OrderResourcePacks")}
CONSOLE_VERSIONS.update({action: "2025-05-21" for action in (
    "ListMegaTTSTrainStatus", "BatchListMegaTTSTrainStatus", "OrderAccessResourcePacks",
    "RenewAccessResourcePacks", "QuotaMonitoring", "UsageMonitoring", "TagResources", "UntagResources", "ListTagsForResources")})
CONSOLE_VERSIONS["ListMegaTTSByOrderID"] = "2023-11-07"


def signed_headers(payload, query, access_key, secret_key, region="cn-beijing", now=None, content_type="application/json; charset=UTF-8", method="POST"):
    """Volcengine HMAC-SHA256, signing the exact transmitted bytes."""
    timestamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    day = timestamp[:8]
    digest = hashlib.sha256(payload).hexdigest()
    host = "open.volcengineapi.com"
    canonical_headers = f"host:{host}\nx-content-sha256:{digest}\nx-date:{timestamp}\n"
    names = "host;x-content-sha256;x-date"
    canonical = f"{method}\n/\n{query}\n{canonical_headers}\n{names}\n{digest}"
    scope = f"{day}/{region}/speech_saas_prod/request"
    signing = f"HMAC-SHA256\n{timestamp}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    key = secret_key.encode()
    for value in (day, region, "speech_saas_prod", "request"):
        key = hmac.new(key, value.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, signing.encode(), hashlib.sha256).hexdigest()
    return {"Content-Type": content_type, "Host": host, "X-Date": timestamp,
            "X-Content-Sha256": digest,
            "Authorization": f"HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={names}, Signature={signature}"}


def _signed_post(action, version, parameters, payload=None, content_type="application/json; charset=UTF-8", region="cn-beijing", method="POST"):
    ak = os.environ.get("VOLC_ACCESS_KEY_ID")
    sk = os.environ.get("VOLC_SECRET_ACCESS_KEY")
    if not ak or not sk:
        return _failure("控制面 API 需要 VOLC_ACCESS_KEY_ID 和 VOLC_SECRET_ACCESS_KEY（火山引擎 IAM AK/SK）")
    query_parameters = {"Action": action, "Version": version}
    if method == "GET":
        query_parameters.update(parameters)
        payload = b""
    query = urllib.parse.urlencode(sorted(query_parameters.items()), doseq=True, quote_via=urllib.parse.quote)
    payload = payload if payload is not None else json.dumps(parameters, ensure_ascii=False).encode()
    req = urllib.request.Request("https://open.volcengineapi.com/?" + query, data=payload if method != "GET" else None, method=method,
                                 headers=signed_headers(payload, query, ak, sk, region, content_type=content_type, method=method))
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return _response(response.headers, response.read().decode(), None)
    except urllib.error.HTTPError as error:
        return _failure(speech.http_error(error))
    except (urllib.error.URLError, TimeoutError) as error:
        return _failure(f"请求失败：{error}")


def console_action(action, parameters, version=None):
    """Invoke a speech_saas_prod action with its complete official request body."""
    version = version or CONSOLE_VERSIONS.get(action)
    if not version or not action or not action.isalnum():
        return _failure("请提供官方 Action 和 Version")
    if version == "2021-08-30" and action in ("QuotaMonitoring", "UsageMonitoring"):
        return _signed_post(action, version, parameters, region="cn-north-1", method="GET")
    if action == "ListApplications":
        return _signed_post(action, version, parameters, region="cn-north-1", method="GET")
    return _signed_post(action, version, parameters)


def _multipart(parameters, content):
    boundary = "doubao-" + uuid.uuid4().hex
    parts = []
    for name, value in parameters.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="File"; filename="words.txt"\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n'.encode())
    parts.extend([content.encode(), f"\r\n--{boundary}--\r\n".encode()])
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def word_table(action, parameters, content=None, auth="api_key"):
    """Learning table CRUD; content is the literal documented TXT file contents.

    Hotword API-Key proxy is officially supported. Replacement table documentation
    currently specifies AK/SK only, so it uses the signed OpenAPI route.
    """
    if action not in HOTWORD_ACTIONS | CORRECT_ACTIONS:
        return _failure("不支持的词表 Action")
    version = "2022-08-30" if action in HOTWORD_ACTIONS else "2023-10-30"
    body = {**parameters, "Action": action, "Version": version}
    upload = action.startswith(("Create", "Update"))
    if upload and (not isinstance(content, str) or not content or len(content.encode()) >= 8 * 1024 * 1024):
        return _failure("创建或更新词表需要非空 content，UTF-8 大小必须小于 8 MB")
    payload, content_type = _multipart(body, content) if upload else (None, "application/json; charset=UTF-8")
    if auth == "api_key" and action in HOTWORD_ACTIONS:
        path = "/api/proxy/invoke?" + urllib.parse.urlencode({"Action": action})
        if not upload:
            return _response(*speech.post(path, body))
        key = os.environ.get("VOLC_SPEECH_API_KEY")
        if not key:
            return _failure("未设置 VOLC_SPEECH_API_KEY")
        req = urllib.request.Request(speech.HOST + path, data=payload,
                                     headers={"X-Api-Key": key, "Content-Type": content_type})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return _response(response.headers, response.read().decode(), None)
        except urllib.error.HTTPError as error:
            return _failure(speech.http_error(error))
        except (urllib.error.URLError, TimeoutError) as error:
            return _failure(f"请求失败：{error}")
    if auth not in ("api_key", "aksk"):
        return _failure("auth 只能是 api_key 或 aksk")
    return _signed_post(action, version, body, payload, content_type, "cn-north-1")
