"""Tests for the erp-service stdio MCP server."""

import asyncio
import json

from erp_service import mcp_server


def test_mcp_initialize_and_tools_list():
    init = asyncio.run(mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    assert init["result"]["serverInfo"]["name"] == "erp-service"
    listed = asyncio.run(mcp_server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {"erp.warehouse.analyze", "erp.warehouse.snapshot"}


def test_mcp_tools_call_analyze(monkeypatch):
    class _FakeClient:
        async def fetch_snapshot(self, warehouse_id):
            return {
                "connectors": [{"name": "4PX", "delay_minutes": 5, "failed_jobs": 0}],
                "inbounds": [],
                "skus": [],
                "locations": [],
            }

    monkeypatch.setattr(mcp_server.WarehouseERPClient, "from_env", classmethod(lambda cls: _FakeClient()))
    resp = asyncio.run(
        mcp_server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "erp.warehouse.analyze", "arguments": {"warehouse_id": "WH-CN-01"}},
            }
        )
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["warehouse_id"] == "WH-CN-01"
    assert payload["result"]["final_signal"]
