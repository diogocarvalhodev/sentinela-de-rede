from pathlib import Path

from nvr_monitor.sqlite_repo import SQLiteRepository


def test_sqlite_repository_roundtrip(tmp_path: Path):
    db_path = tmp_path / "monitor.db"
    repo = SQLiteRepository(str(db_path))
    repo.ensure_schema()

    units = [
        {
            "unit_name": "Unidade X",
            "recorder_ip": "10.1.1.10",
            "edge_ip": "10.1.1.1",
            "network_cidr": "10.1.1.0/24",
            "max_endpoints_seen": 5,
        }
    ]
    repo.upsert_units(units)

    runtime_state = {
        "schools": {
            "Unidade X": {
                "max_cameras_seen": 5,
                "known_camera_ips": ["10.1.1.20", "10.1.1.21"],
                "last_full_scan_cycle": 3,
                "last_active_cameras": 4,
                "updated_at_epoch": 123,
            }
        }
    }
    repo.save_runtime_state(runtime_state)
    repo.append_baseline_audit("Unidade X", 3, 5, "test")

    loaded_units = repo.load_units()
    loaded_state = repo.load_runtime_state()

    assert len(loaded_units) == 1
    assert loaded_units[0]["unit_name"] == "Unidade X"
    assert loaded_state["schools"]["Unidade X"]["max_cameras_seen"] == 5
    assert loaded_state["schools"]["Unidade X"]["known_camera_ips"] == ["10.1.1.20", "10.1.1.21"]
