import socket
import subprocess
from json import JSONDecodeError

from nvr_monitor.config import (
    build_metric_labels,
    classify_exception,
    parse_bool,
    parse_int,
    parse_ports,
    school_metric_labels,
)


def test_parse_bool_truthy_and_falsey_values():
    assert parse_bool("true", False) is True
    assert parse_bool("1", False) is True
    assert parse_bool("no", True) is False


def test_parse_int_with_minimum_guard():
    assert parse_int("15", 10, minimum=5) == 15
    assert parse_int("2", 10, minimum=5) == 10
    assert parse_int("invalid", 10, minimum=5) == 10


def test_parse_ports_filters_invalid_and_keeps_valid():
    ports = parse_ports("80,invalid,70000, 554", [1234])
    assert ports == [80, 554]


def test_build_metric_labels_and_label_map():
    assert build_metric_labels(False) == ["school"]
    assert build_metric_labels(True) == ["school", "nvr_ip"]
    assert school_metric_labels("Unidade A", "10.1.1.1", False) == {"school": "Unidade A"}
    assert school_metric_labels("Unidade A", "10.1.1.1", True) == {
        "school": "Unidade A",
        "nvr_ip": "10.1.1.1",
    }


def test_classify_exception_known_types():
    assert classify_exception(subprocess.TimeoutExpired(cmd="ping", timeout=1)) == "timeout"
    assert classify_exception(socket.timeout()) == "socket_timeout"
    assert classify_exception(JSONDecodeError("msg", "{}", 0)) == "json_decode"
    assert classify_exception(FileNotFoundError()) == "file_not_found"
    assert classify_exception(PermissionError()) == "permission_error"
    assert classify_exception(KeyError("k")) == "missing_key"
    assert classify_exception(ValueError("v")) == "invalid_value"
