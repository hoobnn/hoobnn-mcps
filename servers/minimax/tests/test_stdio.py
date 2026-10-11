"""Actual MCP stdio, with provider calls replaced by a deterministic offline fixture."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class StdioContracts(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_validation_submission_poll_and_error_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"MINIMAX_JOB_DIR": directory, "MINIMAX_OUT_DIR": directory,
                   "MINIMAX_RESOURCE_MODE": "url", "MINIMAX_API_KEY": "offline-fixture",
                   "MINIMAX_API_HOST": "https://api.minimax.cn", "MCP_TOOL_GROUPS": ""}
            params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).resolve()), "--fixture"], env=env)
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await asyncio.wait_for(session.initialize(), 10)
                    tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                    self.assertIn("generate_video", tools)
                    self.assertIn("music_generation", tools)
                    self.assertNotIn("delete_video_task", tools)
                    self.assertFalse(tools["generate_video"].annotations.read_only_hint)
                    self.assertTrue(tools["list_video_tasks"].annotations.read_only_hint)
                    self.assertIn("reference_audios", tools["generate_video"].input_schema["properties"])
                    self.assertIn("content", tools["generate_video"].input_schema["properties"])
                    failed = await session.call_tool("generate_video", {"prompt": "cat", "duration": 2})
                    self.assertTrue(failed.is_error)
                    submitted = await session.call_tool("generate_video", {"prompt": "cat"})
                    self.assertFalse(submitted.is_error)
                    payload = submitted.structured_content
                    self.assertFalse(payload["completed"])
                    self.assertEqual(payload["task_id"], "123")
                    self.assertEqual(json.loads(submitted.content[0].text), payload)
                    jsonschema.validate(payload, tools["generate_video"].output_schema)
                    completed = await session.call_tool("get_job", {"job_id": payload["job_id"]})
                    self.assertFalse(completed.is_error)
                    self.assertTrue(completed.structured_content["completed"])
                    self.assertEqual(completed.structured_content["files"], ["https://example.test/video.mp4"])
                    failed = await session.call_tool("generate_video", {"prompt": "fail"})
                    self.assertTrue(failed.is_error)
                    self.assertEqual(failed.structured_content["error_code"], 402)
                    capability = (await session.call_tool("list_capabilities", {})).structured_content
                    self.assertEqual(capability["enabled_tools"], sorted(tools))


def fixture():
    from minimax_mcp import client, server
    def request(path, body=None, **kwargs):
        if path == "/v2/video_generation":
            if body["content"][0]["text"] == "fail":
                raise client.APIError("insufficient balance", 402)
            return {"task_id": "123"}
        if path == "/v2/query/video_generation/123":
            return {"task": {"id": "123", "status": "succeeded", "task_type": "generation",
                             "content": {"url": "https://example.test/video.mp4"}}}
        raise AssertionError("Unexpected network operation: " + path)
    client.request = request
    server.main()


if __name__ == "__main__":
    if "--fixture" in sys.argv:
        fixture()
    else:
        unittest.main()
