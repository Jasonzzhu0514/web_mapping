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

from web_mapping.protocol import DEFAULT_SOURCES, VALID_SOURCES  # noqa: E402


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


if __name__ == "__main__":
    test_binary_cloud_payload_contract()
    test_default_sources_keep_hidden_layers_streaming()
    print("web mapping protocol ok")
