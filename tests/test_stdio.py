"""Each standalone installed entrypoint must work over real stdio."""
import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import jsonschema
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


class StandaloneStdio(unittest.IsolatedAsyncioTestCase):
    async def test_all_servers_initialize_discover_call_and_shutdown(self):
        for name in ("volcengine-ark", "ali-bailian", "doubao-speech"):
            with self.subTest(server=name), tempfile.TemporaryDirectory() as directory:
                command = ROOT / "servers" / name / ".venv" / "bin" / (name + "-mcp")
                params = StdioServerParameters(command=str(command), env={"ARK_JOB_DIR": directory,
                    "BAILIAN_JOB_DIR": directory, "MCP_TOOL_GROUPS": "help", "MCP_TOOL_TIMEOUT_SEC": "10"})
                started = time.monotonic()
                async with stdio_client(params) as streams:
                    async with ClientSession(*streams) as client:
                        await asyncio.wait_for(client.initialize(), 10)
                        tools = (await client.list_tools()).tools
                        names = [tool.name for tool in tools]
                        self.assertEqual(names, sorted(names))
                        self.assertIn("get_tool_help", names)
                        self.assertNotIn("generate_image", names)
                        result = await client.call_tool("get_tool_help", {"tool": "missing"})
                        self.assertTrue(result.is_error)
                        self.assertEqual(json.loads(result.content[0].text), result.structured_content)
                        result = await client.call_tool("get_tool_help", {"tool": "get_tool_help"})
                        self.assertFalse(result.is_error)
                        tool = next(tool for tool in tools if tool.name == "get_tool_help")
                        jsonschema.validate(result.structured_content, tool.output_schema)
                        self.assertTrue(tool.annotations.read_only_hint)
                        self.assertFalse(tool.annotations.open_world_hint)
                        capability_tool = "list_speech_capabilities" if name == "doubao-speech" else "list_capabilities"
                        capability = (await client.call_tool(capability_tool, {})).structured_content
                        self.assertEqual(capability["enabled_tools"], names)
                        self.assertEqual(capability["selected_groups"], ["help"])
                self.assertLess(time.monotonic() - started, 10)


if __name__ == "__main__":
    unittest.main()
