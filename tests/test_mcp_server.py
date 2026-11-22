"""Tests for the erp-service stdio MCP server."""

import asyncio
import json

from erp_service import mcp_server


def test_mcp_initialize_and_tools_list():
    init = asyncio.run(mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    assert init["result"]["serverInfo"]["name"] == "erp-service"
    listed = asyncio.run(mcp_server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {
        "erp.warehouse.analyze",
        "erp.warehouse.snapshot",
        "erp.inventory.plan",
        "erp.carriers.score",
        "erp.freight.audit",
        "erp.warehouse.task",
        "erp.shipper.digest",
    }


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


def test_mcp_tools_call_freight_audit():
    resp = asyncio.run(
        mcp_server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "erp.freight.audit",
                    "arguments": {
                        "waybills": [
                            {"waybill_no": "WB-1", "carrier": "DHL", "total_cost": 120.0, "is_on_time": True},
                            {"waybill_no": "WB-2", "carrier": "DHL", "total_cost": 80.0, "is_on_time": False},
                        ]
                    },
                },
            }
        )
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["data"]["total_freight_spend"] == 200.0
    assert payload["data"]["overall_on_time_rate"] == 50.0


def test_mcp_tools_call_shipper_digest_enforces_owner_scope():
    resp = asyncio.run(
        mcp_server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "erp.shipper.digest",
                    "arguments": {
                        "owner_id": "ACME",
                        "skus": [
                            {"owner_id": "ACME", "sku": "A100", "on_hand": 5, "daily_demand": [4, 5, 6, 5, 4, 5, 5], "lead_time_days": 5},
                            {"owner_id": "BETA", "sku": "B100", "on_hand": 1, "daily_demand": [8, 8, 8, 8, 8, 8, 8], "lead_time_days": 5},
                        ],
                    },
                },
            }
        )
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["owner_id"] == "ACME"
    sku_ids = [item["sku"] for item in payload["inventory"]["items"]]
    assert sku_ids == ["A100"]

