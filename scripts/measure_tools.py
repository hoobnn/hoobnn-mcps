"""Measure discovery cost without credentials or provider requests."""
import argparse
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("server", choices=("volcengine-ark", "ali-bailian", "doubao-speech"))
    parser.add_argument("--groups", default="")
    args = parser.parse_args()
    os.environ["MCP_TOOL_GROUPS"] = args.groups
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "servers" / args.server / "src"))
    server = importlib.import_module(args.server.replace("-", "_") + "_mcp.server").mcp
    tools = await server.list_tools()
    wire = json.dumps([tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                       for tool in tools], ensure_ascii=False)
    print(json.dumps({"server": args.server, "groups": args.groups or "all", "tools": len(tools),
                      "schema_bytes": len(wire.encode()),
                      "description_chars": sum(len(tool.description or "") for tool in tools)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
