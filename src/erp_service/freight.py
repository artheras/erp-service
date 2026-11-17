"""Standalone waybill freight audit helper for warehouse_logistics_cost."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _num(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _load_waybills(params: Dict[str, Any]) -> tuple[List[Dict[str, Any]], str, str | None]:
    if isinstance(params.get("waybills"), list):
        return (
            [w for w in params["waybills"] if isinstance(w, dict)],
            "caller-supplied records",
            None,
        )
    raw_path = params.get("file_path")
    if isinstance(raw_path, str) and raw_path.strip():
        p = Path(raw_path).expanduser()
        if not p.is_file():
            return [], str(p), f"No such file: {p}"
        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            rows = data.get("waybills", data) if isinstance(data, dict) else data
            return (
                [w for w in rows if isinstance(w, dict)] if isinstance(rows, list) else [],
                str(p),
                None,
            )
        with p.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)], str(p), None
    return [], "", "No waybills or file_path supplied."


def tool_analyze_logistics_data(params: Dict[str, Any]) -> Dict[str, Any]:
    waybills, source, err = _load_waybills(params)
    if err:
        return {"success": False, "error": err}
    if not waybills:
        return {"success": False, "error": "No waybills supplied."}

    total_spend = 0.0
    known_on_time = 0
    known_total = 0
    anomalies: List[Dict[str, Any]] = []
    by_carrier: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_spend": 0.0, "on_time": 0, "known": 0}
    )

    for w in waybills:
        carrier = str(w.get("carrier") or "Unknown")
        cost = _num(w.get("total_cost"))
        total_spend += cost
        c_stat = by_carrier[carrier]
        c_stat["count"] += 1
        c_stat["total_spend"] += cost

        raw_ot = w.get("is_on_time")
        if raw_ot is not None and str(raw_ot).strip() != "":
            is_ot = raw_ot if isinstance(raw_ot, bool) else str(raw_ot).strip().lower() in ("true", "1", "yes")
            known_total += 1
            c_stat["known"] += 1
            if is_ot:
                known_on_time += 1
                c_stat["on_time"] += 1

        actual_w = _num(w.get("actual_weight_kg"))
        billed_w = _num(w.get("billed_weight_kg"))
        if actual_w > 0 and billed_w > actual_w * 1.2:
            anomalies.append(
                {
                    "waybill_no": w.get("waybill_no"),
                    "carrier": carrier,
                    "actual_weight_kg": actual_w,
                    "billed_weight_kg": billed_w,
                }
            )

    overall_rate = round(100.0 * known_on_time / known_total, 2) if known_total else None
    carrier_metrics = [
        {
            "carrier": name,
            "count": st["count"],
            "total_spend": round(st["total_spend"], 2),
            "on_time_rate": round(100.0 * st["on_time"] / st["known"], 2) if st["known"] else None,
        }
        for name, st in sorted(by_carrier.items())
    ]
    return {
        "success": True,
        "source": source,
        "data": {
            "data_source": source,
            "total_waybills": len(waybills),
            "total_freight_spend": round(total_spend, 2),
            "overall_on_time_rate": overall_rate,
            "known_delivery_count": known_total,
            "carrier_metrics": carrier_metrics,
            "billing_anomalies": anomalies,
        },
    }
