#!/usr/bin/env python3
"""
NVR Monitoring Exporter - Versão Windows (Sem Docker)
Replica o comportamento do IP Utility da Intelbras para monitorar NVRs e câmeras
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import platform
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Dict, List, Sequence, Set, Tuple

from prometheus_client import Counter, Gauge, Info, start_http_server
from nvr_monitor.config import (
    Settings as ModularSettings,
    build_metric_labels as modular_build_metric_labels,
    classify_exception as modular_classify_exception,
    school_metric_labels as modular_school_metric_labels,
)
from nvr_monitor.discovery import NetworkScanner as ModularNetworkScanner
from nvr_monitor.sqlite_repo import SQLiteRepository
from nvr_monitor.unit_compat import build_unit_record

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _parse_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _parse_int(value: str, default: int, minimum: int | None = None) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        logger.warning("Valor inteiro inválido '%s'. Usando padrão %s.", value, default)
        return default
    if minimum is not None and parsed < minimum:
        logger.warning("Valor %s menor que o mínimo %s. Usando padrão %s.", parsed, minimum, default)
        return default
    return parsed


def _parse_ports(value: str, default: List[int]) -> List[int]:
    if not value:
        return default

    parsed_ports: List[int] = []
    for item in value.split(','):
        chunk = item.strip()
        if not chunk:
            continue
        try:
            port = int(chunk)
            if 1 <= port <= 65535:
                parsed_ports.append(port)
            else:
                logger.warning("Porta fora do range válido ignorada: %s", chunk)
        except ValueError:
            logger.warning("Porta inválida ignorada: %s", chunk)

    return parsed_ports or default


def classify_exception(exc: Exception) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return 'timeout'
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return 'socket_timeout'
    if isinstance(exc, JSONDecodeError):
        return 'json_decode'
    if isinstance(exc, FileNotFoundError):
        return 'file_not_found'
    if isinstance(exc, PermissionError):
        return 'permission_error'
    if isinstance(exc, KeyError):
        return 'missing_key'
    if isinstance(exc, ValueError):
        return 'invalid_value'
    if isinstance(exc, OSError):
        return 'os_error'
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

    @staticmethod
    def from_env(default_units_file: str, script_dir: str) -> 'Settings':
        default_ports = [80, 554, 8000, 8080, 37777]
        units_file = os.getenv('UNITS_FILE') or os.getenv('SCHOOLS_FILE') or default_units_file

        return Settings(
            exporter_port=_parse_int(os.getenv('EXPORTER_PORT'), 8000, minimum=1),
            scan_interval=_parse_int(os.getenv('SCAN_INTERVAL_SECONDS'), 300, minimum=10),
            inter_school_delay=_parse_int(os.getenv('INTER_SCHOOL_DELAY_SECONDS'), 0, minimum=0),
            ping_timeout_seconds=_parse_int(os.getenv('PING_TIMEOUT_SECONDS'), 1, minimum=1),
            socket_timeout_seconds=float(os.getenv('SOCKET_TIMEOUT_SECONDS', '0.5')),
            subnet_workers=_parse_int(os.getenv('SUBNET_WORKERS'), 50, minimum=1),
            school_workers=_parse_int(os.getenv('SCHOOL_WORKERS'), 1, minimum=1),
            subnet_prefix=_parse_int(os.getenv('SUBNET_PREFIX'), 24, minimum=8),
            full_scan_every_cycles=_parse_int(os.getenv('FULL_SCAN_EVERY_CYCLES'), 6, minimum=1),
            max_hosts_per_scan=_parse_int(os.getenv('MAX_HOSTS_PER_SCAN'), 0, minimum=0),
            camera_ports=_parse_ports(os.getenv('CAMERA_PORTS'), default_ports),
            expose_nvr_ip_label=_parse_bool(os.getenv('EXPOSE_NVR_IP_LABEL'), False),
            units_file=units_file,
        )


def build_metric_labels(expose_nvr_ip_label: bool) -> List[str]:
    return ['school', 'nvr_ip'] if expose_nvr_ip_label else ['school']


def school_metric_labels(school_name: str, nvr_ip: str, expose_nvr_ip_label: bool) -> Dict[str, str]:
    labels = {'school': school_name}
    if expose_nvr_ip_label:
        labels['nvr_ip'] = nvr_ip
    return labels


def _first_non_empty(raw: Dict[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        parsed = str(value).strip()
        if parsed:
            return parsed
    return ''


def _first_int(raw: Dict[str, Any], keys: Sequence[str], default: int = 0) -> int:
    for key in keys:
        value = raw.get(key)
        if value in (None, ''):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("Valor inteiro inválido para '%s': %s", key, value)
    return default

class NetworkScanner:
    """Scanner de rede para descobrir câmeras IP"""

    def __init__(self, timeout: int = 1, socket_timeout: float = 0.5, max_workers: int = 50, camera_ports: List[int] | None = None):
        self.timeout = timeout
        self.socket_timeout = socket_timeout
        self.max_workers = max_workers
        self.camera_ports = camera_ports or [80, 554, 8000, 8080, 37777]
        self.is_windows = platform.system().lower() == 'windows'

    def ping_host(self, ip: str) -> bool:
        """
        Faz ping em um host para verificar se está ativo
        
        Args:
            ip: Endereço IP para fazer ping
            
        Returns:
            True se o host respondeu, False caso contrário
        """
        try:
            # Comando ping varia entre Windows e Linux
            param = '-n' if self.is_windows else '-c'
            timeout_param = '-w' if self.is_windows else '-W'
            
            command = ['ping', param, '1', timeout_param, str(self.timeout * 1000 if self.is_windows else self.timeout), ip]
            
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout + 1,
                encoding='utf-8',
                errors='ignore'
            )
            
            # Verificar se ping foi bem-sucedido
            if result.returncode != 0:
                return False
            
            # No Windows, verificar se não é resposta de "Host inacessível" do gateway
            if self.is_windows:
                output = result.stdout.lower()
                # Detectar respostas de gateway dizendo que host está inacessível
                if any(phrase in output for phrase in [
                    'host de destino inacessível',
                    'destination host unreachable',
                    'unreachable',
                    'inacessível'
                ]):
                    logger.debug(f"Ping para {ip}: Gateway reportou host inacessível")
                    return False
            
            return True
            
        except Exception as e:
            logger.debug(f"Erro ao fazer ping em {ip}: {e}")
            return False

    def check_camera_ports(self, ip: str) -> bool:
        """
        Verifica se alguma porta comum de câmera está aberta
        
        Args:
            ip: Endereço IP para verificar
            
        Returns:
            True se alguma porta de câmera está aberta
        """
        for port in self.camera_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.socket_timeout)
                result = sock.connect_ex((ip, port))
                sock.close()

                if result == 0:
                    logger.debug(f"Câmera encontrada em {ip}:{port}")
                    return True

            except Exception as e:
                logger.debug(f"Erro ao verificar porta {port} em {ip}: {e}")
                continue

        return False

    def scan_host(self, ip: str) -> Tuple[str, bool]:
        """
        Escaneia um único host (ping + verificação de portas)
        
        Args:
            ip: Endereço IP para escanear
            
        Returns:
            Tupla (ip, is_camera) onde is_camera indica se é uma câmera
        """
        # Primeiro faz ping
        if not self.ping_host(ip):
            return (ip, False)
        
        # Se respondeu ao ping, verifica portas de câmera
        is_camera = self.check_camera_ports(ip)
        
        if is_camera:
            logger.info(f"Câmera ativa encontrada: {ip}")

        return (ip, is_camera)

    def scan_ip_list(self, ips: List[str], excluded_ips: Set[str] | None = None) -> Set[str]:
        """Valida uma lista de IPs já conhecidos de câmeras."""
        excluded_ips = excluded_ips or set()
        candidate_ips = [ip for ip in ips if ip not in excluded_ips]
        cameras_found: Set[str] = set()

        if not candidate_ips:
            return cameras_found

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(candidate_ips))) as executor:
            futures = {executor.submit(self.scan_host, ip): ip for ip in candidate_ips}
            for future in as_completed(futures):
                ip, is_camera = future.result()
                if is_camera:
                    cameras_found.add(ip)

        return cameras_found

    def scan_subnet(self, subnet_cidr: str, excluded_ips: Set[str] | None = None, max_hosts: int = 0) -> Set[str]:
        """
        Escaneia uma sub-rede e retorna os IPs de câmeras ativas.

        Args:
            subnet_cidr: Faixa a escanear no formato CIDR
            excluded_ips: IPs que devem ser ignorados
            max_hosts: Limite de hosts para escaneamento (0 = sem limite)

        Returns:
            Conjunto com IPs de câmeras ativas
        """
        excluded_ips = excluded_ips or set()

        try:
            network = ipaddress.IPv4Network(subnet_cidr, strict=False)
            logger.info(f"Iniciando scan da sub-rede {network}")

            hosts_to_scan = [str(ip) for ip in network.hosts() if str(ip) not in excluded_ips]
            if max_hosts > 0 and len(hosts_to_scan) > max_hosts:
                logger.warning(
                    "Sub-rede %s tem %s hosts e será limitada a %s para proteger recursos.",
                    network,
                    len(hosts_to_scan),
                    max_hosts,
                )
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

            logger.info(f"Scan completo: {len(cameras_found)} câmeras encontradas em {network}")
            return cameras_found

        except Exception as e:
            logger.error(f"Erro ao escanear sub-rede {subnet_cidr}: {e}")
            return set()


# Sprint 2: bindings modulares para reduzir acoplamento no monolito existente.
Settings = ModularSettings
NetworkScanner = ModularNetworkScanner
build_metric_labels = modular_build_metric_labels
school_metric_labels = modular_school_metric_labels
classify_exception = modular_classify_exception


class NVRMonitor:
    """Monitor de NVRs e câmeras"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.units_file = settings.units_file
        self.repository = SQLiteRepository(settings.sqlite_db_path)
        self.repository.ensure_schema()
        self.scanner = NetworkScanner(
            timeout=settings.ping_timeout_seconds,
            socket_timeout=settings.socket_timeout_seconds,
            max_workers=settings.subnet_workers,
            camera_ports=settings.camera_ports,
        )

        self.metric_labels = build_metric_labels(settings.expose_nvr_ip_label)
        self.nvr_status = Gauge('nvr_status', 'Status do NVR (1=online, 0=offline)', self.metric_labels)
        self.cameras_active = Gauge('cameras_active', 'Número de câmeras ativas descobertas', self.metric_labels)
        self.cameras_total = Gauge('cameras_total', 'Total de câmeras esperadas', self.metric_labels)
        self.cameras_missing = Gauge('cameras_missing', 'Câmeras faltando (total - ativas)', self.metric_labels)
        self.scan_duration = Gauge('scan_duration_seconds', 'Tempo de duração do scan por escola', ['school'])
        self.school_info = Info('school_info', 'Informações da escola', ['school'])

        self.exporter_cycle_duration = Gauge('exporter_cycle_duration_seconds', 'Duração total de um ciclo de monitoramento')
        self.exporter_cycle_lag = Gauge('exporter_cycle_lag_seconds', 'Quanto o ciclo excedeu o intervalo configurado')
        self.exporter_cycle_overrun_total = Counter('exporter_cycle_overrun_total', 'Número de ciclos que excederam o intervalo configurado')
        self.school_scan_total = Counter('school_scan_total', 'Execuções de monitoramento por escola', ['school', 'outcome'])
        self.school_scan_errors_total = Counter('school_scan_errors_total', 'Falhas por escola e tipo de erro', ['school', 'error_type'])
        self.discovery_scan_total = Counter('discovery_scan_total', 'Scans de descoberta executados por tipo', ['school', 'scan_type'])

        self._state_lock = threading.Lock()
        self.runtime_state = self.load_runtime_state()
        self.units = self.load_units()
        # Alias legado para evitar quebra em pontos já existentes.
        self.schools = self.units

    def _labels(self, unit_name: str, recorder_ip: str) -> Dict[str, str]:
        return school_metric_labels(unit_name, recorder_ip, self.settings.expose_nvr_ip_label)

    def _state_entry(self, unit_name: str) -> Dict[str, Any]:
        schools_state = self.runtime_state.setdefault('schools', {})
        state = schools_state.setdefault(unit_name, {})
        state.setdefault('max_cameras_seen', 0)
        state.setdefault('known_camera_ips', [])
        state.setdefault('last_full_scan_cycle', 0)
        state.setdefault('last_active_cameras', 0)
        state.setdefault('updated_at_epoch', 0)
        return state

    def load_runtime_state(self) -> Dict[str, Any]:
        try:
            loaded = self.repository.load_runtime_state()
            if isinstance(loaded, dict):
                loaded.setdefault('schools', {})
                return loaded
            logger.warning("Estado inválido no SQLite. Recriando estado em memória.")
            return {'schools': {}}
        except Exception as e:
            logger.error("Erro ao carregar estado SQLite (%s): %s", self.settings.sqlite_db_path, e)
            return {'schools': {}}

    def persist_runtime_state(self) -> None:
        self.repository.save_runtime_state(self.runtime_state)

    def append_baseline_audit(self, unit_name: str, old_value: int, new_value: int, reason: str) -> None:
        self.repository.append_baseline_audit(unit_name, old_value, new_value, reason)

    def load_units(self) -> List[Dict]:
        """Carrega unidades do SQLite e usa JSON apenas para bootstrap inicial."""
        try:
            db_units = self.repository.load_units()
            if db_units:
                logger.info("Carregadas %s unidades do SQLite (%s)", len(db_units), self.settings.sqlite_db_path)
                return db_units

            if not os.path.exists(self.units_file):
                logger.warning(
                    "Nenhuma unidade no SQLite e arquivo de bootstrap ausente: %s",
                    self.units_file,
                )
                return []

            # utf-8-sig lida tanto com UTF-8 normal quanto UTF-8 com BOM
            with open(self.units_file, 'r', encoding='utf-8-sig') as f:
                loaded = json.load(f)

            if not isinstance(loaded, list):
                logger.error("Arquivo %s deve conter uma lista de unidades.", self.units_file)
                return []

            units: List[Dict] = []
            invalid_entries = 0
            for idx, raw_unit in enumerate(loaded, start=1):
                if not isinstance(raw_unit, dict):
                    invalid_entries += 1
                    logger.warning("Entrada inválida na posição %s: esperado objeto.", idx)
                    continue

                unit_name = _first_non_empty(raw_unit, ['unit_name', 'site_name', 'location_name', 'school', 'name'])
                recorder_ip = _first_non_empty(raw_unit, ['recorder_ip', 'nvr_ip', 'gateway_ip'])

                if not unit_name or not recorder_ip:
                    invalid_entries += 1
                    logger.warning("Unidade ignorada por falta de unit_name/recorder_ip na posição %s.", idx)
                    continue

                try:
                    ipaddress.ip_address(recorder_ip)
                except ValueError:
                    invalid_entries += 1
                    logger.warning("IP do recorder inválido para %s: %s", unit_name, recorder_ip)
                    continue

                state = self._state_entry(unit_name)
                baseline_from_state = int(state.get('max_cameras_seen', 0) or 0)
                unit = build_unit_record(
                    raw_unit=raw_unit,
                    subnet_prefix=self.settings.subnet_prefix,
                    baseline_from_state=baseline_from_state,
                )

                edge_ip = unit.get('edge_ip', '')
                if edge_ip:
                    try:
                        ipaddress.ip_address(edge_ip)
                    except ValueError:
                        logger.warning("Edge IP inválido para %s: %s. Campo será ignorado.", unit_name, edge_ip)
                        unit['edge_ip'] = ''
                        unit['firewall_ip'] = ''

                units.append(unit)

            if invalid_entries:
                logger.warning("Total de entradas inválidas ignoradas: %s", invalid_entries)

            if units:
                self.repository.upsert_units(units)
                logger.info("Bootstrap concluído: %s unidades persistidas no SQLite.", len(units))

            logger.info(f"Carregadas {len(units)} unidades válidas do arquivo {self.units_file}")
            return units

        except Exception as e:
            logger.error(f"Erro ao carregar arquivo {self.units_file}: {e}")
            return []

    def load_schools(self) -> List[Dict]:
        """Alias legado para manter compatibilidade com a base atual."""
        return self.load_units()

    def should_full_scan(self, school_state: Dict[str, Any], cycle_number: int) -> bool:
        if not school_state.get('known_camera_ips'):
            return True
        last_full = int(school_state.get('last_full_scan_cycle', 0) or 0)
        return (cycle_number - last_full) >= self.settings.full_scan_every_cycles

    def monitor_school(self, school: Dict, cycle_number: int) -> None:
        """
        Monitora uma escola específica

        Args:
            school: Dicionário com dados da escola
            cycle_number: número atual do ciclo de monitoramento
        """
        unit_name = school.get('unit_name', school['name'])
        recorder_ip = school.get('recorder_ip', school['nvr_ip'])
        edge_ip = school.get('edge_ip', school.get('firewall_ip', ''))
        network_cidr = school.get('network_cidr', school.get('subnet_cidr', f"{recorder_ip}/{self.settings.subnet_prefix}"))
        labels = self._labels(unit_name, recorder_ip)

        logger.info(f"=== Monitorando {unit_name} (Recorder: {recorder_ip}) ===")

        start_time = time.time()

        school_state = self._state_entry(unit_name)
        known_camera_ips: Set[str] = set(school_state.get('known_camera_ips', []))
        max_cameras_seen = int(school.get('max_endpoints_seen', school.get('max_cameras_seen', 0)) or 0)
        max_cameras_seen = max(max_cameras_seen, int(school_state.get('max_cameras_seen', 0) or 0))
        school['max_endpoints_seen'] = max_cameras_seen
        school['max_cameras_seen'] = max_cameras_seen

        try:
            # 1. Verifica status do NVR
            nvr_online = self.scanner.ping_host(recorder_ip)
            self.nvr_status.labels(**labels).set(1 if nvr_online else 0)

            logger.info(f"{unit_name} - Recorder Status: {'ONLINE' if nvr_online else 'OFFLINE'}")

            active_camera_ips: Set[str] = set()
            excluded_ips = {recorder_ip}
            if edge_ip:
                excluded_ips.add(edge_ip)

            # 2. Se NVR está online, usa estratégia incremental para reduzir custo
            if nvr_online:
                run_full_scan = self.should_full_scan(school_state, cycle_number)

                if run_full_scan:
                    self.discovery_scan_total.labels(school=unit_name, scan_type='full').inc()
                    active_camera_ips = self.scanner.scan_subnet(
                        subnet_cidr=network_cidr,
                        excluded_ips=excluded_ips,
                        max_hosts=self.settings.max_hosts_per_scan,
                    )
                    school_state['last_full_scan_cycle'] = cycle_number
                    known_camera_ips = set(active_camera_ips)
                else:
                    self.discovery_scan_total.labels(school=unit_name, scan_type='incremental').inc()
                    active_camera_ips = self.scanner.scan_ip_list(sorted(known_camera_ips), excluded_ips=excluded_ips)

                    # Queda abrupta aciona scan completo de confirmação no mesmo ciclo
                    if known_camera_ips and len(active_camera_ips) < max(1, int(len(known_camera_ips) * 0.5)):
                        logger.warning(
                            "%s - Queda abrupta (%s/%s). Executando full scan de confirmação.",
                            unit_name,
                            len(active_camera_ips),
                            len(known_camera_ips),
                        )
                        self.discovery_scan_total.labels(school=unit_name, scan_type='fallback_full').inc()
                        active_camera_ips = self.scanner.scan_subnet(
                            subnet_cidr=network_cidr,
                            excluded_ips=excluded_ips,
                            max_hosts=self.settings.max_hosts_per_scan,
                        )
                        school_state['last_full_scan_cycle'] = cycle_number
                        known_camera_ips = set(active_camera_ips)

                active_cameras = len(active_camera_ips)

                # Atualização automática: total só pode subir, nunca descer
                if active_cameras > max_cameras_seen:
                    old_value = max_cameras_seen
                    logger.warning(
                        "%s - Total de câmeras atualizado automaticamente: %s -> %s",
                        unit_name,
                        old_value,
                        active_cameras,
                    )
                    school['max_cameras_seen'] = active_cameras
                    school['max_endpoints_seen'] = active_cameras
                    max_cameras_seen = active_cameras

                    with self._state_lock:
                        school_state['max_cameras_seen'] = max_cameras_seen
                        school_state['updated_at_epoch'] = int(time.time())
                        self.persist_runtime_state()
                        self.append_baseline_audit(unit_name, old_value, active_cameras, 'auto_increase_on_discovery')

                self.cameras_active.labels(**labels).set(active_cameras)

                missing = max(0, max_cameras_seen - active_cameras)
                self.cameras_missing.labels(**labels).set(missing)

                logger.info(f"{unit_name} - Câmeras: {active_cameras}/{max_cameras_seen} ativas")
                if missing > 0:
                    logger.warning(f"{unit_name} - {missing} câmeras faltando!")

                outcome = 'ok'
            else:
                # NVR offline = câmeras indisponíveis
                self.cameras_active.labels(**labels).set(0)
                self.cameras_missing.labels(**labels).set(max_cameras_seen)
                logger.warning(f"{unit_name} - Recorder OFFLINE, impossível verificar câmeras")
                outcome = 'nvr_offline'

            with self._state_lock:
                school_state['known_camera_ips'] = sorted(known_camera_ips)
                school_state['max_cameras_seen'] = max_cameras_seen
                school_state['last_active_cameras'] = len(active_camera_ips)
                school_state['updated_at_epoch'] = int(time.time())
                self.persist_runtime_state()

            # 3. Atualiza métricas fixas
            self.cameras_total.labels(**labels).set(max_cameras_seen)
            self.school_info.labels(school=unit_name).info({
                'nvr_ip': recorder_ip,
                'firewall_ip': edge_ip,
                'subnet_cidr': network_cidr,
                'tracked_camera_ips': str(len(known_camera_ips)),
            })

            self.school_scan_total.labels(school=unit_name, outcome=outcome).inc()

        except Exception as e:
            error_type = classify_exception(e)
            self.school_scan_errors_total.labels(school=unit_name, error_type=error_type).inc()
            self.school_scan_total.labels(school=unit_name, outcome='error').inc()
            logger.exception("Erro ao monitorar %s (%s): %s", unit_name, error_type, e)

        # 4. Tempo de scan
        duration = time.time() - start_time
        self.scan_duration.labels(school=unit_name).set(duration)

        logger.info(f"{unit_name} - Scan completo em {duration:.2f}s")

    def run_cycle(self, cycle_number: int) -> None:
        if self.settings.school_workers == 1:
            for i, school in enumerate(self.units, 1):
                self.monitor_school(school, cycle_number)
                if self.settings.inter_school_delay > 0 and i < len(self.units):
                    logger.info(
                        "Aguardando %ss antes da próxima escola... (%s/%s)",
                        self.settings.inter_school_delay,
                        i,
                        len(self.units),
                    )
                    time.sleep(self.settings.inter_school_delay)
            return

        with ThreadPoolExecutor(max_workers=self.settings.school_workers) as executor:
            futures = [executor.submit(self.monitor_school, school, cycle_number) for school in self.units]
            for future in as_completed(futures):
                future.result()

    def run(self, interval: int = 300) -> None:
        """
        Loop principal de monitoramento

        Args:
            interval: Intervalo em segundos entre cada scan completo
        """
        logger.info(f"Iniciando monitoramento com intervalo de {interval}s")

        cycle_number = 0
        while True:
            try:
                cycle_number += 1
                cycle_start = time.time()

                logger.info("=" * 60)
                logger.info("INICIANDO NOVO CICLO DE MONITORAMENTO (#%s)", cycle_number)
                logger.info("=" * 60)

                self.run_cycle(cycle_number)

                cycle_duration = time.time() - cycle_start
                self.exporter_cycle_duration.set(cycle_duration)

                remaining = interval - cycle_duration
                if remaining > 0:
                    self.exporter_cycle_lag.set(0)
                    logger.info(f"Aguardando {remaining:.2f}s até próximo ciclo...")
                    time.sleep(remaining)
                else:
                    lag = abs(remaining)
                    self.exporter_cycle_lag.set(lag)
                    self.exporter_cycle_overrun_total.inc()
                    logger.warning(
                        "Ciclo levou %.2fs (intervalo %.2fs). Próximo ciclo iniciará imediatamente.",
                        cycle_duration,
                        float(interval),
                    )

            except KeyboardInterrupt:
                logger.info("Monitoramento interrompido pelo usuário")
                break
            except Exception as e:
                logger.exception(f"Erro no loop principal: {e}")
                time.sleep(60)


def main():
    """Função principal"""
    # Configurações
    # Procura units.json no diretório atual ou no mesmo diretório do script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    units_file = os.path.join(script_dir, 'units.json')
    
    if not os.path.exists(units_file):
        units_file = 'units.json'

    settings = Settings.from_env(default_units_file=units_file, script_dir=script_dir)
    
    logger.info("=" * 60)
    logger.info("SISTEMA DE MONITORAMENTO NVR - VERSÃO WINDOWS")
    logger.info("=" * 60)
    logger.info("Arquivo de unidades: %s", settings.units_file)
    logger.info("Banco SQLite: %s", settings.sqlite_db_path)
    logger.info("Porta do exporter: %s", settings.exporter_port)
    logger.info("Intervalo de scan: %ss", settings.scan_interval)
    logger.info("Workers por sub-rede: %s", settings.subnet_workers)
    logger.info("Workers entre escolas: %s", settings.school_workers)
    logger.info("Full scan a cada %s ciclo(s)", settings.full_scan_every_cycles)
    logger.info("Expose NVR IP label: %s", settings.expose_nvr_ip_label)
    logger.info("=" * 60)

    # O arquivo de unidades e usado apenas para bootstrap inicial.
    if not os.path.exists(settings.units_file):
        logger.warning(
            "Arquivo de bootstrap não encontrado (%s). O exporter tentará carregar unidades do SQLite.",
            settings.units_file,
        )

    # Inicia servidor Prometheus
    start_http_server(settings.exporter_port)
    logger.info(f"Prometheus exporter iniciado na porta {settings.exporter_port}")
    logger.info(f"Métricas disponíveis em http://localhost:{settings.exporter_port}/metrics")
    logger.info("")
    logger.info("Para parar o monitoramento, pressione Ctrl+C")
    logger.info("=" * 60)

    # Inicia monitoramento
    monitor = NVRMonitor(settings)
    if not monitor.units:
        logger.error("Nenhuma unidade válida para monitorar. Encerrando.")
        return
    monitor.run(interval=settings.scan_interval)


if __name__ == '__main__':
    main()