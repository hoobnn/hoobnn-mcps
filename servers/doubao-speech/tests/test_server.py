"""Real stdio transport smoke: initialize, discover JSON schemas, call tools."""
import asyncio
import json
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class StdioSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_validation_without_credentials(self):
        command = str(Path(sys.executable).parent / "doubao-speech-mcp")
        async with stdio_client(StdioServerParameters(command=command)) as streams:
            async with ClientSession(*streams) as client:
                await asyncio.wait_for(client.initialize(), 10)
                tools = {t.name: t for t in (await client.list_tools()).tools}
                for original in ("text_to_speech", "speech_to_text", "generate_audio"):
                    self.assertIn(original, tools)
                self.assertIn("request", tools["generate_podcast"].input_schema["required"])
                result = await client.call_tool("list_speech_capabilities", {})
                self.assertFalse(result.is_error)
                catalog = json.loads(result.content[0].text)
                for names in catalog["products"].values():
                    self.assertTrue(set(names) <= tools.keys())
                self.assertIn(catalog["usage_examples"]["tool"], tools)
                # Validate actual client-facing examples against discovered schemas.
                # This catches renamed fields and missing required parameters.
                import jsonschema
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
                invalid = await client.call_tool("submit_long_text_speech", {"request": {}})
                self.assertFalse(json.loads(invalid.content[0].text)["ok"])


if __name__ == "__main__":
    unittest.main()
