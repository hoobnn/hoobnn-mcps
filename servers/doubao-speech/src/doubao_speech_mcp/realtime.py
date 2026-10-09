"""Seeduplex 3.0 persistent JSON WebSocket sessions (no binary V2 protocol)."""

import asyncio
import atexit
import base64
import copy
import json
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from websockets.asyncio.client import connect

from .speech import HOST, InputError, local_file

ENDPOINT = HOST.replace("https://", "wss://").replace("http://", "ws://") + "/api/v3/duplex/realtime/dialogue"
MAX_SESSIONS = 16
MAX_EVENT_BYTES = 2 * 1024 * 1024


def create_event(session, extension=None):
    """Keep advanced tools and extension fields; default only documented audio specs."""
    if not isinstance(session, dict):
        raise InputError("session 必须是对象")
    config = copy.deepcopy(session)
    config.setdefault("model", "1.2.6.1")
    if config["model"] != "1.2.6.1":
        raise InputError("实时 3.0 session.model 必须为 1.2.6.1")
    audio = config.setdefault("audio", {})
    audio.setdefault("input", {}).setdefault("format", {"type": "pcm", "rate": 16000})
    output = audio.setdefault("output", {})
    output.setdefault("format", {"type": "pcm_s16le", "rate": 24000})
    if not output.get("voice"):
        raise InputError("缺少 session.audio.output.voice")
    if audio["input"]["format"].get("rate") != 16000:
        raise InputError("输入音频仅支持 16000 Hz")
    if audio["input"]["format"].get("type") == "opus":
        audio["input"]["format"]["type"] = "speech_opus"  # Preserve the older convenience alias.
    if audio["input"]["format"].get("type") not in ("pcm", "speech_opus"):
        raise InputError("输入音频仅支持 pcm / speech_opus")
    if output["format"].get("type") not in ("pcm", "pcm_s16le", "ogg_opus") or output["format"].get("rate") != 24000:
        raise InputError("输出音频须为 pcm / pcm_s16le / ogg_opus，24000 Hz")
    event = {"type": "session.create", "session": config, "event_id": str(uuid.uuid4())}
    if extension is not None:
        if not isinstance(extension, dict):
            raise InputError("extension 必须是对象")
        event["extension"] = copy.deepcopy(extension)
    return event


@dataclass
class _Session:
    websocket: object
    directory: Path
    audio_format: str
    input_format: str = "pcm"
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=2048))
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    receive_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    reader: object = None
    last_used: float = field(default_factory=time.monotonic)
    audio_path: object = None
    audio_bytes: int = 0
    audio_handle: object = None
    closed_at: float | None = None
    dropped_events: int = 0
    error: str = ""
    close_ack: bool = False
    socket_closed: bool = False
    remote_id: str = ""
    sequence: int = 0


class RealtimeSessions:
    """One background reader per socket; handles never expose credentials or server IDs."""

    def __init__(self, idle_ttl=300, retention_ttl=60, cleanup_interval=15):
        for value in (idle_ttl, retention_ttl, cleanup_interval):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("会话 TTL 和清理间隔必须为有限正数")
        self.idle_ttl = idle_ttl
        self.retention_ttl = retention_ttl
        self.cleanup_interval = cleanup_interval
        self.cleanup_task = None
        self.sessions = {}
        self.lock = asyncio.Lock()
        atexit.register(self.abort_at_exit)

    async def start(self):
        """Start the idle-session reaper from the server lifespan."""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.cleanup_interval)
            await self.reap()

    async def reap(self):
        now = time.monotonic()
        for handle, state in list(self.sessions.items()):
            if state is None:
                continue
            if state.closed.is_set():
                if state.closed_at is not None and now - state.closed_at >= self.retention_ttl:
                    self.sessions.pop(handle, None)
            elif now - state.last_used >= self.idle_ttl and not state.send_lock.locked() and not state.receive_lock.locked():
                state.error = "会话因空闲超时关闭"
                self._enqueue(state, {"type": "error", "error": {"code": "idle_timeout", "message": state.error}})
                await self._dispose(state)

    @staticmethod
    def _validate_timeout(timeout, maximum):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= maximum:
            raise InputError(f"timeout 须在 0 到 {maximum} 秒之间")

    @staticmethod
    def _close_audio(state):
        if state.audio_handle is not None:
            state.audio_handle.close()
            state.audio_handle = None

    @staticmethod
    def _enqueue(state, event):
        # Keep the socket reader moving. Drop audio/text deltas before control events.
        if state.queue.full():
            pending = []
            while not state.queue.empty():
                pending.append(state.queue.get_nowait())
            index = next((i for i, item in enumerate(pending) if item.get("type", "").endswith(".delta")), None)
            state.dropped_events += 1
            if index is None and event.get("type", "").endswith(".delta"):
                for item in pending:
                    state.queue.put_nowait(item)
                return
            if index is None:
                index = next((i for i, item in enumerate(pending) if item.get("type") not in ("error", "session.closed")), 0)
            pending.pop(index)
            for item in pending:
                state.queue.put_nowait(item)
        state.queue.put_nowait(event)

    async def _dispose(self, state):
        state.closed.set()
        if state.closed_at is None:
            state.closed_at = time.monotonic()
        if state.reader and state.reader is not asyncio.current_task():
            state.reader.cancel()
            await asyncio.gather(state.reader, return_exceptions=True)
        self._close_audio(state)
        if state.socket_closed:
            return
        try:
            await asyncio.wait_for(state.websocket.close(), 5)
        except Exception:
            transport = getattr(state.websocket, "transport", None)
            if transport is not None:
                transport.abort()
        state.socket_closed = True

    def abort_at_exit(self):
        # Async close_all is the normal lifespan shutdown. Abort is a final fallback.
        for state in list(self.sessions.values()):
            transport = getattr(getattr(state, "websocket", None), "transport", None)
            if transport is not None:
                transport.abort()

    async def _reader(self, state):
        try:
            async for raw in state.websocket:
                if not isinstance(raw, str):
                    raise InputError("实时 3.0 服务返回了非 JSON 文本帧")
                event = json.loads(raw)
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise InputError("服务返回了无效事件")
                if event["type"] == "session.created":
                    state.remote_id = (event.get("session") or {}).get("id", "")
                if event["type"] in ("response.output_audio.started", "response.canceled"):
                    self._close_audio(state)
                    state.audio_path = None
                    state.audio_bytes = 0
                if event["type"] == "error":
                    state.error = json.dumps(event.get("error", event), ensure_ascii=False)
                if event["type"] == "response.output_audio.delta":
                    data = base64.b64decode(event.get("delta", ""), validate=True)
                    if state.audio_path is None:
                        state.sequence += 1
                        extension = "ogg" if state.audio_format == "ogg_opus" else "pcm"
                        state.audio_path = state.directory / f"response-{state.sequence:04d}.{extension}"
                        state.audio_bytes = 0
                    if state.audio_handle is None:
                        state.audio_handle = state.audio_path.open("ab")
                    state.audio_handle.write(data)
                    state.audio_handle.flush()
                    state.audio_bytes += len(data)
                    event.pop("delta", None)
                    event.update(audio_file=str(state.audio_path), chunk_bytes=len(data), audio_bytes=state.audio_bytes,
                                 audio_format=state.audio_format, sample_rate=24000)
                elif event["type"] == "response.output_audio.done":
                    if state.audio_path:
                        event.update(audio_file=str(state.audio_path), audio_bytes=state.audio_bytes,
                                     audio_format=state.audio_format, sample_rate=24000)
                    self._close_audio(state)
                    state.audio_path = None
                if event["type"] == "session.closed":
                    state.close_ack = True
                    state.closed.set()
                self._enqueue(state, event)
                if event["type"] in ("session.closed", "error"):
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.error = f"实时连接结束：{type(exc).__name__}: {exc}"
        finally:
            await self._dispose(state)

    async def open(self, session, out_dir, extension=None, timeout=30):
        try:
            self._validate_timeout(timeout, 120)
            return await asyncio.wait_for(self._open(session, out_dir, extension, timeout), timeout)
        except Exception as exc:
            return {"ok": False, "error": str(exc) or type(exc).__name__}

    async def _open(self, session, out_dir, extension=None, timeout=30):
        websocket = None
        reserved = False
        session_id = str(uuid.uuid4())
        try:
            event = create_event(session, extension)
            if not 0 < timeout <= 120:
                raise InputError("timeout 须在 0 到 120 秒之间")
            key = os.environ.get("VOLC_SPEECH_API_KEY")
            if not key:
                raise InputError("未设置环境变量 VOLC_SPEECH_API_KEY")
            directory = Path(out_dir).expanduser().resolve() / session_id
            directory.mkdir(parents=True, exist_ok=True)
            async with self.lock:
                if sum(state is None or not state.closed.is_set() for state in self.sessions.values()) >= MAX_SESSIONS:
                    raise InputError(f"最多同时保持 {MAX_SESSIONS} 个实时会话，请先关闭旧会话")
                self.sessions[session_id] = None  # reserve a slot before awaiting connect
                reserved = True
            websocket = await connect(ENDPOINT, additional_headers={"X-Api-Key": key},
                                      open_timeout=timeout, close_timeout=5, max_size=MAX_EVENT_BYTES)
            await asyncio.wait_for(websocket.send(json.dumps(event, ensure_ascii=False)), timeout)
            raw = await asyncio.wait_for(websocket.recv(), timeout)
            ack = json.loads(raw)
            if not isinstance(ack, dict) or ack.get("type") != "session.created":
                raise InputError(f"会话创建失败：{ack}")
            state = _Session(websocket, directory, event["session"]["audio"]["output"]["format"]["type"],
                             event["session"]["audio"]["input"]["format"]["type"])
            state.remote_id = (ack.get("session") or {}).get("id", "")
            self.sessions[session_id] = state
            state.reader = asyncio.create_task(self._reader(state))
            return {"ok": True, "session_id": session_id, "event": ack, "output_dir": str(directory)}
        except BaseException as exc:
            if reserved:
                self.sessions.pop(session_id, None)
            if websocket is not None:
                try:
                    await asyncio.wait_for(websocket.close(), 5)
                except Exception:
                    transport = getattr(websocket, "transport", None)
                    if transport is not None:
                        transport.abort()
            if isinstance(exc, asyncio.CancelledError):
                raise
            return {"ok": False, "error": str(exc) or type(exc).__name__}

    def _get(self, session_id):
        state = self.sessions.get(session_id)
        if state is None:
            raise InputError("未知或已关闭的 session_id")
        state.last_used = time.monotonic()
        return state

    async def send(self, session_id, event, audio_file="", timeout=30):
        try:
            self._validate_timeout(timeout, 120)
            return await asyncio.wait_for(self._send_event(session_id, event, audio_file, timeout), timeout)
        except Exception as exc:
            return {"ok": False, "error": str(exc) or type(exc).__name__}

    async def _send_event(self, session_id, event, audio_file="", timeout=30):
        """Send arbitrary documented upstream event; audio_file streams PCM at 20 ms pace."""
        try:
            state = self._get(session_id)
            if state.closed.is_set():
                raise InputError(state.error or "会话已关闭")
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise InputError("event 须为包含 type 的对象")
            if event["type"] in ("session.create", "session.close"):
                raise InputError("请使用 open / close 管理会话生命周期")
            if not 0 < timeout <= 120:
                raise InputError("timeout 须在 0 到 120 秒之间")
            payload = copy.deepcopy(event)
            payload.setdefault("event_id", str(uuid.uuid4()))
            if event["type"] == "session.update":
                config = payload.get("session", {})
                if "audio" in config and "output" in config["audio"] and "format" in config["audio"]["output"]:
                    raise InputError("持久会话中不可切换输出格式，请新建会话")
            chunks = 0
            if audio_file:
                if event["type"] != "input_audio_buffer.append":
                    raise InputError("audio_file 仅可用于 input_audio_buffer.append")
                if state.input_format != "pcm":
                    raise InputError("audio_file PCM 分包要求会话输入格式为 pcm")
                path = local_file(audio_file, 100)
                if path.suffix.lower() != ".pcm" or path.stat().st_size % 2:
                    raise InputError("audio_file 须为裸 PCM 文件：16000 Hz / mono / int16 little-endian / .pcm")
                with path.open("rb") as handle:
                    while data := handle.read(640):
                        if state.closed.is_set() or session_id not in self.sessions:
                            raise InputError("音频发送中会话已关闭")
                        packet = {**payload, "audio": base64.b64encode(data).decode(), "event_id": str(uuid.uuid4())}
                        await self._send(state, packet, timeout)
                        chunks += 1
                        await asyncio.sleep(len(data) / 32000)
                        state.last_used = time.monotonic()
            else:
                await self._send(state, payload, timeout)
            return {"ok": True, "session_id": session_id, "event_id": payload["event_id"], "chunks": chunks}
        except Exception as exc:
            return {"ok": False, "error": str(exc) or type(exc).__name__}

    async def _send(self, state, event, timeout):
        raw = json.dumps(event, ensure_ascii=False)
        if len(raw.encode()) > MAX_EVENT_BYTES:
            raise InputError("event 超过 2MB；音频请用 audio_file")
        async def locked_send():
            async with state.send_lock:
                await state.websocket.send(raw)
        await asyncio.wait_for(locked_send(), timeout)

    async def receive(self, session_id, max_events=100, timeout=10):
        try:
            self._validate_timeout(timeout, 60)
            return await asyncio.wait_for(self._receive(session_id, max_events, timeout), timeout)
        except asyncio.TimeoutError:
            try:
                state = self._get(session_id)
                return {"ok": not bool(state.error), "session_id": session_id, "events": [],
                        "closed": state.closed.is_set(), "error": state.error or None,
                        "dropped_events": state.dropped_events}
            except InputError as exc:
                return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": str(exc) or type(exc).__name__}

    async def _receive(self, session_id, max_events=100, timeout=10):
        """Return text, usage, tools and context verbatim; audio deltas become local paths."""
        try:
            state = self._get(session_id)
            if isinstance(max_events, bool) or not isinstance(max_events, int) or not 1 <= max_events <= 500 or not 0 < timeout <= 60:
                raise InputError("max_events 须为 1..500；timeout 须为 0..60 秒")
            events = []
            async with state.receive_lock:
                if state.queue.empty() and not state.closed.is_set():
                    get = asyncio.create_task(state.queue.get())
                    closed = asyncio.create_task(state.closed.wait())
                    try:
                        done, _ = await asyncio.wait((get, closed), timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
                        if get in done:
                            events.append(get.result())
                    finally:
                        for task in (get, closed):
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(get, closed, return_exceptions=True)
                while len(events) < max_events and not state.queue.empty():
                    events.append(state.queue.get_nowait())
            return {"ok": not bool(state.error), "session_id": session_id, "events": events,
                    "closed": state.closed.is_set(), "error": state.error or None,
                    "dropped_events": state.dropped_events}
        except Exception as exc:
            return {"ok": False, "error": str(exc) or type(exc).__name__}

    async def close(self, session_id, timeout=10):
        try:
            self._validate_timeout(timeout, 60)
        except InputError as exc:
            return {"ok": False, "error": str(exc)}
        deadline = time.monotonic() + timeout
        state = self.sessions.pop(session_id, None)
        if state is None:
            return {"ok": False, "error": "未知或已关闭的 session_id"}
        graceful = False
        try:
            if not 0 < timeout <= 60:
                raise InputError("timeout 须为 0..60 秒")
            if not state.closed.is_set():
                await self._send(state, {"type": "session.close", "event_id": str(uuid.uuid4())}, timeout)
                await asyncio.wait_for(state.closed.wait(), max(0, deadline - time.monotonic()))
            # A transport disconnect sets closed too; retain actual ack distinction.
            events = []
            while not state.queue.empty():
                events.append(state.queue.get_nowait())
            graceful = state.close_ack
            return {"ok": graceful and not bool(state.error), "session_id": session_id,
                    "graceful": graceful, "events": events, "dropped_events": state.dropped_events,
                    "error": state.error or (None if graceful else "未收到 session.closed")}
        except Exception as exc:
            return {"ok": False, "session_id": session_id, "graceful": graceful, "error": str(exc) or type(exc).__name__}
        finally:
            await self._dispose(state)

    async def close_all(self):
        if self.cleanup_task is not None:
            self.cleanup_task.cancel()
            await asyncio.gather(self.cleanup_task, return_exceptions=True)
            self.cleanup_task = None
        await asyncio.gather(*(self.close(handle) for handle, state in list(self.sessions.items()) if state), return_exceptions=True)


sessions = RealtimeSessions()
