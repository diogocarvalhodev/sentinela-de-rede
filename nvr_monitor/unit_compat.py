from __future__ import annotations

from typing import Any, Dict, List, Sequence


def first_non_empty(raw: Dict[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        parsed = str(value).strip()
        if parsed:
            return parsed
    return ""


def first_int(raw: Dict[str, Any], keys: Sequence[str], default: int = 0) -> int:
    for key in keys:
        value = raw.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


def build_unit_record(raw_unit: Dict[str, Any], subnet_prefix: int, baseline_from_state: int) -> Dict[str, Any]:
    unit_name = first_non_empty(raw_unit, ["unit_name", "site_name", "location_name", "school", "name"])
    recorder_ip = first_non_empty(raw_unit, ["recorder_ip", "nvr_ip", "gateway_ip"])
    edge_ip = first_non_empty(raw_unit, ["edge_ip", "firewall_ip", "router_ip"])

    baseline_from_file = first_int(raw_unit, ["total_cameras", "expected_endpoints", "baseline_total"], default=0)
    network_cidr = first_non_empty(raw_unit, ["network_cidr", "subnet_cidr"]) or f"{recorder_ip}/{subnet_prefix}"
    max_endpoints_seen = max(baseline_from_file, baseline_from_state)

    return {
        "unit_name": unit_name,
        "recorder_ip": recorder_ip,
        "edge_ip": edge_ip,
        "network_cidr": network_cidr,
        "max_endpoints_seen": max_endpoints_seen,
        "name": unit_name,
        "nvr_ip": recorder_ip,
        "firewall_ip": edge_ip,
        "subnet_cidr": network_cidr,
        "max_cameras_seen": max_endpoints_seen,
    }
