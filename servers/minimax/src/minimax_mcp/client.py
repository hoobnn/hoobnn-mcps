"""MiniMax V1/V2 JSON and multipart transport. Never retry a paid request."""
import json
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import transport


class APIError(ValueError):
    def __init__(self, message, code=None, request_id=None, definitive=True):
        super().__init__(message)
        self.code, self.request_id, self.definitive = code, request_id, definitive


def configuration():
    host = os.environ.get("MINIMAX_API_HOST", "https://api.minimax.cn").rstrip("/")
    parsed = urllib.parse.urlsplit(host)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path):
        raise ValueError("MINIMAX_API_HOST 必须是 HTTPS API 域名，不含路径或凭据")
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not key:
        raise ValueError("未设置 MINIMAX_API_KEY；须与 MINIMAX_API_HOST 所属区域一致")
    return host, key


def identifier(value):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
        raise ValueError("无效的 task_id / file_id")
    return value


def request(path, body=None, *, method=None, query=None, raw=None, content_type=None):
    host, key = configuration()
    url = host + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    data = raw if raw is not None else (json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
    if data is not None and len(data) > 64 * 1024 * 1024:
        raise ValueError("请求体超过 64 MB；请改用公网 URL 或 upload_file 返回的 mm_file://")
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = content_type or "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data is not None else "GET"))
    try:
        with transport.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read())
        except (ValueError, OSError):
            error = {}
        detail = error.get("error") or error.get("base_resp") or {}
        message = detail.get("message", detail.get("status_msg", "MiniMax HTTP error")) if isinstance(detail, dict) else str(detail)
        raise APIError(f"HTTP {exc.code}: {message}".replace(key, "[redacted]"), exc.code,
                       error.get("request_id"), definitive=exc.code < 500) from None
    if not isinstance(result, dict):
        raise ValueError("MiniMax 响应不是 JSON object")
    base = result.get("base_resp") or {}
    if base.get("status_code") not in (None, 0, "0") or result.get("error"):
        detail = result.get("error") or base
        message = detail.get("message", detail.get("status_msg", "MiniMax API error")) if isinstance(detail, dict) else str(detail)
        code = base.get("status_code") or (detail.get("type") if isinstance(detail, dict) else None)
        raise APIError(str(message).replace(key, "[redacted]"), code, result.get("request_id"),
                       definitive=code not in (1000, 1001, 1013, "1000", "1001", "1013"))
    return result


FORMATS = {"image": {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"},
           "video": {".mp4", ".mov"}, "audio": {".mp3", ".wav"}}
LIMITS = {"image": 30, "video": 50, "audio": 15}


def local_media(value, kind):
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError("本地素材须为存在的绝对文件路径")
    if path.suffix.lower() not in FORMATS[kind]:
        raise ValueError(f"不支持的 {kind} 格式: {path.suffix}")
    if not 0 < path.stat().st_size <= LIMITS[kind] * 1024 * 1024:
        raise ValueError(f"{kind} 文件须非空且不超过 {LIMITS[kind]} MB")
    return path


def upload(file, purpose="video_generation_input"):
    path = Path(file).expanduser()
    if purpose == "video_generation_input":
        kind = next((kind for kind, suffixes in FORMATS.items() if path.suffix.lower() in suffixes), None)
        if not kind:
            raise ValueError("不支持的视频生成素材格式")
        path = local_media(file, kind)
    elif purpose in ("voice_clone", "prompt_audio"):
        if not path.is_absolute() or not path.is_file() or path.suffix.lower() not in {".mp3", ".m4a", ".wav"}:
            raise ValueError("音色素材须为本地 mp3/m4a/wav 绝对路径")
        if not 0 < path.stat().st_size <= 20 * 1024 * 1024:
            raise ValueError("音色素材须非空且不超过20 MB")
    else:
        raise ValueError("purpose 支持 video_generation_input / voice_clone / prompt_audio")
    boundary = "minimax-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # Generated filename avoids header injection while retaining a meaningful extension.
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\n{purpose}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"input{path.suffix.lower()}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode()
    body = head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    response = request("/v1/files/upload", raw=body, content_type=f"multipart/form-data; boundary={boundary}")
    file_id = response.get("file", {}).get("file_id")
    if not file_id:
        raise ValueError("上传响应缺少 file.file_id")
    return {"ok": True, "file_id": str(file_id), "uri": "mm_file://" + str(file_id), "file": response["file"]}
