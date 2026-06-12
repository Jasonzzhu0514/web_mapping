"""PCD preview sampling helpers for saved map rendering."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import json
import math
import struct
from pathlib import Path
from typing import Callable, Optional


MAX_HEADER_BYTES = 1024 * 1024


class PcdPreviewError(ValueError):
    """Raised when a saved PCD file cannot be parsed for preview."""


@dataclass(frozen=True)
class PcdHeader:
    point_count: int
    data: str
    fields: list[str]
    sizes: list[int]
    types: list[str]
    counts: list[int]
    header_length: int


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


def build_pcd_preview_payload(
    path: Path,
    *,
    session_id: str,
    filename: str,
    source: str = "map",
    max_points: int = 1_000_000,
) -> bytes:
    target_points = max(1, min(int(max_points), 2_000_000))
    raw = path.read_bytes()
    sampled = sample_pcd_xyzi(raw, target_points)
    header = {
        "source": source,
        "seq": int(path.stat().st_mtime * 1000),
        "topic": f"history/{session_id}/{filename}",
        "session_id": session_id,
        "filename": filename,
        "source_point_count": sampled["source_point_count"],
        "point_count": sampled["point_count"],
        "sample_every": sampled["sample_every"],
        "bounds": sampled["bounds"],
        "has_intensity": sampled["has_intensity"],
        "intensity_range": sampled["intensity_range"],
    }
    return make_binary_cloud_payload(header, sampled["values"])


def sample_pcd_xyzi(raw: bytes, max_points: int) -> dict:
    header = _read_pcd_header(raw)
    plan = _sampling_plan(header.point_count, max_points)
    if plan["target_points"] == 0:
        return _empty_sample(plan["sample_every"], header.point_count)

    field_names = [field.lower() for field in header.fields]
    try:
        idx_x = field_names.index("x")
        idx_y = field_names.index("y")
        idx_z = field_names.index("z")
    except ValueError as exc:
        raise PcdPreviewError("PCD missing x/y/z fields") from exc
    idx_i = _first_field_index(field_names, ("intensity", "reflectivity", "i"))

    selector = _exact_uniform_selector(plan["total_points"], plan["target_points"])
    values = array("f")
    stats = _Stats()

    if header.data == "ascii":
        _sample_ascii(raw, header, selector, idx_x, idx_y, idx_z, idx_i, values, stats)
    elif header.data in {"binary", "binary_compressed"}:
        _sample_binary(raw, header, selector, idx_x, idx_y, idx_z, idx_i, values, stats)
    else:
        raise PcdPreviewError(f"Unsupported PCD DATA format: {header.data}")

    return {
        "values": values,
        "source_point_count": header.point_count,
        "point_count": stats.accepted,
        "sample_every": plan["sample_every"],
        "bounds": stats.bounds(),
        "has_intensity": idx_i is not None,
        "intensity_range": stats.intensity_range(idx_i is not None),
    }


def _read_pcd_header(raw: bytes) -> PcdHeader:
    offset = 0
    lines: list[str] = []
    data = ""

    while offset < len(raw):
        newline = raw.find(b"\n", offset)
        end = len(raw) if newline < 0 else newline + 1
        line_bytes = raw[offset:end]
        offset = end
        line = line_bytes.decode("ascii", errors="ignore").strip()
        lines.append(line)

        parts = line.split()
        if parts and parts[0].upper() == "DATA":
            if len(parts) < 2:
                raise PcdPreviewError("Invalid PCD DATA line")
            data = parts[1].lower()
            break
        if offset > MAX_HEADER_BYTES:
            raise PcdPreviewError("PCD header is too large")

    if not data:
        raise PcdPreviewError("Invalid PCD header: DATA not found")

    fields = _header_tokens(lines, "FIELDS")
    sizes = _header_ints(lines, "SIZE")
    types = [item.upper() for item in _header_tokens(lines, "TYPE")]
    counts = _header_ints(lines, "COUNT") or [1] * len(fields)
    if not fields or not (len(fields) == len(sizes) == len(types) == len(counts)):
        raise PcdPreviewError("Invalid PCD field descriptors")

    points = _header_int(lines, "POINTS", 0)
    width = _header_int(lines, "WIDTH", 0)
    height = _header_int(lines, "HEIGHT", 1)
    point_count = points if points > 0 else width * height
    return PcdHeader(
        point_count=max(0, int(point_count)),
        data=data,
        fields=fields,
        sizes=sizes,
        types=types,
        counts=counts,
        header_length=offset,
    )


def _header_tokens(lines: list[str], key: str) -> list[str]:
    value = _header_value(lines, key)
    return value.split() if value else []


def _header_ints(lines: list[str], key: str) -> list[int]:
    values = []
    for token in _header_tokens(lines, key):
        try:
            values.append(int(token))
        except ValueError as exc:
            raise PcdPreviewError(f"Invalid PCD {key} value: {token}") from exc
    return values


def _header_int(lines: list[str], key: str, default: int) -> int:
    value = _header_value(lines, key)
    if not value:
        return default
    try:
        return int(float(value.split()[0]))
    except ValueError as exc:
        raise PcdPreviewError(f"Invalid PCD {key} value: {value}") from exc


def _header_value(lines: list[str], key: str) -> str:
    target = key.upper()
    for line in lines:
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].upper() == target:
            return parts[1].strip()
    return ""


def _sampling_plan(total_points: int, max_points: int) -> dict[str, int]:
    total = max(0, int(total_points))
    target = max(1, int(max_points))
    effective = min(total, target)
    sample_every = 1 if effective <= 0 else max(1, math.ceil(total / effective))
    return {"total_points": total, "target_points": effective, "sample_every": sample_every}


def _exact_uniform_selector(total_points: int, target_points: int) -> Callable[[int], bool]:
    if total_points <= 0 or target_points <= 0:
        return lambda _index: False
    if target_points >= total_points:
        return lambda index: 0 <= index < total_points
    previous_threshold = 0

    def should_accept(index: int) -> bool:
        nonlocal previous_threshold
        if index < 0 or index >= total_points:
            return False
        next_threshold = ((index + 1) * target_points) // total_points
        accepted = next_threshold > previous_threshold
        previous_threshold = next_threshold
        return accepted

    return should_accept


def _sample_ascii(
    raw: bytes,
    header: PcdHeader,
    selector: Callable[[int], bool],
    idx_x: int,
    idx_y: int,
    idx_z: int,
    idx_i: Optional[int],
    values: array,
    stats: "_Stats",
) -> None:
    token_offsets = []
    token_index = 0
    for count in header.counts:
        token_offsets.append(token_index)
        token_index += max(1, count)
    min_tokens = token_index

    text = raw[header.header_length :].decode("utf-8", errors="replace")
    processed = 0
    for line in text.splitlines():
        if processed >= header.point_count:
            break
        stripped = line.strip()
        if not stripped:
            continue
        current = processed
        processed += 1
        if not selector(current):
            continue
        tokens = stripped.split()
        if len(tokens) < min_tokens:
            continue
        x = _ascii_value(tokens, token_offsets[idx_x])
        y = _ascii_value(tokens, token_offsets[idx_y])
        z = _ascii_value(tokens, token_offsets[idx_z])
        if x is None or y is None or z is None:
            continue
        intensity = _ascii_value(tokens, token_offsets[idx_i]) if idx_i is not None else 0.0
        _append_sample(values, stats, x, y, z, intensity)


def _ascii_value(tokens: list[str], index: int) -> Optional[float]:
    try:
        value = float(tokens[index])
    except (IndexError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _sample_binary(
    raw: bytes,
    header: PcdHeader,
    selector: Callable[[int], bool],
    idx_x: int,
    idx_y: int,
    idx_z: int,
    idx_i: Optional[int],
    values: array,
    stats: "_Stats",
) -> None:
    offsets = []
    stride = 0
    for size, count in zip(header.sizes, header.counts):
        offsets.append(stride)
        stride += size * max(1, count)

    field_major = False
    if header.data == "binary":
        payload = memoryview(raw)[header.header_length :]
    else:
        if len(raw) < header.header_length + 8:
            raise PcdPreviewError("Invalid binary_compressed PCD payload")
        compressed_size, uncompressed_size = struct.unpack_from("<II", raw, header.header_length)
        start = header.header_length + 8
        end = start + compressed_size
        if end > len(raw):
            raise PcdPreviewError("Truncated binary_compressed PCD payload")
        payload = memoryview(_lzf_decompress(raw[start:end], uncompressed_size))
        field_major = True

    def field_offset(field_index: int, point_index: int) -> int:
        if not field_major:
            return point_index * stride + offsets[field_index]
        base = 0
        for i in range(field_index):
            base += header.sizes[i] * max(1, header.counts[i]) * header.point_count
        return base + point_index * header.sizes[field_index] * max(1, header.counts[field_index])

    for point_index in range(header.point_count):
        if not selector(point_index):
            continue
        x = _binary_value(payload, field_offset(idx_x, point_index), header.types[idx_x], header.sizes[idx_x])
        y = _binary_value(payload, field_offset(idx_y, point_index), header.types[idx_y], header.sizes[idx_y])
        z = _binary_value(payload, field_offset(idx_z, point_index), header.types[idx_z], header.sizes[idx_z])
        if x is None or y is None or z is None:
            continue
        intensity = (
            _binary_value(payload, field_offset(idx_i, point_index), header.types[idx_i], header.sizes[idx_i])
            if idx_i is not None
            else 0.0
        )
        _append_sample(values, stats, x, y, z, intensity)


def _binary_value(payload: memoryview, offset: int, field_type: str, size: int) -> Optional[float]:
    if offset < 0 or offset + size > len(payload):
        return None
    try:
        if field_type == "F":
            if size == 4:
                return float(struct.unpack_from("<f", payload, offset)[0])
            if size == 8:
                return float(struct.unpack_from("<d", payload, offset)[0])
        if field_type == "I":
            fmt = {1: "b", 2: "<h", 4: "<i"}.get(size)
            return float(struct.unpack_from(fmt, payload, offset)[0]) if fmt else None
        if field_type == "U":
            fmt = {1: "B", 2: "<H", 4: "<I"}.get(size)
            return float(struct.unpack_from(fmt, payload, offset)[0]) if fmt else None
    except struct.error:
        return None
    return None


def _lzf_decompress(data: bytes | memoryview, output_length: int) -> bytes:
    source = memoryview(data)
    output = bytearray(output_length)
    in_pos = 0
    out_pos = 0
    while in_pos < len(source):
        ctrl = source[in_pos]
        in_pos += 1
        if ctrl < 32:
            length = ctrl + 1
            if in_pos + length > len(source) or out_pos + length > output_length:
                raise PcdPreviewError("Invalid LZF literal run")
            output[out_pos : out_pos + length] = source[in_pos : in_pos + length]
            in_pos += length
            out_pos += length
            continue
        length = ctrl >> 5
        ref = out_pos - ((ctrl & 0x1F) << 8) - 1
        if length == 7:
            if in_pos >= len(source):
                raise PcdPreviewError("Invalid LZF length")
            length += source[in_pos]
            in_pos += 1
        if in_pos >= len(source):
            raise PcdPreviewError("Invalid LZF reference")
        ref -= source[in_pos]
        in_pos += 1
        length += 2
        if ref < 0 or out_pos + length > output_length:
            raise PcdPreviewError("Invalid LZF back-reference")
        for _ in range(length):
            output[out_pos] = output[ref]
            out_pos += 1
            ref += 1
    return bytes(output)


def _append_sample(values: array, stats: "_Stats", x: float, y: float, z: float, intensity: Optional[float]) -> None:
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        return
    if intensity is None or not math.isfinite(intensity):
        intensity = 0.0
    values.extend((float(x), float(y), float(z), float(intensity)))
    stats.observe(float(x), float(y), float(z), float(intensity))


def _first_field_index(fields: list[str], names: tuple[str, ...]) -> Optional[int]:
    for name in names:
        if name in fields:
            return fields.index(name)
    return None


def _empty_sample(sample_every: int, source_point_count: int) -> dict:
    return {
        "values": array("f"),
        "source_point_count": source_point_count,
        "point_count": 0,
        "sample_every": sample_every,
        "bounds": None,
        "has_intensity": False,
        "intensity_range": [0.0, 1.0],
    }


class _Stats:
    def __init__(self) -> None:
        self.accepted = 0
        self.min_x = self.min_y = self.min_z = math.inf
        self.max_x = self.max_y = self.max_z = -math.inf
        self.min_i = math.inf
        self.max_i = -math.inf

    def observe(self, x: float, y: float, z: float, intensity: float) -> None:
        self.accepted += 1
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.min_z = min(self.min_z, z)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)
        self.max_z = max(self.max_z, z)
        self.min_i = min(self.min_i, intensity)
        self.max_i = max(self.max_i, intensity)

    def bounds(self) -> Optional[dict]:
        if self.accepted <= 0:
            return None
        return {
            "min": [self.min_x, self.min_y, self.min_z],
            "max": [self.max_x, self.max_y, self.max_z],
        }

    def intensity_range(self, has_intensity: bool) -> list[float]:
        if not has_intensity or self.accepted <= 0:
            return [0.0, 1.0]
        high = self.max_i if self.max_i > self.min_i else self.min_i + 1.0
        return [float(self.min_i), float(high)]
