from __future__ import annotations

import ipaddress
import logging
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)


class NetworkScanner:
    """Scanner de rede para descobrir endpoints ativos por ping e portas."""

    def __init__(
        self,
        timeout: int = 1,
        socket_timeout: float = 0.5,
        max_workers: int = 50,
        camera_ports: List[int] | None = None,
    ):
        self.timeout = timeout
        self.socket_timeout = socket_timeout
        self.max_workers = max_workers
        self.camera_ports = camera_ports or [80, 554, 8000, 8080, 37777]
        self.is_windows = platform.system().lower() == "windows"

    def ping_host(self, ip: str) -> bool:
        try:
            param = "-n" if self.is_windows else "-c"
            timeout_param = "-w" if self.is_windows else "-W"
            timeout_value = str(self.timeout * 1000 if self.is_windows else self.timeout)
            command = ["ping", param, "1", timeout_param, timeout_value, ip]

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout + 1,
                encoding="utf-8",
                errors="ignore",
            )

            if result.returncode != 0:
                return False

            if self.is_windows:
                output = result.stdout.lower()
                if any(
                    phrase in output
                    for phrase in [
                        "host de destino inacessivel",
                        "destination host unreachable",
                        "unreachable",
                        "inacessivel",
                    ]
                ):
                    return False

            return True
        except Exception:
            return False

    def check_camera_ports(self, ip: str) -> bool:
        for port in self.camera_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.socket_timeout)
                result = sock.connect_ex((ip, port))
                sock.close()

                if result == 0:
                    return True
            except Exception:
                continue

        return False

    def scan_host(self, ip: str) -> Tuple[str, bool]:
        if not self.ping_host(ip):
            return (ip, False)

        is_camera = self.check_camera_ports(ip)
        if is_camera:
            logger.info("Endpoint ativo encontrado: %s", ip)
        return (ip, is_camera)

    def scan_ip_list(self, ips: List[str], excluded_ips: Set[str] | None = None) -> Set[str]:
        excluded_ips = excluded_ips or set()
        candidate_ips = [ip for ip in ips if ip not in excluded_ips]
        found: Set[str] = set()

        if not candidate_ips:
            return found

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(candidate_ips))) as executor:
            futures = {executor.submit(self.scan_host, ip): ip for ip in candidate_ips}
            for future in as_completed(futures):
                ip, is_camera = future.result()
                if is_camera:
                    found.add(ip)

        return found

    def scan_subnet(self, subnet_cidr: str, excluded_ips: Set[str] | None = None, max_hosts: int = 0) -> Set[str]:
        excluded_ips = excluded_ips or set()

        try:
            network = ipaddress.IPv4Network(subnet_cidr, strict=False)
            hosts_to_scan = [str(ip) for ip in network.hosts() if str(ip) not in excluded_ips]

            if max_hosts > 0 and len(hosts_to_scan) > max_hosts:
                hosts_to_scan = hosts_to_scan[:max_hosts]

            if not hosts_to_scan:
                return set()

            cameras_found: Set[str] = set()
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self.scan_host, ip): ip for ip in hosts_to_scan}
                for future in as_completed(futures):
                    ip, is_camera = future.result()
                    if is_camera:
                        cameras_found.add(ip)

            return cameras_found
        except Exception:
            return set()
