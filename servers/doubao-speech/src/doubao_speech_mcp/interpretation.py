"""Doubao simultaneous interpretation, using the official AST protobuf demo.

Source: https://docs.volcengine.com/docs/DoubaoVoice/SimultaneousInterpretation20APIAccessDocumentation?lang=zh
The source WAV container is removed before 80ms PCM packets are sent.
"""

import asyncio
import base64
import copy
import os
import uuid
import wave
from pathlib import Path

import websockets
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
from google.protobuf.message import DecodeError

from . import speech
from ._ast.ast_service_pb2 import TranslateRequest, TranslateResponse
from ._ast.events_pb2 import Type

ENDPOINT = "wss://openspeech.bytedance.com/api/v4/ast/v2/translate"
RESOURCE_ID = "volc.service_type.10053"
CHUNK_BYTES = 2560  # 80ms, 16000Hz, 16bit, mono


def encode_request(request):
    """Serialize a complete official TranslateRequest dictionary to protobuf.

    source_audio.binary_data accepts Python bytes or a protobuf JSON base64 string.
    Unknown fields fail rather than disappearing from the request.
    """
    if not isinstance(request, dict):
        raise speech.InputError("request 必须是 JSON object")
    body = copy.deepcopy(request)
    for name in ("source_audio", "target_audio"):
        audio = body.get(name)
        if isinstance(audio, dict) and isinstance(audio.get("binary_data"), bytes):
            audio["binary_data"] = base64.b64encode(audio["binary_data"]).decode("ascii")
    try:
        return ParseDict(body, TranslateRequest()).SerializeToString()
    except (ParseError, TypeError, ValueError) as exc:
        raise speech.InputError(f"同传 protobuf 请求字段无效：{exc}") from exc


def decode_response(raw):
    """Decode the official TranslateResponse, retaining raw audio bytes and billing."""
    if not isinstance(raw, bytes):
        raise speech.InputError("同传接口应返回 binary protobuf frame")
    message = TranslateResponse()
    try:
        message.ParseFromString(raw)
    except DecodeError as exc:
        raise speech.InputError("同传接口返回了无效 protobuf") from exc
    body = MessageToDict(message, preserving_proto_field_name=True,
                         use_integers_for_enums=True)
    body.update(event=message.event, text=message.text, data=message.data,
                start_time=message.start_time, end_time=message.end_time,
                spk_chg=message.spk_chg)
    try:
        body["event_name"] = Type.Name(message.event)
    except ValueError:
        body["event_name"] = str(message.event)
    return body


def read_pcm(audio):
    """Read 16kHz/16bit/mono WAV or raw PCM; never transmit a WAV header."""
    path = speech.local_file(audio, 100)
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as source:
                if (source.getframerate(), source.getsampwidth(), source.getnchannels(),
                        source.getcomptype()) != (16000, 2, 1, "NONE"):
                    raise speech.InputError("同传 WAV 必须是 16000Hz、16bit、单声道 PCM")
                data = source.readframes(source.getnframes())
        except (wave.Error, EOFError) as exc:
            raise speech.InputError(f"无法读取 WAV：{exc}") from exc
    elif path.suffix.lower() == ".pcm":
        data = path.read_bytes()
    else:
        raise speech.InputError("同传 audio 仅支持本地 .wav 或 .pcm")
    if not data or len(data) % 2:
        raise speech.InputError("音频为空或不是完整的 16bit PCM 采样")
    return data


def _start_request(request, session_id, source_language, target_language, mode):
    if mode not in {"s2t", "s2s"}:
        raise speech.InputError("mode 只能是 s2t 或 s2s")
    if not isinstance(source_language, str) or not source_language.strip():
        raise speech.InputError("缺少 source_language")
    if not isinstance(target_language, str) or not target_language.strip():
        raise speech.InputError("缺少 target_language")
    if request is not None and not isinstance(request, dict):
        raise speech.InputError("request 必须是 JSON object")
    body = copy.deepcopy(request or {})
    for name in ("request_meta", "source_audio", "request", "target_audio"):
        if name in body and not isinstance(body[name], dict):
            raise speech.InputError(f"{name} 必须是 object")
    body.setdefault("request_meta", {})["SessionID"] = session_id
    body["event"] = Type.StartSession
    body.setdefault("user", {"uid": "doubao_speech_mcp"})
    # The uploaded source is validated by read_pcm; enforce its actual metadata.
    body.setdefault("source_audio", {}).update(format="wav", codec="raw", rate=16000, bits=16, channel=1)
    for name in ("binary_data", "data", "url"):
        body["source_audio"].pop(name, None)
    body.setdefault("request", {}).update(mode=mode, source_language=source_language,
                                          target_language=target_language)
    if mode == "s2s":
        target = body.setdefault("target_audio", {})
        target.setdefault("format", "pcm")
        target.setdefault("rate", 48000 if target["format"] == "ogg_opus" else 16000)
        target.setdefault("bits", 32 if target["rate"] == 24000 or target["format"] == "ogg_opus" else 16)
        target.setdefault("channel", 1)
        fmt, rate = target["format"], target["rate"]
        if fmt not in {"pcm", "ogg_opus"} or (fmt == "pcm" and rate not in {16000, 24000}) or (fmt == "ogg_opus" and rate != 48000):
            raise speech.InputError("target_audio 支持 pcm(16000/24000Hz) 或 ogg_opus(48000Hz)")
        if target["channel"] != 1 or (fmt == "pcm" and target["bits"] != (32 if rate == 24000 else 16)):
            raise speech.InputError("target_audio 必须单声道；pcm16000 使用16bit，pcm24000 使用float32")
    return body


def _save_audio(data, target, out_dir, session_id):
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    fmt, rate = target["format"], target["rate"]
    if fmt == "pcm" and len(data) % (4 if rate == 24000 else 2):
        raise speech.InputError("服务端返回的 PCM 音频采样不完整")
    if fmt == "pcm" and rate == 16000:
        path = directory / f"interpretation_{session_id}.wav"
        def write(handle):
            with wave.open(handle, "wb") as dest:
                dest.setnchannels(1)
                dest.setsampwidth(2)
                dest.setframerate(rate)
                dest.writeframes(data)
        speech._atomic_write(path, write)
    else:
        path = directory / f"interpretation_{session_id}.{'ogg' if fmt == 'ogg_opus' else 'pcm'}"
        speech._atomic_bytes(path, data)
    return str(path)


async def _receive_response(connection):
    return await asyncio.to_thread(decode_response, await connection.recv())


async def interpret_audio(audio, source_language, target_language, mode="s2t",
                          request=None, out_dir=Path("."), timeout=60):
    """Translate one local recording, returning source/translation segments and usage.

    timeout limits each receive wait; the entire session is bounded by audio
    duration + twice timeout. Server failure cancels the sender immediately.
    Raw target pcm24000 output is float32; its metadata is included in the result.
    """
    result = {"ok": False, "error": None, "source_text": "", "translation_text": "",
              "source_segments": [], "translation_segments": [], "usage": [], "files": [],
              "session_id": str(uuid.uuid4()), "logid": None}
    sender = None
    try:
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
            raise speech.InputError("timeout 必须在 0–600 秒之间")
        pcm = await asyncio.wait_for(asyncio.to_thread(read_pcm, audio), timeout)
        start = _start_request(request, result["session_id"], source_language, target_language, mode)
        start_bytes = await asyncio.to_thread(encode_request, start)  # Validate before connecting or billing.
        key = os.environ.get("VOLC_SPEECH_API_KEY")
        if not key:
            raise speech.InputError("未设置 VOLC_SPEECH_API_KEY")
        headers = {"X-Api-Key": key, "X-Api-Resource-Id": RESOURCE_ID,
                   "X-Api-Connect-Id": str(uuid.uuid4())}
        async with websockets.connect(ENDPOINT, additional_headers=headers,
                                      open_timeout=timeout, close_timeout=5,
                                      max_size=16 * 1024 * 1024, ping_interval=None) as connection:
            response = getattr(connection, "response", None)
            if response is not None:
                result["logid"] = response.headers.get("X-Tt-Logid")
            await connection.send(start_bytes)
            started = await asyncio.wait_for(
                _receive_response(connection), timeout)
            if started["event"] != Type.SessionStarted:
                raise speech.InputError(f"同传启动失败：{started['event_name']} "
                                        f"{started.get('response_meta', {}).get('Message', '')}")

            async def send_audio():
                loop = asyncio.get_running_loop()
                started_at = loop.time()
                for index, offset in enumerate(range(0, len(pcm), CHUNK_BYTES)):
                    await connection.send(encode_request({"request_meta": {"SessionID": result["session_id"]},
                        "event": Type.TaskRequest, "source_audio": {"binary_data": pcm[offset:offset + CHUNK_BYTES]}}))
                    # Avoid accumulated drift while preserving the requested realtime pace.
                    await asyncio.sleep(max(0, started_at + (index + 1) * .08 - loop.time()))
                await connection.send(encode_request({"request_meta": {"SessionID": result["session_id"]},
                                                       "event": Type.FinishSession}))

            received_audio = bytearray()
            active = {"source": "", "translation": ""}
            segment_meta = {"source": {}, "translation": {}}

            def append_segment(kind, event):
                # End events contain the finalized sentence: prefer that over
                # intermediate text packets, which may have been revised.
                text = event["text"] or active[kind]
                if text:
                    result[kind + "_segments"].append({"text": text,
                        "start_ms": event["start_time"] or segment_meta[kind].get("start_ms", 0),
                        "end_ms": event["end_time"],
                        "speaker_changed": segment_meta[kind].get("speaker_changed", event["spk_chg"]),
                        **{key: event[key] for key in ("detected_language", "language_confidence", "speaker_id")
                           if key in event}})
                active[kind] = ""
                segment_meta[kind] = {}

            async def receive_all():
                while True:
                    recv_task = asyncio.create_task(connection.recv())
                    try:
                        # Observe send failure without waiting for the receive timeout.
                        watching = {recv_task}
                        if not sender.done():
                            watching.add(sender)
                        done, _ = await asyncio.wait(watching, timeout=timeout,
                                                     return_when=asyncio.FIRST_COMPLETED)
                        if not done:
                            raise TimeoutError("同传响应超时")
                        if sender in done:
                            sender.result()
                        if recv_task not in done:
                            raw = await asyncio.wait_for(recv_task, timeout)
                        else:
                            raw = recv_task.result()
                    finally:
                        if not recv_task.done():
                            recv_task.cancel()
                            await asyncio.gather(recv_task, return_exceptions=True)
                    event = await asyncio.to_thread(decode_response, raw)
                    ev = event["event"]
                    if ev in {Type.SessionFailed, Type.SessionCanceled, Type.ConnectionFailed}:
                        meta = event.get("response_meta", {})
                        raise speech.InputError(f"同传失败：{event['event_name']} "
                                                f"{meta.get('StatusCode', '')} {meta.get('Message', '')}")
                    if ev == Type.UsageResponse:
                        result["usage"].append(event.get("response_meta", {}).get("Billing", {}))
                    if ev == Type.TTSResponse:
                        received_audio.extend(event["data"])
                    for kind, begin, update, end in [
                        ("source", Type.SourceSubtitleStart, Type.SourceSubtitleResponse, Type.SourceSubtitleEnd),
                        ("translation", Type.TranslationSubtitleStart, Type.TranslationSubtitleResponse, Type.TranslationSubtitleEnd)]:
                        if ev == begin:
                            if active[kind]:
                                append_segment(kind, event)
                            active[kind] = event["text"]
                            segment_meta[kind] = {"start_ms": event["start_time"],
                                                  "speaker_changed": event["spk_chg"]}
                        elif ev == update:
                            active[kind] += event["text"]
                        elif ev == end:
                            append_segment(kind, event)
                    if ev == Type.SessionFinished:
                        for kind in active:
                            if active[kind]:
                                append_segment(kind, event)
                        return

            sender = asyncio.create_task(send_audio())
            try:
                await asyncio.wait_for(receive_all(), len(pcm) / 32000 + timeout * 2)
                await asyncio.wait_for(sender, timeout)
            finally:
                if not sender.done():
                    sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            if received_audio:
                target = start.get("target_audio", {"format": "pcm", "rate": 16000, "bits": 16, "channel": 1})
                result["files"].append(await asyncio.to_thread(
                    _save_audio, received_audio, target, out_dir, result["session_id"]))
                result["audio_params"] = target
            elif mode == "s2s":
                raise speech.InputError("同传 SessionFinished 但未返回目标音频")
            result["ok"] = True
    except (speech.InputError, OSError, TimeoutError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as exc:
        result["error"] = str(exc) or "同传响应超时"
    finally:
        result["source_text"] = "".join(item["text"] for item in result["source_segments"])
        result["translation_text"] = "".join(item["text"] for item in result["translation_segments"])
    return result
