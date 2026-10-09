"""Local wire faults: no credentials or paid cloud traffic."""
import asyncio
import contextlib
import importlib
import json
import gzip
import os
import sys
import threading
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import anyio
import httpx
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
for name in ("volcengine-ark", "ali-bailian", "doubao-speech"):
    sys.path.insert(0, str(ROOT / "servers" / name / "src"))

from volcengine_ark_mcp import transport
from volcengine_ark_mcp.mcp_runtime import ReliableMCPServer


class WireHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    ports = []
    count = {}

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.respond()

    def respond(self):
        type(self).ports.append(self.client_address[1])
        type(self).count[self.path] = type(self).count.get(self.path, 0) + 1
        count = type(self).count[self.path]
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/long-retry":
            self.send_response(429)
            self.send_header("Retry-After", "120")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/gzip":
            data = gzip.compress(b"media" * 100)
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/slow":
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            for _ in range(10):
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
                time.sleep(0.08)
            return
        status = 503 if self.path in ("/retry", "/post") and count == 1 else 200
        data = b'{"ok":true}'
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Retry-After", "0")
        self.end_headers()
        self.wfile.write(data)


class HTTPFaults(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        WireHandler.ports = []
        WireHandler.count = {}
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), WireHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"
        self.runtime = transport.Runtime()
        self.life = self.runtime.lifespan()
        await self.life.__aenter__()

    async def asyncTearDown(self):
        await self.life.__aexit__(None, None, None)
        await asyncio.to_thread(self.http.shutdown)
        self.http.server_close()

    def read(self, route, timeout=1, method="GET"):
        request = urllib.request.Request(self.base + route, method=method)
        with self.runtime.urlopen(request, timeout=timeout) as response:
            return response.read()

    async def test_connection_reused(self):
        for _ in range(3):
            self.assertEqual(await asyncio.to_thread(self.read, "/ok"), b'{"ok":true}')
        self.assertEqual(len(set(WireHandler.ports)), 1)

    async def test_get_retry_post_not_replayed(self):
        await asyncio.to_thread(self.read, "/retry")
        self.assertEqual(WireHandler.count["/retry"], 2)
        with self.assertRaises(urllib.error.HTTPError):
            await asyncio.to_thread(self.read, "/post", 1, "POST")
        self.assertEqual(WireHandler.count["/post"], 1)

    async def test_slow_trickle_has_total_deadline(self):
        started = time.monotonic()
        with self.assertRaises((TimeoutError, transport.PartialReadError)):
            await asyncio.to_thread(self.read, "/slow", 0.15)
        self.assertLess(time.monotonic() - started, 0.5)

    async def test_cancellation_stops_inflight_read(self):
        op = transport.Operation(time.monotonic() + 5)
        token = transport.operation.set(op)
        try:
            task = asyncio.create_task(asyncio.to_thread(self.read, "/slow", 5))
            await asyncio.sleep(0.08)
            op.cancelled.set()
            with self.assertRaises(transport.OperationCancelled):
                await asyncio.wait_for(task, 0.4)
        finally:
            transport.operation.reset(token)
        self.assertFalse(self.runtime.futures)

    async def test_redirect_has_request_budget(self):
        self.assertEqual(await asyncio.to_thread(self.read, "/redirect"), b'{"ok":true}')
        self.assertEqual(WireHandler.count, {"/redirect": 1, "/ok": 1})

    async def test_long_retry_after_never_retried_early(self):
        self.assertEqual(transport.retry_delay({"Retry-After": "120"}, 0), 120)
        with self.assertRaises(TimeoutError):
            await asyncio.to_thread(self.read, "/long-retry", 0.2)
        self.assertEqual(WireHandler.count["/long-retry"], 1)

    async def test_gzip_does_not_keep_encoded_content_length(self):
        def read():
            with self.runtime.urlopen(self.base + "/gzip") as response:
                self.assertIsNone(response.headers.get("Content-Length"))
                return response.read()
        self.assertEqual(await asyncio.to_thread(read), b"media" * 100)

    async def test_streaming_multipart_length_and_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "样本.wav"
            path.write_bytes(b"audio" * 100)
            fields = {"key": "value", "policy": "abc"}
            body = b"".join(transport.multipart(fields, path, "boundary"))
            self.assertEqual(len(body), transport.multipart_length(fields, path, "boundary"))
            request = urllib.request.Request(self.base + "/upload", data=transport.multipart(fields, path, "boundary"),
                                             headers={"Content-Length": str(len(body))})
            def upload():
                with self.runtime.urlopen(request) as response:
                    return response.read()
            self.assertEqual(await asyncio.to_thread(upload), b'{"ok":true}')


class MCPBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_error_pending_structured_and_annotations(self):
        server = ReliableMCPServer("test")
        @server.tool()
        def failure() -> dict:
            return {"ok": False, "job_id": "id", "error": "bad"}
        @server.tool()
        def pending() -> dict:
            return {"ok": False, "job_state": "running", "job_id": "id", "error": None}
        for name, is_error in (("failure", True), ("pending", False)):
            result = await server.call_tool(name, {})
            self.assertEqual(result.is_error, is_error)
            tool = next(t for t in await server.list_tools() if t.name == name)
            jsonschema.validate(result.structured_content, tool.output_schema)
        result = await server.call_tool("pending", {})
        self.assertTrue(result.structured_content["ok"])
        self.assertFalse(result.structured_content["completed"])
        self.assertEqual(json.loads(result.content[0].text), result.structured_content)
        tools = await server.list_tools()
        self.assertEqual([t.name for t in tools], sorted(t.name for t in tools))
        self.assertTrue(all(t.annotations is not None for t in tools))

    async def test_deadline_and_cancellation_release_worker(self):
        server = ReliableMCPServer("test")
        server.timeout = 0.08
        @server.tool()
        def wait_forever() -> dict:
            transport.sleep(5)
            return {"ok": True}
        started = time.monotonic()
        result = await server.call_tool("wait_forever", {})
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["error_code"], "deadline_exceeded")
        self.assertLess(time.monotonic() - started, 0.3)
        server.timeout = 5
        task = asyncio.create_task(server.call_tool("wait_forever", {}))
        await asyncio.sleep(0.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_timed_out_noncooperative_worker_keeps_physical_slot(self):
        server = ReliableMCPServer("test")
        server.workers = 1
        server.timeout = 0.025
        release = threading.Event()
        started = threading.Event()
        count = 0
        @server.tool()
        def blocked() -> dict:
            nonlocal count
            count += 1
            started.set()
            release.wait(1)
            return {"ok": True}
        try:
            for _ in range(3):
                result = await server.call_tool("blocked", {})
                self.assertTrue(result.is_error)
            self.assertEqual(count, 1)
        finally:
            release.set()
            await asyncio.sleep(0.03)
            server.executor.shutdown(wait=True)

    async def test_local_status_stays_available_when_generation_workers_busy(self):
        server = ReliableMCPServer("test")
        server.workers = 1
        release = threading.Event()
        @server.tool()
        def blocked() -> dict:
            release.wait(1)
            return {"ok": True}
        @server.tool()
        def get_job() -> dict:
            return {"ok": True}
        task = asyncio.create_task(server.call_tool("blocked", {}))
        try:
            await asyncio.sleep(0.02)
            result = await asyncio.wait_for(server.call_tool("get_job", {}), 0.1)
            self.assertFalse(result.is_error)
        finally:
            release.set()
            await task
            server.executor.shutdown(wait=True)
            server.local_executor.shutdown(wait=True)

    async def test_all_package_schemas_help_and_failures(self):
        import logging
        for package in ("volcengine_ark_mcp", "ali_bailian_mcp", "doubao_speech_mcp"):
            server = importlib.import_module(package + ".server").mcp
            tools = await server.list_tools()
            for tool in tools:
                jsonschema.Draft202012Validator.check_schema(tool.input_schema)
                jsonschema.Draft202012Validator.check_schema(tool.output_schema)
            result = await server.call_tool("get_tool_help", {"tool": "missing"})
            self.assertTrue(result.is_error)
            result = await server.call_tool("get_tool_help", {"tool": tools[0].name})
            self.assertTrue(result.structured_content["ok"])
            capability_tool = "list_speech_capabilities" if package == "doubao_speech_mcp" else "list_capabilities"
            capability = (await server.call_tool(capability_tool, {})).structured_content
            self.assertEqual(capability["enabled_tools"], [tool.name for tool in tools])
        self.assertGreaterEqual(logging.getLogger("httpx").getEffectiveLevel(), logging.WARNING)

    async def test_compact_results_opt_in_raw_response(self):
        server = ReliableMCPServer("test")
        @server.tool()
        def chat() -> dict:
            return {"ok": True, "content": "answer", "response": {"choices": []}}
        compact = (await server.call_tool("chat", {})).structured_content
        verbose = (await server.call_tool("chat", {"include_response": True})).structured_content
        self.assertNotIn("response", compact)
        self.assertIn("response", verbose)

    async def test_progress_stops_and_optional_failure_is_ignored(self):
        from unittest.mock import AsyncMock
        server = ReliableMCPServer("test")
        @server.tool()
        async def delayed() -> dict:
            await asyncio.sleep(0.02)
            return {"ok": True}
        context = AsyncMock()
        # The SDK requires a real Context; use its direct-request Context and
        # patch only the optional reporting method.
        from mcp.server.mcpserver import Context
        context = Context(mcp_server=server)
        with patch.object(type(context), "report_progress", new_callable=AsyncMock) as report:
            result = await server.call_tool("delayed", {}, context)
            self.assertFalse(result.is_error)
            self.assertEqual(report.await_count, 1)
            await asyncio.sleep(0.03)
            self.assertEqual(report.await_count, 1)
        with patch.object(type(context), "report_progress", new_callable=AsyncMock, side_effect=RuntimeError("unsupported")):
            self.assertFalse((await server.call_tool("delayed", {}, context)).is_error)

    async def test_invalid_settings_and_groups(self):
        for value in ("nan", "inf", "0", "-1"):
            with patch.dict(os.environ, {"MCP_TOOL_TIMEOUT_SEC": value}):
                with self.assertRaises(ValueError):
                    ReliableMCPServer("test")
        with patch.dict(os.environ, {"MCP_TOOL_GROUPS": "image"}):
            server = ReliableMCPServer("test", groups={"image": {"generate_image"}, "language": {"chat"}})
            @server.tool()
            def chat() -> dict:
                return {"ok": True}
            @server.tool()
            def generate_image() -> dict:
                return {"ok": True}
            self.assertEqual({t.name for t in await server.list_tools()}, {"generate_image", "get_tool_help"})


if __name__ == "__main__":
    unittest.main()
