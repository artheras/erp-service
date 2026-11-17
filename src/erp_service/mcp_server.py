"""Minimal stdio JSON-RPC 2.0 MCP server for erp-service."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict

from erp_service.agents.workflow import run_warehouse_analysis
from erp_service.client import WarehouseERPClient

SERVER_INFO = {"name": "erp-service", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "erp.warehouse.analyze",
        "description": "Run read-only 5-agent Warehouse ERP analysis for a warehouse_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "warehouse_id": {"type": "string", "description": "Warehouse identifier, e.g. WH-CN-01"}
            },
            "required": ["warehouse_id"],
        },
    },
    {
        "name": "erp.warehouse.snapshot",
        "description": "Fetch raw read-only ERP snapshot (connectors, inbounds, skus, locations) for a warehouse_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "warehouse_id": {"type": "string", "description": "Warehouse identifier, e.g. WH-CN-01"}
            },
            "required": ["warehouse_id"],
        },
    },
]


async def dispatch_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    warehouse_id = str(arguments.get("warehouse_id") or "").strip()
    if not warehouse_id:
        raise ValueError("warehouse_id is required")
    if name == "erp.warehouse.analyze":
        result, snapshot = await run_warehouse_analysis(warehouse_id)
        return {
            "warehouse_id": warehouse_id,
            "result": result.to_dict(),
            "snapshot_counts": {k: len(snapshot.get(k, [])) for k in ("connectors", "inbounds", "skus", "locations")},
        }
    if name == "erp.warehouse.snapshot":
        client = WarehouseERPClient.from_env()
        return await client.fetch_snapshot(warehouse_id)
    raise ValueError(f"Unknown tool: {name}")


async def handle_request(req: Dict[str, Any]) -> Dict[str, Any] | None:
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params") or {}

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        try:
            payload = await dispatch_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }
    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()
            continue
        resp = asyncio.run(handle_request(req))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
