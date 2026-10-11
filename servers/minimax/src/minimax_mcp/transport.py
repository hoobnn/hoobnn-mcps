"""Vendored HTTP runtime: pooled async I/O behind existing synchronous adapters.

Business functions run in workers; all MCP network I/O belongs to the lifespan
event loop. Cancellation closes in-flight requests without replaying paid POSTs.
Direct Python use has a pooled synchronous fallback, never an extra daemon.
"""
import asyncio
import atexit
import concurrent.futures
import contextvars
import io
import math
import os
import threading
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx


def positive_setting(name, default, maximum):
    value = float(os.environ.get(name, default))
    if not math.isfinite(value) or not 0 < value <= maximum:
        raise ValueError(f"{name} must be in (0, {maximum}]")
    return value


def integer_setting(name, default, maximum):
    value = positive_setting(name, default, maximum)
    if not value.is_integer():
        raise ValueError(f"{name} must be an integer")
    return int(value)


class OperationCancelled(BaseException):
    """Must not be turned into a successful result by provider error handlers."""


class PartialReadError(urllib.error.URLError):
    def __init__(self, cause, partial, headers):
        super().__init__(str(cause))
        self.partial = partial
        self.headers = headers


@dataclass
class Operation:
    deadline: float
    cancelled: threading.Event = field(default_factory=threading.Event)

    def remaining(self):
        if self.cancelled.is_set():
            raise OperationCancelled()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("MCP operation deadline exceeded")
        return remaining


operation = contextvars.ContextVar("mcp_operation", default=None)


def checkpoint():
    current = operation.get()
    if current is not None:
        current.remaining()


def sleep(seconds):
    current = operation.get()
    if current is None:
        time.sleep(seconds)
        return
    current.cancelled.wait(min(seconds, current.remaining()))
    checkpoint()


class Response:
    """Small urllib-compatible streaming facade; never buffers a whole download."""

    def __init__(self, runtime, response, timeout, asynchronous):
        self.runtime, self.response = runtime, response
        self.headers = httpx.Headers(response.headers)
        if self.headers.get("Content-Encoding", "identity").lower() != "identity":
            # HTTPX iter_bytes is decoded. Encoded Content-Length no longer
            # describes these bytes; httpcore still checks wire completeness.
            self.headers.pop("Content-Length", None)
        self.status = response.status_code
        self.timeout = timeout
        self.asynchronous = asynchronous
        self.iterator = response.aiter_bytes().__aiter__() if asynchronous else response.iter_bytes()
        self.deadline = time.monotonic() + timeout
        self.buffer = bytearray()
        self.eof = False
        self.closed = False

    def _next(self):
        checkpoint()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP response deadline exceeded")
        try:
            if self.asynchronous:
                return self.runtime.wait(self.iterator.__anext__(), remaining)
            return next(self.iterator)
        except (StopIteration, StopAsyncIteration):
            self.eof = True
            return b""
        except httpx.HTTPError as exc:
            raise urllib.error.URLError(type(exc).__name__) from exc

    def read(self, size=-1):
        limit = self.runtime.max_response_bytes
        if size == 0:
            return b""
        try:
            while not self.eof and (size < 0 or len(self.buffer) < size):
                self.buffer.extend(self._next())
                if size < 0 and len(self.buffer) > limit:
                    raise ValueError("HTTP response exceeds MCP_MAX_RESPONSE_MB")
        except (urllib.error.URLError, TimeoutError) as exc:
            if size < 0 and self.buffer:
                raise PartialReadError(exc, bytes(self.buffer), self.headers) from exc
            raise
        count = len(self.buffer) if size < 0 else min(size, len(self.buffer))
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def __iter__(self):
        while True:
            while b"\n" not in self.buffer and not self.eof:
                self.buffer.extend(self._next())
                if len(self.buffer) > self.runtime.max_response_bytes:
                    raise ValueError("HTTP stream line exceeds MCP_MAX_RESPONSE_MB")
            if not self.buffer:
                return
            end = self.buffer.find(b"\n")
            count = end + 1 if end >= 0 else len(self.buffer)
            line = bytes(self.buffer[:count])
            del self.buffer[:count]
            yield line

    def close(self):
        if not self.closed:
            self.closed = True
            if self.asynchronous:
                if self.runtime.loop is not None:
                    self.runtime.wait(self.response.aclose(), 5, cleanup=True)
            else:
                self.response.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Runtime:
    def __init__(self):
        self.loop = None
        self.loop_thread = None
        self.client = None
        self.sync_client = None
        self.sync_lock = threading.Lock()
        self.futures = set()
        self.futures_lock = threading.Lock()
        self.max_connections = integer_setting("MCP_HTTP_CONNECTIONS", 16, 256)
        self.max_response_bytes = int(positive_setting("MCP_MAX_RESPONSE_MB", 512, 4096) * 1024 * 1024)
        atexit.register(self.close_sync)

    def options(self):
        return {"limits": httpx.Limits(max_connections=self.max_connections,
                    max_keepalive_connections=min(self.max_connections, 8), keepalive_expiry=30),
                "follow_redirects": True}

    @asynccontextmanager
    async def lifespan(self):
        if self.client is not None:
            raise RuntimeError("HTTP lifespan already active")
        self.loop = asyncio.get_running_loop()
        self.loop_thread = threading.get_ident()
        async with httpx.AsyncClient(**self.options()) as client:
            self.client = client
            try:
                yield self
            finally:
                with self.futures_lock:
                    pending = list(self.futures)
                for future in pending:
                    future.cancel()
                self.client = None
                self.loop = None
                self.loop_thread = None
        self.close_sync()

    def close_sync(self):
        with self.sync_lock:
            if self.sync_client is not None:
                self.sync_client.close()
                self.sync_client = None

    def wait(self, coroutine, timeout, cleanup=False):
        loop = self.loop
        if loop is None or loop.is_closed():
            coroutine.close()
            raise RuntimeError("HTTP lifespan is closed")
        if threading.get_ident() == self.loop_thread:
            coroutine.close()
            raise RuntimeError("Sync HTTP adapter must run in a worker thread")
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        with self.futures_lock:
            self.futures.add(future)
        deadline = time.monotonic() + timeout
        try:
            while True:
                budget = deadline - time.monotonic()
                if not cleanup:
                    current = operation.get()
                    if current is not None:
                        budget = min(budget, current.remaining())
                if budget <= 0:
                    raise TimeoutError("HTTP operation deadline exceeded")
                try:
                    return future.result(timeout=min(budget, 0.1))
                except concurrent.futures.TimeoutError:
                    if future.done():
                        return future.result()
        finally:
            if not future.done():
                future.cancel()
            with self.futures_lock:
                self.futures.discard(future)

    def urlopen(self, request, timeout=60):
        checkpoint()
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("HTTP timeout must be finite and positive")
        if isinstance(request, str):
            request = urllib.request.Request(request)
        headers = dict(request.header_items())
        if not any(name.lower() == "accept-encoding" for name in headers):
            headers["Accept-Encoding"] = "identity"
        settings = httpx.Timeout(timeout, connect=min(10, timeout), write=min(60, timeout), pool=min(5, timeout))
        current = operation.get()
        if current is not None:
            timeout = min(timeout, current.remaining())
        deadline = time.monotonic() + timeout
        try:
            asynchronous = self.client is not None
            if asynchronous:
                async def send():
                    for attempt in range(3):
                        content = request.data
                        if content is not None and not isinstance(content, (bytes, str)):
                            content = async_content(content)
                        outgoing = self.client.build_request(request.get_method(), request.full_url,
                                                            headers=headers, content=content, timeout=settings)
                        response = await self.client.send(outgoing, stream=True)
                        if request.get_method() != "GET" or response.status_code not in (429, 502, 503, 504) or attempt == 2:
                            return response
                        delay = retry_delay(response.headers, attempt)
                        await response.aclose()
                        if time.monotonic() + delay >= deadline:
                            raise TimeoutError("HTTP retry exceeds deadline")
                        await asyncio.sleep(delay)
                response = self.wait(send(), timeout)
            else:
                # Library use outside MCP. Do not silently block an async caller.
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError("Use Runtime.lifespan and a worker for synchronous HTTP adapters")
                with self.sync_lock:
                    if self.sync_client is None:
                        self.sync_client = httpx.Client(**self.options())
                    client = self.sync_client
                for attempt in range(3):
                    outgoing = client.build_request(request.get_method(), request.full_url,
                                                    headers=headers, content=request.data, timeout=settings)
                    response = client.send(outgoing, stream=True)
                    if request.get_method() != "GET" or response.status_code not in (429, 502, 503, 504) or attempt == 2:
                        break
                    delay = retry_delay(response.headers, attempt)
                    response.close()
                    if time.monotonic() + delay >= deadline:
                        raise TimeoutError("HTTP retry exceeds deadline")
                    sleep(delay)
            wrapped = Response(self, response, max(0.001, deadline - time.monotonic()), asynchronous)
            if response.status_code >= 400:
                try:
                    body = wrapped.read(65536)
                finally:
                    wrapped.close()
                raise urllib.error.HTTPError(request.full_url, response.status_code,
                                             response.reason_phrase, response.headers, io.BytesIO(body))
            return wrapped
        except httpx.HTTPError as exc:
            raise urllib.error.URLError(type(exc).__name__) from exc


runtime = Runtime()
urlopen = runtime.urlopen


def retry_delay(headers, attempt):
    """Retry-After is honored only inside the request's total budget."""
    from email.utils import parsedate_to_datetime
    try:
        raw = headers.get("Retry-After", "")
        try:
            delay = float(raw)
        except ValueError:
            delay = parsedate_to_datetime(raw).timestamp() - time.time()
        if math.isfinite(delay):
            return max(0, delay)
    except (ValueError, TypeError, OverflowError):
        pass
    return min(0.25 * 2 ** attempt, 2)


async def async_content(chunks):
    """File upload iterators are advanced off the event loop."""
    iterator = iter(chunks)
    sentinel = object()
    try:
        while True:
            chunk = await asyncio.to_thread(next, iterator, sentinel)
            if chunk is sentinel:
                return
            yield chunk
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            await asyncio.to_thread(close)


def multipart(fields, path, boundary):
    """Stream multipart upload; never build a GB-sized bytes payload."""
    from pathlib import Path
    path = Path(path)
    for name, value in fields.items():
        yield f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    filename = path.name.replace('"', '_').replace('\r', '_').replace('\n', '_')
    yield (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
           'Content-Type: application/octet-stream\r\n\r\n').encode()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checkpoint()
            yield chunk
    yield f"\r\n--{boundary}--\r\n".encode()


def multipart_length(fields, path, boundary):
    from pathlib import Path
    path = Path(path)
    filename = path.name.replace('"', '_').replace('\r', '_').replace('\n', '_')
    size = sum(len(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
               for name, value in fields.items())
    size += len((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n').encode())
    return size + path.stat().st_size + len(f"\r\n--{boundary}--\r\n".encode())
