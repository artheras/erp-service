"""Minimal stdio or Streamable HTTP JSON-RPC 2.0 MCP server for erp-service."""

from __future__ import annotations

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
}

TOOLS = [
    {
        "name": "erp.warehouse.analyze",
        "description": "Run read-only 5-agent Warehouse ERP analysis for a warehouse_id.",
        "annotations": _READ_ONLY_ANNOTATIONS,
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
        "annotations": _READ_ONLY_ANNOTATIONS,
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
        "annotations": _READ_ONLY_ANNOTATIONS,
        "inputSchema": INVENTORY_SCHEMA.get("parameters", {"type": "object", "properties": {}}),
    },
    {
        "name": "erp.carriers.score",
        "description": CARRIERS_SCHEMA.get("description", "3PL carrier scorecard & billing anomaly audit."),
        "annotations": _READ_ONLY_ANNOTATIONS,
        "inputSchema": CARRIERS_SCHEMA.get("parameters", {"type": "object", "properties": {}}),
    },
    {
        "name": "erp.freight.audit",
        "description": "Audit freight spend, on-time rate, and weight billing anomalies from waybills or CSV/JSON.",
        "annotations": _READ_ONLY_ANNOTATIONS,
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
        "annotations": _READ_ONLY_ANNOTATIONS,
        "inputSchema": WAREHOUSE_TASK_SCHEMA,
    },
    {
        "name": "erp.shipper.digest",
        "description": "Build a tenant-isolated daily shipper digest (reorder alerts, stockout risks, freight billing anomalies, and carrier lane switch recommendations) strictly scoped to a single owner_id.",
        "annotations": _READ_ONLY_ANNOTATIONS,
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_id": {"type": "string", "description": "Required shipper/tenant identifier (e.g. ACME)."},
                "skus": {"type": "array", "items": {"type": "object"}, "description": "Inventory SKU records."},
                "inventory_file": {"type": "string", "description": "Path to inventory CSV/JSON file."},
                "waybills": {"type": "array", "items": {"type": "object"}, "description": "Waybill records."},
                "waybills_file": {"type": "string", "description": "Path to waybills CSV/JSON file."},
            },
            "required": ["owner_id"],
        },
    },
]


def _build_shipper_digest(arguments: Dict[str, Any]) -> Dict[str, Any]:
    import os
    from erp_service.logistics.tenancy import OWNER_SCOPE_ENV

    owner_id = str(arguments.get("owner_id") or "").strip()
    if not owner_id:
        raise ValueError("owner_id is required for erp.shipper.digest")

    prev_scope = os.environ.get(OWNER_SCOPE_ENV)
    os.environ[OWNER_SCOPE_ENV] = owner_id
    try:
        inventory_report = None
        carrier_report = None
        problems: list[str] = []

        if arguments.get("skus") or arguments.get("inventory_file"):
            inv_args: Dict[str, Any] = {"owner_id": owner_id}
            if arguments.get("skus") is not None:
                inv_args["skus"] = arguments["skus"]
            if arguments.get("inventory_file"):
                inv_args["file_path"] = arguments["inventory_file"]
            inv_res = tool_plan_inventory_policy(inv_args)
            if inv_res.get("success"):
                inventory_report = inv_res.get("data", inv_res)
            else:
                problems.append(str(inv_res.get("error") or "inventory analysis failed"))

        if arguments.get("waybills") or arguments.get("waybills_file"):
            wb_args: Dict[str, Any] = {"owner_id": owner_id}
            if arguments.get("waybills") is not None:
                wb_args["waybills"] = arguments["waybills"]
            if arguments.get("waybills_file"):
                wb_args["file_path"] = arguments["waybills_file"]
            wb_res = tool_score_carriers(wb_args)
            if wb_res.get("success"):
                carrier_report = wb_res.get("data", wb_res)
            else:
                problems.append(str(wb_res.get("error") or "carrier analysis failed"))

        if inventory_report is None and carrier_report is None and not problems:
            problems.append("Provide skus/inventory_file and/or waybills/waybills_file")

        return {
            "success": len(problems) == 0,
            "owner_id": owner_id,
            "scope": {"mode": "single_owner", "owner_id": owner_id, "client_facing": True},
            "inventory": inventory_report,
            "carriers": carrier_report,
            "problems": problems,
        }
    finally:
        if prev_scope is None:
            os.environ.pop(OWNER_SCOPE_ENV, None)
        else:
            os.environ[OWNER_SCOPE_ENV] = prev_scope


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
    if name == "erp.shipper.digest":
        return _build_shipper_digest(arguments)
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="erp-service-mcp",
        description="ERP Service MCP server (stdio by default, or Streamable HTTP).",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport mode (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host.")
    parser.add_argument("--port", type=int, default=8766, help="HTTP bind port.")
    return parser


def make_http_handler():
    class _McpHttpHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._send_json(200, {"status": "ok", "service": SERVER_INFO["name"], "transport": "streamable-http"})
            else:
                self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/", "/mcp"):
                self._send_json(404, {"error": "Not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                req = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._send_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})
                return
            resp = asyncio.run(handle_request(req))
            if resp is None:
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._send_json(200, resp)

    return _McpHttpHandler


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.transport == "streamable-http":
        server = ThreadingHTTPServer((args.host, args.port), make_http_handler())
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return

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
