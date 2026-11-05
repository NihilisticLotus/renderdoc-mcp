"""Compare the live MCP tools/list input contract with its reviewed snapshot."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "tests" / "fixtures" / "mcp_tool_schema.json"


async def read_contract() -> list[dict[str, object]]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from renderdoc_mcp.server.runtime import main; raise SystemExit(main())",
            "run-mcp",
        ],
        env=os.environ.copy(),
        cwd=str(ROOT),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()

    contract: list[dict[str, object]] = []
    for tool in response.tools:
        value = tool.model_dump(by_alias=True, exclude_none=True, mode="json")
        contract.append(
            {
                "name": value["name"],
                "inputSchema": value.get("inputSchema", {}),
            }
        )
    return sorted(contract, key=lambda item: str(item["name"]))


def serialized(contract: list[dict[str, object]]) -> str:
    return json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--update",
        action="store_true",
        help="replace the reviewed baseline after an intentional schema change",
    )
    args = parser.parse_args()

    actual = await read_contract()
    actual_json = json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    actual_hash = hashlib.sha256(serialized(actual).encode("utf-8")).hexdigest()

    if args.update:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(actual_json, encoding="utf-8")
        print(f"Updated {args.baseline}: {len(actual)} tools, schema sha256 {actual_hash}")
        return 0

    if not args.baseline.is_file():
        print(f"Missing schema baseline: {args.baseline}", file=sys.stderr)
        return 2

    expected = json.loads(args.baseline.read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256(serialized(expected).encode("utf-8")).hexdigest()
    if actual != expected:
        expected_names = {str(item["name"]) for item in expected}
        actual_names = {str(item["name"]) for item in actual}
        print("MCP input schema changed; review the tool diff before updating the baseline.", file=sys.stderr)
        print(f"Expected: {len(expected)} tools, sha256 {expected_hash}", file=sys.stderr)
        print(f"Actual:   {len(actual)} tools, sha256 {actual_hash}", file=sys.stderr)
        print(f"Added: {sorted(actual_names - expected_names)}", file=sys.stderr)
        print(f"Removed: {sorted(expected_names - actual_names)}", file=sys.stderr)
        return 1

    print(f"MCP input schema OK: {len(actual)} tools, schema sha256 {actual_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
