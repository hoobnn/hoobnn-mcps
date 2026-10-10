"""Real stdio transport smoke: initialize, discover JSON schemas, call tools."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

COMMAND = str(Path(sys.executable).parent / "doubao-speech-mcp")
OPTIONAL = {"open_realtime_session", "send_realtime_event", "receive_realtime_events", "close_realtime_session",
            "manage_word_table", "speech_console"}


def params(**env):
    return StdioServerParameters(command=COMMAND, env={**os.environ, **env})


class StdioSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_default_surface_is_typed_and_hides_optional_groups(self):
        with tempfile.TemporaryDirectory() as jobs:
            async with stdio_client(params(DOUBAO_SPEECH_JOB_DIR=jobs, MCP_TOOL_GROUPS="")) as streams:
                async with ClientSession(*streams) as client:
                    await asyncio.wait_for(client.initialize(), 10)
                    tools = {t.name: t for t in (await client.list_tools()).tools}
                    self.assertFalse(OPTIONAL & tools.keys())
                    # Only the raw escape hatch takes a whole official request body.
                    for name, tool in tools.items():
                        if name != "speech_raw_request":
                            self.assertNotIn("request", tool.input_schema.get("properties", {}), name)
                    catalog = json.loads((await client.call_tool("list_speech_capabilities", {})).content[0].text)
                    self.assertEqual(catalog["disabled_groups"], ["admin", "realtime"])
                    self.assertIn("MCP_TOOL_GROUPS=", catalog["enable_hint"])
                    self.assertEqual(sorted(catalog["enabled_tools"]), sorted(tools))
                    invalid = await client.call_tool("summarize_meeting", {"file_url": "/local/meeting.wav"})
                    self.assertTrue(invalid.is_error)
                    missing = await client.call_tool("get_job", {"task_id": "unknown"})
                    self.assertTrue(missing.is_error)

    async def test_examples_match_schemas_with_all_groups(self):
        import jsonschema
        groups = "speech,voice,jobs,realtime,admin,help"
        async with stdio_client(params(MCP_TOOL_GROUPS=groups)) as streams:
            async with ClientSession(*streams) as client:
                await asyncio.wait_for(client.initialize(), 10)
                tools = {t.name: t for t in (await client.list_tools()).tools}
                self.assertTrue(OPTIONAL <= tools.keys())
                catalog = json.loads((await client.call_tool("list_speech_capabilities", {})).content[0].text)
                self.assertEqual(catalog["disabled_groups"], [])
                for names in catalog["products"].values():
                    self.assertTrue(set(names) <= tools.keys())
                self.assertIn(catalog["usage_examples"]["tool"], tools)
                # Validate actual client-facing examples against discovered schemas.
                for product in catalog["usage_examples"]["products"]:
                    result = await client.call_tool("get_speech_usage_examples", {"product": product})
                    guide = json.loads(result.content[0].text)
                    self.assertTrue(guide["ok"])
                    for example in guide["examples"]:
                        with self.subTest(product=product, example=example["name"]):
                            jsonschema.validate(example["arguments"], tools[example["tool"]].input_schema)
                filtered = await client.call_tool("get_speech_usage_examples", {"category": "timing"})
                guide = json.loads(filtered.content[0].text)
                self.assertEqual(set(guide["categories"]), {"timing"})
                self.assertTrue(all(e["category"] == "timing" for e in guide["examples"]))
                unknown = await client.call_tool("get_speech_usage_examples", {"product": "missing"})
                self.assertFalse(json.loads(unknown.content[0].text)["ok"])


if __name__ == "__main__":
    unittest.main()
