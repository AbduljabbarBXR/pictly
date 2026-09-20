"""Minimal MCP stdio server (JSON-RPC 2.0, newline delimited). No dependencies."""

from __future__ import annotations

import json
import sys

from ..tools import call_tool, tool_catalog

PROTOCOL = "2024-11-05"


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "pictly", "version": _version()},
        }}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tool_catalog()}}
    if method == "tools/call":
        params = msg.get("params") or {}
        payload = call_tool(params.get("name"), params.get("arguments") or {})
        text = json.dumps(payload.get("result") if payload.get("ok") else {"error": payload.get("error")}, indent=2)
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "isError": not payload.get("ok"),
            "content": [{"type": "text", "text": text}],
        }}
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def _version() -> str:
    from .. import __version__
    return __version__


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
