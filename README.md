# erp-service

Standalone Warehouse ERP & Logistics analysis service and MCP server extracted from `aria-code`.

## Features

- **Read-only Warehouse ERP Client** (`erp_service.client.WarehouseERPClient`) for fetching connectors, inbounds, SKUs, and storage locations.
- **5-Agent Warehouse Analysis Team** (`erp_service.agents.workflow.run_warehouse_analysis`):
  - `warehouse_logistics_cost`
  - `warehouse_fulfillment_leadtime`
  - `warehouse_inventory_health`
  - `warehouse_inbound_exceptions`
  - `warehouse_logistics_sync`
- **MCP Server (`erp-service-mcp`)**: Exposes `erp.warehouse.analyze` and `erp.warehouse.snapshot` over stdio JSON-RPC 2.0 for `aria-code`.

## Installation & Testing

```bash
pip install -e .
pytest -q
```

## Connecting from `aria-code`

Add the server to your `.mcp.json` or `~/.aria/mcp.json`:

```json
{
  "mcpServers": {
    "erp-service": {
      "command": "erp-service-mcp",
      "env": {
        "WAREHOUSE_ERP_BASE_URL": "https://erp.example.com",
        "WAREHOUSE_ERP_TOKEN": "..."
      }
    }
  }
}
```
