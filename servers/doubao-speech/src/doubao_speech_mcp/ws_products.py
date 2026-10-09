"""Event framing from the official TTS protocols attachment (2026-09-28).

https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-text-to-speech-websocket
Podcast uses the same framing, with its own session lifecycle.
"""

import asyncio
import copy
import gzip
import json
import os
import struct
import uuid
from pathlib import Path

import websockets

from . import speech


def headers(resource):
    key = os.environ.get("VOLC_SPEECH_API_KEY")
    if not key:
        raise speech.InputError("未设置 VOLC_SPEECH_API_KEY")
    return {"X-Api-Key": key, "X-Api-Resource-Id": resource,
            "X-Api-Request-Id": str(uuid.uuid4()), "X-Api-Connect-Id": str(uuid.uuid4()),
            "X-Control-Require-Usage-Tokens-Return": "*"}


def url(path):
    return speech.HOST.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + path


def frame(payload=None, event=None, session_id=""):
    data = json.dumps(payload or {}, ensure_ascii=False).encode()
    packet = bytes([0x11, 0x14 if event is not None else 0x10, 0x10, 0])
    if event is not None:
        packet += struct.pack(">i", event)
        if event not in {1, 2}:
            sid = session_id.encode()
            packet += struct.pack(">I", len(sid)) + sid
    return packet + struct.pack(">I", len(data)) + data


def parse_frame(packet):
    if not isinstance(packet, bytes) or len(packet) < 8 or packet[0] >> 4 != 1:
        raise speech.InputError("无效 WebSocket 二进制帧")
    pos = (packet[0] & 15) * 4
    if pos < 4 or pos > len(packet):
        raise speech.InputError("无效 header size")
    kind, flags = packet[1] >> 4, packet[1] & 15
    if kind not in {1, 2, 9, 11, 12, 15} or flags not in {0, 1, 2, 3, 4}:
        raise speech.InputError("不支持的 WebSocket message type/flags")
    if packet[2] >> 4 not in {0, 1}:
        raise speech.InputError("不支持的帧序列化格式")
    result = {"type": kind, "event": None, "sequence": None}

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(packet):
            raise speech.InputError("WebSocket 帧被截断")
        data = packet[pos:pos + n]
        pos += n
        return data

    def integer(signed=False):
        return struct.unpack(">i" if signed else ">I", take(4))[0]

    if kind == 15:
        result["error_code"] = integer()
    elif flags & 1:
        result["sequence"] = integer(True)
    if flags & 4:
        event = result["event"] = integer(True)
        if event not in {1, 2}:
            try:
                result["connection_id" if event in {50, 51, 52} else "session_id"] = take(integer()).decode()
            except UnicodeDecodeError as exc:
                raise speech.InputError("WebSocket 帧的 ID 不是 UTF-8") from exc
    payload = take(integer())
    if pos != len(packet):
        raise speech.InputError("WebSocket 帧存在多余字节")
    compression = packet[2] & 15
    if compression == 1:
        try:
            payload = gzip.decompress(payload)
        except (OSError, EOFError) as exc:
            raise speech.InputError("WebSocket 帧的 gzip 数据无效") from exc
    elif compression != 0:
        raise speech.InputError("不支持的帧压缩格式")
    result["payload"] = payload
    # Podcast audio event 361 is raw even where the docs label serialization JSON.
    if kind == 15 or result["event"] in {51, 153}:
        raise speech.InputError(f"服务端错误 {result.get('error_code', result['event'])}: {payload.decode(errors='replace')}")
    if packet[2] >> 4 == 1 and result["event"] not in {352, 361}:
        try:
            result["data"] = json.loads(payload) if payload else {}
        except (ValueError, UnicodeDecodeError) as exc:
            raise speech.InputError("WebSocket 帧的 JSON 数据无效") from exc
    return result


async def receive(ws, timeout=60):
    async def decode():
        return await asyncio.to_thread(parse_frame, await ws.recv())
    return await asyncio.wait_for(decode(), timeout)


async def expect(ws, event):
    msg = await receive(ws)
    if msg["event"] != event:
        raise speech.InputError(f"期望事件 {event}，实际 {msg['event']}")
    return msg


async def receive_with_sender(ws, sender, timeout=300):
    """Stop receiving immediately if concurrent text transmission fails."""
    if sender is None:
        return await receive(ws, timeout)
    if sender.done():
        sender.result()
        return await receive(ws, timeout)
    receiver = asyncio.create_task(receive(ws, timeout))
    try:
        done, _ = await asyncio.wait({receiver, sender}, return_when=asyncio.FIRST_COMPLETED)
        if sender in done:
            sender.result()
        return await receiver
    finally:
        if not receiver.done():
            receiver.cancel()
        await asyncio.gather(receiver, return_exceptions=True)


async def synthesize(request, out_dir, mode="bidirectional", text_chunks=None, resource_id=None):
    """One complete WS synthesis, concurrent input and output; saves raw format."""
    sender = None
    result = {"ok": False, "files": [], "events": [], "error": None}
    try:
        body = copy.deepcopy(request)
        if not isinstance(body, dict) or not isinstance(body.get("req_params"), dict):
            raise speech.InputError("request.req_params 必须是 object")
        params = body["req_params"]
        speaker = params["speaker"]
        if not isinstance(speaker, str) or not speaker.strip():
            raise speech.InputError("speaker 必须是非空字符串")
        config = params.get("audio_params", {})
        if not isinstance(config, dict):
            raise speech.InputError("audio_params 必须是 object")
        fmt = config.get("format", "mp3")
        if fmt not in {"mp3", "pcm", "wav", "ogg_opus"}:
            raise speech.InputError("format 只能是 mp3/pcm/wav/ogg_opus")
        if mode not in {"bidirectional", "unidirectional"}:
            raise speech.InputError("mode 只能是 bidirectional/unidirectional")
        chunks = text_chunks if text_chunks is not None else [params.get("text", "")]
        if not isinstance(chunks, list) or not chunks or any(not isinstance(c, str) or not c.strip() for c in chunks):
            raise speech.InputError("需要非空 text 或 text_chunks")
        if mode == "unidirectional" and text_chunks is not None:
            raise speech.InputError("text_chunks 仅用于双向流")
        resource = resource_id or speech.tts_resource(speaker)
        endpoint = "/api/v3/tts/bidirection" if mode == "bidirectional" else "/api/v3/tts/unidirectional/stream"
        async with websockets.connect(url(endpoint), additional_headers=headers(resource),
                                      max_size=10 * 1024 * 1024, open_timeout=30) as ws:
            result["logid"] = ws.response.headers.get("X-Tt-Logid")
            sid = str(uuid.uuid4())
            if mode == "bidirectional":
                await ws.send(frame(event=1))
                await expect(ws, 50)
                start = copy.deepcopy(body)
                start["req_params"].pop("text", None)
                start["event"] = 100
                await ws.send(frame(start, 100, sid))
                await expect(ws, 150)

                async def send_text():
                    for chunk in chunks:
                        task = copy.deepcopy(body)
                        task["event"] = 200
                        task["req_params"]["text"] = chunk
                        await ws.send(frame(task, 200, sid))
                    await ws.send(frame(event=102, session_id=sid))

                sender = asyncio.create_task(send_text())
            else:
                await ws.send(frame(body))
            audio = bytearray()
            while True:
                msg = await receive_with_sender(ws, sender, 300)
                if msg["type"] == 11 and msg["payload"] and msg["event"] == 352:
                    audio.extend(msg["payload"])
                else:
                    result["events"].append({k: v for k, v in msg.items() if k != "payload"})
                if msg["event"] == 152:
                    data = msg.get("data", {})
                    if not isinstance(data, dict) or data.get("status_code", 20000000) != 20000000:
                        raise speech.InputError(f"合成失败：{data}")
                    break
            if sender:
                await sender
            if mode == "bidirectional":
                await ws.send(frame(event=2))
                await expect(ws, 52)
            if not audio:
                raise speech.InputError("合成完成但没有返回音频")
            out_dir = Path(out_dir)
            path = out_dir / f"speech-{uuid.uuid4().hex}.{fmt}"
            await asyncio.to_thread(speech._atomic_bytes, path, audio)
            result.update(ok=True, files=[str(path)], audio_config=config)
    except (OSError, ValueError, KeyError, TypeError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as exc:
        result["error"] = str(exc) or "WebSocket 超时"
    finally:
        if sender:
            if not sender.done():
                sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
    return result


async def podcast(request, out_dir):
    result = {"ok": False, "files": [], "rounds": [], "usage": [], "error": None}
    audio = bytearray()
    try:
        body = copy.deepcopy(request)
        if not isinstance(body, dict):
            raise speech.InputError("request 必须是 object")
        action = body.get("action", 0)
        info = body.get("input_info") or {}
        if not isinstance(info, dict):
            raise speech.InputError("input_info 必须是 object")
        if action == 0 and not (body.get("input_text") or info.get("input_url")):
            raise speech.InputError("action=0 需要 input_text 或 input_info.input_url")
        if action == 4 and not body.get("prompt_text"):
            raise speech.InputError("action=4 需要 prompt_text")
        if action == 3:
            texts = body.get("nlp_texts")
            if not isinstance(texts, list) or not texts:
                raise speech.InputError("action=3 需要非空 nlp_texts")
            if any(not isinstance(t, dict) or not isinstance(t.get("text"), str) or not t["text"] or len(t["text"]) > 300 or not t.get("speaker") for t in texts):
                raise speech.InputError("nlp_texts 每轮需要 speaker 和 1–300 字符 text")
            if sum(len(t["text"]) for t in texts) > 10000:
                raise speech.InputError("nlp_texts 总长超过 10000 字符")
        if action not in {0, 3, 4}:
            raise speech.InputError("action 只能是 0/3/4")
        speaker_info = body.get("speaker_info") or {}
        if not isinstance(speaker_info, dict):
            raise speech.InputError("speaker_info 必须是 object")
        speakers = speaker_info.get("speakers")
        if speakers is not None and (not isinstance(speakers, list) or len(speakers) != 2):
            raise speech.InputError("speaker_info.speakers 必须包含两个音色")
        config = body.setdefault("audio_config", {"format": "mp3", "sample_rate": 24000})
        if not isinstance(config, dict):
            raise speech.InputError("audio_config 必须是 object")
        fmt = config.get("format", "pcm")
        if fmt not in {"mp3", "pcm", "aac", "ogg_opus"}:
            raise speech.InputError("播客 format 只能是 mp3/pcm/aac/ogg_opus")
        sid = result["task_id"] = str(uuid.uuid4())
        result["last_finished_round_id"] = None
        async with websockets.connect(url("/api/v3/sami/podcasttts"),
                                      additional_headers=headers("volc.service_type.10050"),
                                      max_size=10 * 1024 * 1024, open_timeout=30) as ws:
            result["logid"] = ws.response.headers.get("X-Tt-Logid")
            await ws.send(frame(body, 100, sid))
            await expect(ws, 150)
            while True:
                msg = await receive(ws, 300)
                event, data = msg["event"], msg.get("data", {})
                if event != 361 and not isinstance(data, dict):
                    raise speech.InputError("播客事件 payload 必须是 JSON object")
                if event == 361:
                    audio.extend(msg["payload"])
                elif event == 360:
                    result["rounds"].append(data)
                elif event == 362:
                    if data.get("is_error"):
                        raise speech.InputError(data.get("error_msg", "播客轮次失败"))
                    if result["rounds"]:
                        result["rounds"][-1]["timing"] = data
                        result["last_finished_round_id"] = result["rounds"][-1].get("round_id")
                elif event == 363:
                    result["meta"] = data
                elif event == 154:
                    result["usage"].append(data)
                elif event == 152:
                    if data.get("status_code", 20000000) != 20000000:
                        raise speech.InputError(str(data))
                    break
            await ws.send(frame(event=2))
            await expect(ws, 52)
        if not audio and not info.get("only_nlp_text"):
            raise speech.InputError("播客结束但没有音频")
        result["ok"] = True
    except (OSError, ValueError, KeyError, TypeError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as exc:
        result["error"] = str(exc) or "WebSocket 超时"
    # Preserve received audio on a disconnect for diagnosis and explicit resume.
    if audio:
        try:
            out_dir = Path(out_dir)
            path = out_dir / f"podcast-{result['task_id']}.{'partial.' if not result['ok'] else ''}{fmt}"
            await asyncio.to_thread(speech._atomic_bytes, path, audio)
            result["files"] = [str(path)]
            result["audio_config"] = config
        except (OSError, TypeError) as exc:
            result["ok"] = False
            result["error"] = f"{result['error'] + '; ' if result['error'] else ''}音频保存失败：{exc}"
    return result
