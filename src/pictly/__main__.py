"""Pictly CLI: mcp | list | tool | inspect | version."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .tools import call_tool, tool_catalog


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pictly", description="Image toolkit for agents (MCP server + CLI)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("mcp", help="run the MCP stdio server")
    sub.add_parser("list", help="list tools")
    sub.add_parser("version", help="print version")

    t = sub.add_parser("tool", help="run one tool")
    t.add_argument("name")
    t.add_argument("--json", default="{}", help="arguments as JSON")

    i = sub.add_parser("inspect", help="image info")
    i.add_argument("path")

    args = p.parse_args(argv)

    if args.cmd in (None, "list"):
        for tool in tool_catalog():
            print(f"{tool['name']:12} {tool['description']}")
        return 0

    if args.cmd == "version":
        print(f"pictly {__version__}")
        return 0

    if args.cmd == "inspect":
        print(json.dumps(call_tool("inspect", {"path": args.path}), indent=2))
        return 0

    if args.cmd == "mcp":
        from .mcp.server import serve
        serve()
        return 0

    if args.cmd == "tool":
        try:
            payload = json.loads(args.json or "{}")
        except json.JSONDecodeError as exc:
            print(f"invalid --json: {exc}", file=sys.stderr)
            return 2
        out = call_tool(args.name, payload)
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
