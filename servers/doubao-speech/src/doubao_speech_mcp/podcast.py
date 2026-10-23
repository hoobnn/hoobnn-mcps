"""Podcast HTTP SSE: terminal status and complete-round resume boundaries."""

import base64
import copy
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import speech, transport


def validate_request(request):
    body = copy.deepcopy(request)
    if not isinstance(body, dict):
        raise speech.InputError("request 必须是 object")
    action = body.get("action", 0)
    info = body.get("input_info", {})
    if not isinstance(info, dict):
        raise speech.InputError("input_info 必须是 object")
    if type(action) is not int or action not in {0, 3, 4}:
        raise speech.InputError("action 只能是 0/3/4")
    if action == 0 and not (body.get("input_text") or info.get("input_url")):
        raise speech.InputError("action=0 需要 input_text 或 input_info.input_url")
    if action == 4 and not body.get("prompt_text"):
        raise speech.InputError("action=4 需要 prompt_text")
    if action == 3:
        texts = body.get("nlp_texts")
        if not isinstance(texts, list) or not texts or any(
            not isinstance(item, dict) or not isinstance(item.get("text"), str)
            or not 1 <= len(item["text"]) <= 300 or not item.get("speaker") for item in texts
        ):
            raise speech.InputError("nlp_texts 每轮需要 speaker 和 1–300 字符 text")
        if sum(len(item["text"]) for item in texts) > 10000:
            raise speech.InputError("nlp_texts 总长超过 10000 字符")
    speakers = body.get("speaker_info", {})
    if not isinstance(speakers, dict):
        raise speech.InputError("speaker_info 必须是 object")
    if "speakers" in speakers and (not isinstance(speakers["speakers"], list)
            or len(speakers["speakers"]) != 2
            or any(not isinstance(value, str) or not value.strip() for value in speakers["speakers"])):
        raise speech.InputError("speaker_info.speakers 必须包含两个音色")
    config = body.setdefault("audio_config", {"format": "mp3", "sample_rate": 24000})
    if not isinstance(config, dict) or config.get("format", "pcm") not in {"mp3", "pcm", "aac", "ogg_opus"}:
        raise speech.InputError("audio_config.format 只能是 mp3/pcm/aac/ogg_opus")
    if config.get("sample_rate", 24000) not in {16000, 24000, 48000}:
        raise speech.InputError("audio_config.sample_rate 只能是 16000/24000/48000")
    retry = body.get("retry_info", {})
    if not isinstance(retry, dict):
        raise speech.InputError("retry_info 必须是 object")
    if retry and (not isinstance(retry.get("retry_task_id"), str) or not retry["retry_task_id"].strip()
            or type(retry.get("last_finished_round_id")) is not int or retry["last_finished_round_id"] < 0):
        raise speech.InputError("retry_info 需要原 retry_task_id 和最后一个完整轮次的 last_finished_round_id")
    return body


def sse_events(response):
    """Dispatch only blank-line-terminated SSE messages; ignore comments/id/retry."""
    event, data, size = "", [], 0
    first = True
    for raw in response:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if first:
            text = text.removeprefix("\ufeff")
            first = False
        # The HTTP facade yields LF lines. splitlines also handles CR-only SSE.
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if text.endswith(("\r", "\n")):
            lines.pop()  # The line terminator itself is not a second blank line.
        for line in lines:
            if not line:
                if data:
                    if not event.isdecimal():
                        raise speech.InputError("播客 SSE 缺少数字 event 类型")
                    payload = json.loads("\n".join(data))
                    if not isinstance(payload, dict):
                        raise speech.InputError("播客 SSE data 必须是 JSON object")
                    yield int(event), payload
                event, data, size = "", [], 0
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if field == "event":
                event = value
            elif field == "data":
                data.append(value)
                size += len(value)
                if size > 16 * 1024 * 1024:
                    raise speech.InputError("播客 SSE 单条消息超过 16MB")
    # An unfinished event at EOF is deliberately not dispatched.


def preserve(result, body, out_dir, request_id, audio, complete, current, rounds):
    """Commit immutable audio snapshots before advancing the durable resume ID.

    A failed write leaves the old receipt pointing at its old complete-round file.
    Receipts preserve the original request without credentials, even on cancellation.
    """
    config = body["audio_config"]
    fmt = config.get("format", "pcm")
    name = "podcast-" + request_id  # Untrusted remote IDs never become paths.
    candidate = copy.deepcopy(result)
    previous = list(result["files"])
    unfinished = bytes(audio[complete:]) if not result["ok"] else b""
    kept = audio if result["ok"] else audio[:complete]
    boundary = rounds[-1]["round_id"] if rounds else body.get("retry_info", {}).get("last_finished_round_id")
    candidate["received_last_finished_round_id"] = boundary
    saved = True
    audio_saved = not kept
    if kept:
        suffix = f".through-{boundary}.partial" if not result["ok"] else ""
        path = Path(out_dir) / f"{name}{suffix}.{fmt}"
        try:
            speech._atomic_bytes(path, kept)
            candidate["files"] = [str(path)]
            candidate["audio_config"] = config
            audio_saved = True
        except (OSError, TypeError) as exc:
            saved = candidate["ok"] = False
            candidate["state"] = "failed"
            candidate["error"] = f"{candidate['error'] + '; ' if candidate['error'] else ''}音频保存失败：{exc}"
    if audio_saved:
        candidate["rounds"] = copy.deepcopy(rounds)
        candidate["last_finished_round_id"] = boundary
        if candidate.get("task_id") is not None and boundary is not None:
            candidate["retry_info"] = {"retry_task_id": candidate["task_id"], "last_finished_round_id": boundary}
    if current is not None:
        candidate["unfinished_round"] = copy.deepcopy(current)
    if unfinished:
        candidate["discarded_bytes"] = len(unfinished)
        diagnostic = Path(out_dir) / f"{name}.unfinished-round.diagnostic-not-for-resume.{fmt}"
        try:
            speech._atomic_bytes(diagnostic, unfinished)
            candidate["diagnostic_file"] = str(diagnostic)
        except (OSError, TypeError) as exc:
            saved = candidate["ok"] = False
            candidate["state"] = "failed"
            candidate["error"] = f"{candidate['error'] + '; ' if candidate['error'] else ''}诊断音频保存失败：{exc}"
    receipt = Path(out_dir) / f"{name}.progress.json"
    try:
        content = {"format_version": 1, **candidate, "request": body, "progress_file": str(receipt)}
        speech._atomic_bytes(receipt, json.dumps(content, ensure_ascii=False, indent=2).encode())
        candidate["progress_file"] = str(receipt)
        # The new receipt is durable; its predecessor's immutable snapshot is obsolete.
        obsolete = set(previous) | {str(path) for path in Path(out_dir).glob(f"{name}.through-*.partial.{fmt}")}
        for old in obsolete:
            if old not in candidate["files"]:
                try:
                    Path(old).unlink(missing_ok=True)
                except OSError:
                    pass
    except (OSError, TypeError) as exc:
        saved = candidate["ok"] = False
        candidate["state"] = "failed"
        candidate["error"] = f"{candidate['error'] + '; ' if candidate['error'] else ''}续传记录保存失败：{exc}"
    result.clear()
    result.update(candidate)
    return saved


def generate(request, out_dir):
    result = {"ok": False, "files": [], "rounds": [], "usage": [], "error": None,
              "state": "incomplete", "transport": "sse", "last_finished_round_id": None}
    audio, complete, current = bytearray(), 0, None
    rounds = []
    body, dispatched = None, False
    request_id = str(uuid.uuid4())
    result["request_id"] = request_id
    try:
        body = validate_request(request)
        retry = body.get("retry_info", {})
        if retry:
            result["task_id"] = retry["retry_task_id"]
            result["last_finished_round_id"] = retry["last_finished_round_id"]
        key = os.environ.get("VOLC_SPEECH_API_KEY")
        if not key:
            raise speech.InputError("未设置 VOLC_SPEECH_API_KEY")
        req = urllib.request.Request(speech.HOST + "/api/v3/podcast/sse",
            data=json.dumps(body, ensure_ascii=False).encode(), headers={
                "Content-Type": "application/json", "Accept": "text/event-stream",
                "X-Api-Key": key, "X-Api-Resource-Id": "volc.service_type.10050",
                "X-Api-Request-Id": request_id})
        if not preserve(result, body, out_dir, request_id, audio, complete, current, rounds):
            raise speech.InputError(result["error"])
        dispatched = True
        operation = transport.operation.get()
        # Respect the MCP total budget; a 300 s transport cap would truncate long
        # podcasts even when MCP_TOOL_TIMEOUT_SEC has been raised by the client.
        timeout = operation.remaining() if operation is not None else 3600
        with transport.urlopen(req, timeout=timeout) as response:
            result["logid"] = response.headers.get("X-Tt-Logid")
            result["request_id"] = response.headers.get("X-Api-Request-Id", request_id)
            if response.status != 200 or response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "text/event-stream":
                raise speech.InputError("播客需要 HTTP 200 和 text/event-stream 响应")
            terminal = False
            for event, message in sse_events(response):
                payload = message.get("payload") or {}
                if not isinstance(payload, dict):
                    raise speech.InputError("播客 payload 必须是 object")
                if event in {151, 152, 153}:
                    result.update(terminal_event=event, code=message.get("code"), message=message.get("message"))
                    if event == 151:
                        result.update(canceled=True, state="canceled")
                        raise speech.InputError(f"播客会话取消（151）：{message.get('message', '')}")
                    if event == 153 or message.get("code") != 20000000:
                        result["state"] = "failed"
                        raise speech.InputError(f"播客失败（{event}/{message.get('code')}）：{message.get('message', '')}")
                    if not result.get("session_id") or current is not None:
                        raise speech.InputError("播客结束但会话标识或完整轮次结束事件缺失")
                    terminal = True
                    break
                if message.get("code", 0) not in {0, 20000000}:
                    result.update(code=message.get("code"), state="failed")
                    raise speech.InputError(f"播客业务错误：{message.get('code')} {message.get('message', '')}")
                if event == 150:
                    sid = message.get("session_id")
                    if not isinstance(sid, str) or not sid:
                        raise speech.InputError("SessionStarted 缺少 session_id")
                    result["session_id"] = sid
                    result.setdefault("task_id", sid)  # Resume always uses the FIRST session ID.
                    if not preserve(result, body, out_dir, request_id, audio, complete, current, rounds):
                        raise speech.InputError(result["error"])
                elif event == 360:
                    if current is not None or type(payload.get("round_id")) is not int:
                        raise speech.InputError("播客轮次开始缺少 round_id 或上一轮未结束")
                    current = dict(payload)
                elif event == 361:
                    if current is None or not result.get("session_id"):
                        raise speech.InputError("播客音频出现在会话/轮次开始之前")
                    encoded = message.get("data")
                    if not isinstance(encoded, str):
                        raise speech.InputError("播客音频 data 必须是 Base64 字符串")
                    audio.extend(base64.b64decode(encoded, validate=True))
                elif event == 362:
                    if current is None or payload.get("round_id", current["round_id"]) != current["round_id"]:
                        raise speech.InputError("播客轮次结束与开始不匹配")
                    if payload.get("is_error"):
                        result["state"] = "failed"
                        raise speech.InputError(payload.get("error_msg", "播客轮次失败"))
                    current["timing"] = payload
                    rounds.append(current)
                    complete, current = len(audio), None
                    if not preserve(result, body, out_dir, request_id, audio, complete, current, rounds):
                        raise speech.InputError(result["error"])
                elif event == 363:
                    result["meta"] = payload
                elif event == 154:
                    result["usage"].append(payload)
            if not terminal:
                raise speech.InputError("播客 SSE 在成功的 152 结束事件之前断开，结果不完整")
        if not audio and not body.get("input_info", {}).get("only_nlp_text"):
            raise speech.InputError("播客结束但没有音频")
        result.update(ok=True, state="succeeded")
    except urllib.error.HTTPError as exc:
        result.update(state="failed", error=speech.http_error(exc))
    except transport.OperationCancelled:
        result.update(state="incomplete", error="MCP 请求取消；已保留真实会话标识和完整轮次，未重新提交")
        raise
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, TimeoutError) as exc:
        result["error"] = str(exc) or type(exc).__name__
    finally:
        if dispatched:
            preserve(result, body, out_dir, request_id, audio, complete, current, rounds)
    return result
