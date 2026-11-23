---
name: erp-warehouse-ops
description: >
  3PL warehouse analytics, tenant-isolated inventory replenishment, carrier
  scorecards, freight billing audits, and daily shipper digests via erp-service MCP.
---

# 3PL Warehouse & Logistics Operations SOP

Use this workflow whenever analyzing third-party logistics (3PL) inventory,
carrier performance, freight billing anomalies, or preparing a shipper digest.

## Non-Negotiable Tenancy & Approval Rules

1. **Strict shipper isolation**: Never mix records from different `owner_id`
   shippers or analyze unattributed rows. Always pass `owner_id` explicitly.
2. **Stated formulas & data gaps**: Report exact reorder-point, safety-stock, and
   anomaly assumptions; if demand history is insufficient, state the gap instead
   of estimating.
3. **Human approval on PO drafts**: Any replenishment purchase-order draft or
   carrier lane switch is a proposal only and requires explicit human sign-off.

## Standard Tool Sequence

1. **Tenant Daily Digest**: Call `erp.shipper.digest(owner_id, ...)` for a
   consolidated single-shipper operational brief.
2. **Inventory & Replenishment**: Call `erp.inventory.plan` for reorder points,
   safety stock, ABC/XYZ classification, and dead-stock detection.
3. **Carrier & Freight Audit**: Call `erp.carriers.score` and `erp.freight.audit`
   to detect weight/rate billing anomalies and lane switch savings.
4. **Multi-Agent Deep Dive**: Call `erp.warehouse.analyze` for full 5-agent
   warehouse cost, lead-time, inventory health, and inbound exception analysis.
