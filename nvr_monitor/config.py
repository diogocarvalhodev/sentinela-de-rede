from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Dict, List


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str | None, default: int, minimum: int | None = None) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def parse_ports(value: str | None, default: List[int]) -> List[int]:
    if not value:
        return default

    parsed_ports: List[int] = []
    for item in value.split(","):
        chunk = item.strip()
        if not chunk:
            continue
        try:
            port = int(chunk)
            if 1 <= port <= 65535:
                parsed_ports.append(port)
        except ValueError:
            continue

    return parsed_ports or default


def classify_exception(exc: Exception) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "socket_timeout"
    if isinstance(exc, JSONDecodeError):
        return "json_decode"
    if isinstance(exc, FileNotFoundError):
        return "file_not_found"
    if isinstance(exc, PermissionError):
        return "permission_error"
    if isinstance(exc, KeyError):
        return "missing_key"
    if isinstance(exc, ValueError):
        return "invalid_value"
    if isinstance(exc, OSError):
        return "os_error"
    return exc.__class__.__name__.lower()


@dataclass(frozen=True)
class Settings:
    exporter_port: int
    scan_interval: int
    inter_school_delay: int
    ping_timeout_seconds: int
    socket_timeout_seconds: float
    subnet_workers: int
    school_workers: int
    subnet_prefix: int
    full_scan_every_cycles: int
    max_hosts_per_scan: int
    camera_ports: List[int]
    expose_nvr_ip_label: bool
    units_file: str
    sqlite_db_path: str

    @staticmethod
    def from_env(default_units_file: str, script_dir: str) -> "Settings":
        default_ports = [80, 554, 8000, 8080, 37777]
        # Compatibilidade: UNITS_FILE e novo; SCHOOLS_FILE segue aceito como fallback.
        units_file = os.getenv("UNITS_FILE") or os.getenv("SCHOOLS_FILE") or default_units_file

        return Settings(
            exporter_port=parse_int(os.getenv("EXPORTER_PORT"), 8000, minimum=1),
            scan_interval=parse_int(os.getenv("SCAN_INTERVAL_SECONDS"), 300, minimum=10),
            inter_school_delay=parse_int(os.getenv("INTER_SCHOOL_DELAY_SECONDS"), 0, minimum=0),
            ping_timeout_seconds=parse_int(os.getenv("PING_TIMEOUT_SECONDS"), 1, minimum=1),
            socket_timeout_seconds=float(os.getenv("SOCKET_TIMEOUT_SECONDS", "0.5")),
            subnet_workers=parse_int(os.getenv("SUBNET_WORKERS"), 50, minimum=1),
            school_workers=parse_int(os.getenv("SCHOOL_WORKERS"), 1, minimum=1),
            subnet_prefix=parse_int(os.getenv("SUBNET_PREFIX"), 24, minimum=8),
            full_scan_every_cycles=parse_int(os.getenv("FULL_SCAN_EVERY_CYCLES"), 6, minimum=1),
            max_hosts_per_scan=parse_int(os.getenv("MAX_HOSTS_PER_SCAN"), 0, minimum=0),
            camera_ports=parse_ports(os.getenv("CAMERA_PORTS"), default_ports),
            expose_nvr_ip_label=parse_bool(os.getenv("EXPOSE_NVR_IP_LABEL"), False),
            units_file=units_file,
            sqlite_db_path=os.getenv("SQLITE_DB_PATH", os.path.join(script_dir, "data", "monitor.db")),
        )


def build_metric_labels(expose_nvr_ip_label: bool) -> List[str]:
    return ["school", "nvr_ip"] if expose_nvr_ip_label else ["school"]


def school_metric_labels(school_name: str, nvr_ip: str, expose_nvr_ip_label: bool) -> Dict[str, str]:
    labels = {"school": school_name}
    if expose_nvr_ip_label:
        labels["nvr_ip"] = nvr_ip
    return labels
