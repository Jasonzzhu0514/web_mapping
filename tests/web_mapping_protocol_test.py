#!/usr/bin/env python3
"""Protocol checks for the web mapping demo.

This test is intentionally independent from ROS 2 imports, so it can run in a
plain Python environment and still verify the browser/bridge binary contract.
"""

from __future__ import annotations

import json
import struct
from array import array
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "web_mapping"))

from web_mapping.protocol import (  # noqa: E402
    DEFAULT_MAP_HISTORY_ROOT,
    DEFAULT_SOURCES,
    VALID_MAPPING_COMMANDS,
    VALID_MAPPING_STATES,
    VALID_SOURCES,
    WEB_MAPPING_TOPICS,
)
from web_mapping.runtime.mapping_manager import MappingManager  # noqa: E402


def make_binary_cloud_payload(header: dict, values: array) -> bytes:
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    padding = (4 - ((8 + len(header_bytes)) % 4)) % 4
    data_offset = 8 + len(header_bytes) + padding
    return (
        struct.pack("<II", len(header_bytes), data_offset)
        + header_bytes
        + (b"\x00" * padding)
        + values.tobytes()
    )


def decode_like_frontend(payload: bytes) -> tuple[dict, array]:
    header_length = struct.unpack_from("<I", payload, 0)[0]
    data_offset = struct.unpack_from("<I", payload, 4)[0]
    header = json.loads(payload[8 : 8 + header_length].decode("utf-8"))
    assert data_offset % 4 == 0
    values = array("f")
    values.frombytes(payload[data_offset:])
    return header, values


def test_binary_cloud_payload_contract() -> None:
    header = {
        "type": "cloud",
        "source": "optimized",
        "point_count": 2,
        "layout": "float32_xyzi",
        "stride": 4,
        "has_intensity": True,
    }
    values = array("f", [1.0, 2.0, 3.0, 0.4, 4.0, 5.0, 6.0, 0.8])
    payload = make_binary_cloud_payload(header, values)
    decoded_header, decoded_values = decode_like_frontend(payload)

    assert decoded_header == header
    assert list(decoded_values) == list(values)


def test_default_sources_keep_hidden_layers_streaming() -> None:
    assert set(DEFAULT_SOURCES) == VALID_SOURCES


def test_mapping_control_state_machine_shell() -> None:
    manager = MappingManager()

    initial = manager.snapshot()
    assert initial["state"] == "idle"
    assert "start" in initial["allowed_commands"]
    assert set(initial["states"]) == VALID_MAPPING_STATES

    start_result = manager.handle_command("start", {"session_name": "demo"})
    assert start_result.accepted
    assert start_result.state == "mapping"
    assert "save" not in manager.snapshot()["allowed_commands"]

    save_while_mapping_result = manager.handle_command("save", {"save_directory": "/tmp/maps"})
    assert not save_while_mapping_result.accepted
    assert save_while_mapping_result.state == "mapping"

    stop_result = manager.handle_command("stop", {})
    assert stop_result.accepted
    assert stop_result.state == "stopped"
    assert "save" in manager.snapshot()["allowed_commands"]

    save_after_stop_result = manager.handle_command("save", {})
    assert save_after_stop_result.accepted
    assert save_after_stop_result.state == "stopped"


def test_mapping_protocol_commands_are_explicit() -> None:
    assert VALID_MAPPING_COMMANDS == {"start", "stop", "save", "reset_error"}


def test_web_mapping_broker_contract_topics_are_stable() -> None:
    assert WEB_MAPPING_TOPICS == {
        "raw_cloud": "/web_mapping/raw_cloud",
        "current_frame": "/web_mapping/current_frame",
        "global_map": "/web_mapping/global_map",
        "pose": "/web_mapping/pose",
        "raw_path": "/web_mapping/raw_path",
        "optimized_path": "/web_mapping/optimized_path",
        "imu": "/web_mapping/imu",
        "lidar_status": "/web_mapping/lidar_status",
        "mapping_command": "/web_mapping/command",
        "mapping_status": "/web_mapping/status",
    }
    assert DEFAULT_MAP_HISTORY_ROOT == "web_mapping/maps"


if __name__ == "__main__":
    test_binary_cloud_payload_contract()
    test_default_sources_keep_hidden_layers_streaming()
    test_mapping_control_state_machine_shell()
    test_mapping_protocol_commands_are_explicit()
    test_web_mapping_broker_contract_topics_are_stable()
    print("web mapping protocol ok")
