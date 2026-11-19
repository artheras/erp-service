"""Minimal stdio JSON-RPC 2.0 MCP server for erp-service."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict

from erp_service.agents.warehouse_task import DESCRIPTION as WAREHOUSE_TASK_DESCRIPTION, SCHEMA as WAREHOUSE_TASK_SCHEMA, WAREHOUSE_AGENT
from erp_service.agents.workflow import run_warehouse_analysis
from erp_service.client import WarehouseERPClient
from erp_service.freight import tool_analyze_logistics_data
from erp_service.logistics import (
    CARRIERS_SCHEMA,
    INVENTORY_SCHEMA,
    tool_plan_inventory_policy,
    tool_score_carriers,
)

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
    {
        "name": "erp.inventory.plan",
        "description": INVENTORY_SCHEMA.get("description", "3PL inventory reorder & safety stock policy."),
        "inputSchema": INVENTORY_SCHEMA.get("parameters", {"type": "object", "properties": {}}),
    },
    {
        "name": "erp.carriers.score",
        "description": CARRIERS_SCHEMA.get("description", "3PL carrier scorecard & billing anomaly audit."),
        "inputSchema": CARRIERS_SCHEMA.get("parameters", {"type": "object", "properties": {}}),
    },
    {
        "name": "erp.freight.audit",
        "description": "Audit freight spend, on-time rate, and weight billing anomalies from waybills or CSV/JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "waybills": {"type": "array", "items": {"type": "object"}},
                "file_path": {"type": "string"},
            },
        },
    },
    {
        "name": "erp.warehouse.task",
        "description": WAREHOUSE_TASK_DESCRIPTION,
        "inputSchema": WAREHOUSE_TASK_SCHEMA,
    },
]


async def dispatch_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "erp.warehouse.analyze":
        warehouse_id = str(arguments.get("warehouse_id") or "").strip()
        if not warehouse_id:
            raise ValueError("warehouse_id is required")
        result, snapshot = await run_warehouse_analysis(warehouse_id)
        return {
            "warehouse_id": warehouse_id,
            "result": result.to_dict(),
            "snapshot_counts": {k: len(snapshot.get(k, [])) for k in ("connectors", "inbounds", "skus", "locations")},
        }
    if name == "erp.warehouse.snapshot":
        warehouse_id = str(arguments.get("warehouse_id") or "").strip()
        if not warehouse_id:
            raise ValueError("warehouse_id is required")
        client = WarehouseERPClient.from_env()
        return await client.fetch_snapshot(warehouse_id)
    if name == "erp.inventory.plan":
        return tool_plan_inventory_policy(arguments)
    if name == "erp.carriers.score":
        return tool_score_carriers(arguments)
    if name == "erp.freight.audit":
        return tool_analyze_logistics_data(arguments)
    if name == "erp.warehouse.task":
        payload = dict(arguments)
        payload.setdefault("_warehouse_scope", "mcp")
        return WAREHOUSE_AGENT.handle(payload)
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
