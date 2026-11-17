"""Warehouse ERP multi-agent team."""

from erp_service.base import WAREHOUSE_SCHEME

from .fulfillment_leadtime import FulfillmentLeadTimeAgent
from .inbound_exceptions import InboundExceptionAgent
from .inventory_health import InventoryHealthAgent
from .logistics_cost import LogisticsCostOptimizerAgent
from .logistics_sync import LogisticsSyncAgent

AGENT_CLASSES = {
    "warehouse_logistics_cost": LogisticsCostOptimizerAgent,
    "warehouse_fulfillment_leadtime": FulfillmentLeadTimeAgent,
    "warehouse_inventory_health": InventoryHealthAgent,
    "warehouse_inbound_exceptions": InboundExceptionAgent,
    "warehouse_logistics_sync": LogisticsSyncAgent,
}

WAREHOUSE_TEAM = list(AGENT_CLASSES.keys())

__all__ = [
    "AGENT_CLASSES",
    "FulfillmentLeadTimeAgent",
    "InboundExceptionAgent",
    "InventoryHealthAgent",
    "LogisticsCostOptimizerAgent",
    "LogisticsSyncAgent",
    "WAREHOUSE_SCHEME",
    "WAREHOUSE_TEAM",
]
