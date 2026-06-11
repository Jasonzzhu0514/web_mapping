"""PointCloud2 to browser binary payload conversion."""

from __future__ import annotations

import json
import math
import struct
from array import array
from typing import Any, Callable

from sensor_msgs.msg import PointCloud2, PointField


def stamp_to_float(stamp: Any) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def make_binary_cloud_payload(header: dict[str, Any], values: array) -> bytes:
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    padding = (4 - ((8 + len(header_bytes)) % 4)) % 4
    data_offset = 8 + len(header_bytes) + padding
    return (
        struct.pack("<II", len(header_bytes), data_offset)
        + header_bytes
        + (b"\x00" * padding)
        + values.tobytes()
    )


def extract_cloud_xyzi(msg: PointCloud2, max_points: int) -> dict[str, Any]:
    fields = {field.name: field for field in msg.fields}
    missing = [name for name in ("x", "y", "z") if name not in fields]
    if missing:
        raise ValueError(f"PointCloud2 missing fields: {', '.join(missing)}")

    data = memoryview(msg.data)
    point_total = int(msg.width * msg.height)
    sample_every = 1 if max_points <= 0 else max(1, math.ceil(point_total / max_points))
    endian = ">" if msg.is_bigendian else "<"
    read_x = _field_reader(fields["x"], endian, data)
    read_y = _field_reader(fields["y"], endian, data)
    read_z = _field_reader(fields["z"], endian, data)
    intensity_field = _first_existing_field(fields, ("intensity", "reflectivity", "i"))
    read_i = _field_reader(intensity_field, endian, data) if intensity_field else None

    values = array("f")
    min_x = min_y = min_z = math.inf
    max_x = max_y = max_z = -math.inf
    min_i = math.inf
    max_i = -math.inf
    accepted = 0
    width = max(1, int(msg.width))

    for point_index in range(0, point_total, sample_every):
        row = point_index // width
        col = point_index % width
        base = int(row * msg.row_step + col * msg.point_step)
        x = read_x(base)
        y = read_y(base)
        z = read_z(base)
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue
        intensity = read_i(base) if read_i else 0.0
        if not math.isfinite(intensity):
            intensity = 0.0
        values.extend((float(x), float(y), float(z), float(intensity)))
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        min_z = min(min_z, z)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        max_z = max(max_z, z)
        min_i = min(min_i, intensity)
        max_i = max(max_i, intensity)
        accepted += 1

    bounds = None
    if accepted > 0:
        bounds = {
            "min": [min_x, min_y, min_z],
            "max": [max_x, max_y, max_z],
        }
    if accepted == 0 or not read_i:
        intensity_range = [0.0, 1.0]
    else:
        intensity_range = [float(min_i), float(max_i if max_i > min_i else min_i + 1.0)]
    return {
        "values": values,
        "point_count": accepted,
        "sample_every": sample_every,
        "bounds": bounds,
        "has_intensity": read_i is not None,
        "intensity_range": intensity_range,
    }


def extract_livox_custom_xyzi(msg: Any, max_points: int) -> dict[str, Any]:
    points = getattr(msg, "points", [])
    point_total = int(getattr(msg, "point_num", len(points)) or len(points))
    point_total = min(point_total, len(points))
    sample_every = 1 if max_points <= 0 else max(1, math.ceil(point_total / max_points))

    values = array("f")
    min_x = min_y = min_z = math.inf
    max_x = max_y = max_z = -math.inf
    min_i = math.inf
    max_i = -math.inf
    accepted = 0

    for point_index in range(0, point_total, sample_every):
        point = points[point_index]
        x = float(point.x)
        y = float(point.y)
        z = float(point.z)
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue
        intensity = float(getattr(point, "reflectivity", 0))
        if not math.isfinite(intensity):
            intensity = 0.0
        values.extend((x, y, z, intensity))
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        min_z = min(min_z, z)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        max_z = max(max_z, z)
        min_i = min(min_i, intensity)
        max_i = max(max_i, intensity)
        accepted += 1

    bounds = None
    if accepted > 0:
        bounds = {
            "min": [min_x, min_y, min_z],
            "max": [max_x, max_y, max_z],
        }
    if accepted == 0:
        intensity_range = [0.0, 255.0]
    else:
        intensity_range = [float(min_i), float(max_i if max_i > min_i else min_i + 1.0)]
    return {
        "values": values,
        "point_count": accepted,
        "sample_every": sample_every,
        "bounds": bounds,
        "has_intensity": True,
        "intensity_range": intensity_range,
    }


def _first_existing_field(fields: dict[str, PointField], names: tuple[str, ...]) -> PointField | None:
    for name in names:
        if name in fields:
            return fields[name]
    return None


def _field_reader(field: PointField, endian: str, data: memoryview) -> Callable[[int], float]:
    formats = {
        PointField.INT8: "b",
        PointField.UINT8: "B",
        PointField.INT16: "h",
        PointField.UINT16: "H",
        PointField.INT32: "i",
        PointField.UINT32: "I",
        PointField.FLOAT32: "f",
        PointField.FLOAT64: "d",
    }
    fmt = formats.get(field.datatype)
    if fmt is None:
        raise ValueError(f"Unsupported PointField datatype for {field.name}: {field.datatype}")
    unpacker = struct.Struct(endian + fmt)
    offset = int(field.offset)

    def read(base: int) -> float:
        return float(unpacker.unpack_from(data, base + offset)[0])

    return read
