from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict, List


class SQLiteRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS units (
                    unit_name TEXT PRIMARY KEY,
                    recorder_ip TEXT NOT NULL,
                    edge_ip TEXT NOT NULL DEFAULT '',
                    network_cidr TEXT NOT NULL,
                    max_endpoints_seen INTEGER NOT NULL DEFAULT 0,
                    created_at_epoch INTEGER NOT NULL,
                    updated_at_epoch INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runtime_state (
                    unit_name TEXT PRIMARY KEY,
                    max_cameras_seen INTEGER NOT NULL DEFAULT 0,
                    last_full_scan_cycle INTEGER NOT NULL DEFAULT 0,
                    last_active_cameras INTEGER NOT NULL DEFAULT 0,
                    updated_at_epoch INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS known_camera_ips (
                    unit_name TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    PRIMARY KEY (unit_name, ip)
                );

                CREATE TABLE IF NOT EXISTS baseline_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_epoch INTEGER NOT NULL,
                    unit_name TEXT NOT NULL,
                    old_max_cameras INTEGER NOT NULL,
                    new_max_cameras INTEGER NOT NULL,
                    reason TEXT NOT NULL
                );
                """
            )

    def upsert_units(self, units: List[Dict[str, Any]]) -> None:
        now = int(time.time())
        with self._connect() as conn:
            for unit in units:
                unit_name = str(unit.get("unit_name", unit.get("name", ""))).strip()
                recorder_ip = str(unit.get("recorder_ip", unit.get("nvr_ip", ""))).strip()
                if not unit_name or not recorder_ip:
                    continue

                edge_ip = str(unit.get("edge_ip", unit.get("firewall_ip", ""))).strip()
                network_cidr = str(unit.get("network_cidr", unit.get("subnet_cidr", ""))).strip()
                max_endpoints_seen = int(unit.get("max_endpoints_seen", unit.get("max_cameras_seen", 0)) or 0)

                conn.execute(
                    """
                    INSERT INTO units (
                        unit_name, recorder_ip, edge_ip, network_cidr, max_endpoints_seen,
                        created_at_epoch, updated_at_epoch
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(unit_name) DO UPDATE SET
                        recorder_ip=excluded.recorder_ip,
                        edge_ip=excluded.edge_ip,
                        network_cidr=excluded.network_cidr,
                        max_endpoints_seen=excluded.max_endpoints_seen,
                        updated_at_epoch=excluded.updated_at_epoch
                    """,
                    (unit_name, recorder_ip, edge_ip, network_cidr, max_endpoints_seen, now, now),
                )

    def load_units(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT unit_name, recorder_ip, edge_ip, network_cidr, max_endpoints_seen
                FROM units
                ORDER BY unit_name
                """
            ).fetchall()

        units: List[Dict[str, Any]] = []
        for row in rows:
            unit_name = row["unit_name"]
            recorder_ip = row["recorder_ip"]
            edge_ip = row["edge_ip"]
            network_cidr = row["network_cidr"]
            max_endpoints_seen = int(row["max_endpoints_seen"] or 0)
            units.append(
                {
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
            )
        return units

    def load_runtime_state(self) -> Dict[str, Any]:
        schools: Dict[str, Dict[str, Any]] = {}

        with self._connect() as conn:
            state_rows = conn.execute(
                """
                SELECT unit_name, max_cameras_seen, last_full_scan_cycle, last_active_cameras, updated_at_epoch
                FROM runtime_state
                """
            ).fetchall()

            for row in state_rows:
                schools[row["unit_name"]] = {
                    "max_cameras_seen": int(row["max_cameras_seen"] or 0),
                    "known_camera_ips": [],
                    "last_full_scan_cycle": int(row["last_full_scan_cycle"] or 0),
                    "last_active_cameras": int(row["last_active_cameras"] or 0),
                    "updated_at_epoch": int(row["updated_at_epoch"] or 0),
                }

            ip_rows = conn.execute(
                """
                SELECT unit_name, ip
                FROM known_camera_ips
                ORDER BY unit_name, ip
                """
            ).fetchall()

            for row in ip_rows:
                unit_name = row["unit_name"]
                schools.setdefault(
                    unit_name,
                    {
                        "max_cameras_seen": 0,
                        "known_camera_ips": [],
                        "last_full_scan_cycle": 0,
                        "last_active_cameras": 0,
                        "updated_at_epoch": 0,
                    },
                )
                schools[unit_name]["known_camera_ips"].append(row["ip"])

        return {"schools": schools}

    def save_runtime_state(self, runtime_state: Dict[str, Any]) -> None:
        schools = runtime_state.get("schools", {})

        with self._connect() as conn:
            for unit_name, state in schools.items():
                conn.execute(
                    """
                    INSERT INTO runtime_state (
                        unit_name, max_cameras_seen, last_full_scan_cycle, last_active_cameras, updated_at_epoch
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(unit_name) DO UPDATE SET
                        max_cameras_seen=excluded.max_cameras_seen,
                        last_full_scan_cycle=excluded.last_full_scan_cycle,
                        last_active_cameras=excluded.last_active_cameras,
                        updated_at_epoch=excluded.updated_at_epoch
                    """,
                    (
                        unit_name,
                        int(state.get("max_cameras_seen", 0) or 0),
                        int(state.get("last_full_scan_cycle", 0) or 0),
                        int(state.get("last_active_cameras", 0) or 0),
                        int(state.get("updated_at_epoch", 0) or 0),
                    ),
                )

                conn.execute("DELETE FROM known_camera_ips WHERE unit_name = ?", (unit_name,))
                known_ips = sorted(set(state.get("known_camera_ips", [])))
                conn.executemany(
                    "INSERT INTO known_camera_ips (unit_name, ip) VALUES (?, ?)",
                    [(unit_name, ip) for ip in known_ips],
                )

    def append_baseline_audit(self, unit_name: str, old_value: int, new_value: int, reason: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO baseline_audit (
                    timestamp_epoch, unit_name, old_max_cameras, new_max_cameras, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (int(time.time()), unit_name, int(old_value), int(new_value), reason),
            )
