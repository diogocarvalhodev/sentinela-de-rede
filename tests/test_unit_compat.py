from nvr_monitor.unit_compat import build_unit_record, first_int, first_non_empty


def test_first_non_empty_uses_first_populated_key():
    raw = {"site_name": "", "name": "Unit 01", "unit_name": ""}
    assert first_non_empty(raw, ["unit_name", "site_name", "name"]) == "Unit 01"


def test_first_int_parses_with_fallback():
    raw = {"baseline_total": "not-number", "expected_endpoints": "9"}
    assert first_int(raw, ["baseline_total", "expected_endpoints"], default=2) == 9
    assert first_int({}, ["baseline_total"], default=2) == 2


def test_build_unit_record_preserves_legacy_and_canonical_fields():
    raw = {
        "name": "Escola Modelo",
        "nvr_ip": "10.10.0.10",
        "firewall_ip": "10.10.0.1",
        "total_cameras": 12,
    }

    record = build_unit_record(raw, subnet_prefix=24, baseline_from_state=10)

    assert record["unit_name"] == "Escola Modelo"
    assert record["recorder_ip"] == "10.10.0.10"
    assert record["edge_ip"] == "10.10.0.1"
    assert record["network_cidr"] == "10.10.0.10/24"
    assert record["max_endpoints_seen"] == 12

    assert record["name"] == "Escola Modelo"
    assert record["nvr_ip"] == "10.10.0.10"
    assert record["firewall_ip"] == "10.10.0.1"
    assert record["subnet_cidr"] == "10.10.0.10/24"
    assert record["max_cameras_seen"] == 12


def test_build_unit_record_prefers_explicit_cidr_and_largest_baseline():
    raw = {
        "unit_name": "Unidade B",
        "recorder_ip": "172.20.5.43",
        "network_cidr": "172.20.5.0/24",
        "baseline_total": 7,
    }

    record = build_unit_record(raw, subnet_prefix=24, baseline_from_state=9)

    assert record["network_cidr"] == "172.20.5.0/24"
    assert record["max_endpoints_seen"] == 9
