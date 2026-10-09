"""ASR WebSocket protocol: https://www.volcengine.com/docs/6561/1354869."""

import asyncio
import copy
import gzip
import json
import math
import os
import struct
import uuid
import wave

from . import speech

ENDPOINTS = {
    "realtime": "/api/v3/sauc/bigmodel_async",
    "sentence": "/api/v3/sauc/bigmodel_nostream",
}
DEFAULT_RESOURCE = "volc.seedasr.sauc.duration"


def encode_frame(payload, sequence, *, audio=False, final=False):
    """Use sequence-bearing frames; a final audio packet has a negative sequence."""
    if sequence <= 0:
        raise speech.InputError("sequence 必须为正整数")
    compressed = gzip.compress(payload)
    header = bytes((0x11, ((2 if audio else 1) << 4) | (3 if final else 1),
                    0x01 if audio else 0x11, 0))
    return header + struct.pack(">iI", -sequence if final else sequence, len(compressed)) + compressed


def decode_frame(frame):
    """Decode the documented header, optional sequence, error code and payload."""
    if not isinstance(frame, bytes) or len(frame) < 8:
        raise speech.InputError("ASR 返回了无效二进制消息")
    version, header_size = frame[0] >> 4, (frame[0] & 15) * 4
    kind, flags = frame[1] >> 4, frame[1] & 15
    serialization, compression = frame[2] >> 4, frame[2] & 15
    if version != 1 or header_size < 4 or header_size > len(frame):
        raise speech.InputError("ASR 协议版本或 header 长度无效")
    if kind not in (9, 15):
        raise speech.InputError(f"未知 ASR 消息类型：{kind}")
    offset, sequence, code = header_size, None, 0
    def integer(signed=False):
        nonlocal offset
        if offset + 4 > len(frame):
            raise speech.InputError("ASR 消息截断")
        value = struct.unpack_from(">i" if signed else ">I", frame, offset)[0]
        offset += 4
        return value
    if flags & 1:
        sequence = integer(True)
    if kind == 15:
        code = integer()
    size = integer()
    if size != len(frame) - offset:
        raise speech.InputError("ASR payload 长度不匹配")
    payload = frame[offset:]
    if compression == 1:
        payload = gzip.decompress(payload)
    elif compression != 0:
        raise speech.InputError(f"未知 ASR 压缩方法：{compression}")
    if serialization == 1:
        payload = json.loads(payload)
    elif serialization == 0:
        payload = payload.decode("utf-8", errors="replace")
    else:
        raise speech.InputError(f"未知 ASR 序列化方法：{serialization}")
    return {"message_type": kind, "code": code, "payload_sequence": sequence,
            "is_last_package": bool(flags & 2) or (sequence is not None and sequence < 0),
            "payload_size": size, "payload_msg": payload}


def prepare_audio(audio, request):
    """Read local PCM/WAV and preserve all caller-supplied API request options."""
    if not isinstance(request, dict):
        raise speech.InputError("request 必须为完整请求体 dict（user/audio/request）")
    body = copy.deepcopy(request)
    metadata = body.setdefault("audio", {})
    params = body.setdefault("request", {})
    if not isinstance(metadata, dict) or not isinstance(params, dict):
        raise speech.InputError("audio 和 request 字段必须为 dict")
    params.setdefault("model_name", "bigmodel")
    path = speech.local_file(audio, 100)
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise speech.InputError("WAV 必须包含未压缩 PCM")
            metadata.update(rate=wav.getframerate(), bits=wav.getsampwidth() * 8,
                            channel=wav.getnchannels())
            data = wav.readframes(wav.getnframes())
    elif path.suffix.lower() == ".pcm":
        data = path.read_bytes()
        for key, value in (("rate", 16000), ("bits", 16), ("channel", 1)):
            metadata.setdefault(key, value)
    else:
        raise speech.InputError("流式识别仅支持本地 WAV 或 PCM 文件")
    # WAV container is stripped; the wire data must therefore be declared PCM.
    metadata.update(format="pcm", codec="raw")
    if metadata["bits"] != 16 or metadata["channel"] not in (1, 2):
        raise speech.InputError("音频必须为 16-bit PCM，声道数为 1 或 2")
    if not isinstance(metadata["rate"], int) or metadata["rate"] <= 0:
        raise speech.InputError("audio.rate 必须为正整数")
    alignment = metadata["channel"] * 2
    if not data or len(data) % alignment:
        raise speech.InputError("PCM 为空或未按采样帧对齐")
    return body, data, alignment


def websocket_connect(*args, **kwargs):
    from websockets.asyncio.client import connect
    return connect(*args, **kwargs)


async def streaming_recognize(audio, request=None, mode="realtime", resource_id=None,
                              chunk_ms=200, timeout=300):
    """Recognize local audio with concurrent paced upload and result reception.

    request is the complete official JSON body; every advanced field is preserved.
    timeout bounds the entire operation, including upload and final result wait.
    """
    result = {"ok": False, "text": "", "response": None, "messages": [],
              "request_id": str(uuid.uuid4()), "logid": None, "error": None}
    sender = None
    try:
        if mode not in ENDPOINTS:
            raise speech.InputError("mode 只能为 realtime 或 sentence")
        if not isinstance(chunk_ms, int) or not 100 <= chunk_ms <= 200:
            raise speech.InputError("chunk_ms 必须为 100 到 200 毫秒")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise speech.InputError("timeout 必须为正数秒")
        deadline = asyncio.get_running_loop().time() + timeout
        body, data, alignment = await asyncio.wait_for(
            asyncio.to_thread(prepare_audio, audio, request if request is not None else {}), timeout)
        key = os.environ.get("VOLC_SPEECH_API_KEY")
        if not key:
            raise speech.InputError("未设置环境变量 VOLC_SPEECH_API_KEY")
        chunk_size = max(alignment, int(body["audio"]["rate"] * chunk_ms / 1000) * alignment)
        headers = {"X-Api-Key": key, "X-Api-Resource-Id": resource_id or DEFAULT_RESOURCE,
                   "X-Api-Request-Id": result["request_id"], "X-Api-Sequence": "-1"}
        url = speech.HOST.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + ENDPOINTS[mode]
        async def session():
            async with websocket_connect(url, additional_headers=headers, max_size=16 * 1024 * 1024,
                                         open_timeout=min(timeout, 30), close_timeout=5) as ws:
                response = getattr(ws, "response", None)
                if response is not None:
                    result["logid"] = response.headers.get("X-Tt-Logid")
                await ws.send(encode_frame(json.dumps(body, ensure_ascii=False).encode(), 1))
                async def send_audio():
                    for index, start in enumerate(range(0, len(data), chunk_size), 2):
                        final = start + chunk_size >= len(data)
                        await ws.send(encode_frame(data[start:start + chunk_size], index,
                                                   audio=True, final=final))
                        if not final:
                            await asyncio.sleep(chunk_ms / 1000)
                sender = asyncio.create_task(send_audio())
                async def receive():
                    while True:
                        message = await asyncio.to_thread(decode_frame, await ws.recv())
                        result["messages"].append(message)
                        payload = message["payload_msg"]
                        if message["message_type"] == 15:
                            raise speech.InputError(f"ASR {message['code']}: {payload}")
                        result["response"] = payload
                        if isinstance(payload, dict):
                            recognition = payload.get("result") or {}
                            if isinstance(recognition, dict):
                                result["text"] = recognition.get("text", result["text"])
                        if message["is_last_package"]:
                            return
                receiver = asyncio.create_task(receive())
                try:
                    # An upload failure must interrupt the receive wait immediately.
                    done, _ = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
                    if sender in done:
                        await sender
                        await receiver
                    else:
                        await receiver
                finally:
                    for task in (sender, receiver):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(sender, receiver, return_exceptions=True)
        await asyncio.wait_for(session(), timeout=max(0, deadline - asyncio.get_running_loop().time()))
        result["ok"] = True
    except TimeoutError:
        result["error"] = "流式识别超时，未收到最终结果"
    except Exception as exc:
        result["error"] = str(exc)
    return result
