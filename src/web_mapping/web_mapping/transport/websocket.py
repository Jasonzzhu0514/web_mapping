"""Minimal WebSocket framing used by the ROS bridge."""

from __future__ import annotations

import json
import socket
import struct
import threading
from typing import Any

from web_mapping.protocol import DEFAULT_SOURCES


class WebSocketClient:
    def __init__(self, sock: socket.socket, address: tuple[str, int], bridge: Any) -> None:
        self.sock = sock
        self.address = address
        self.bridge = bridge
        self.selected_source = next(iter(DEFAULT_SOURCES))
        self.selected_sources = set(DEFAULT_SOURCES)
        self.alive = True
        self._send_lock = threading.Lock()
        self.sock.settimeout(60.0)

    def send_json(self, payload: dict[str, Any]) -> bool:
        return self.send_frame(json.dumps(payload, separators=(",", ":")).encode("utf-8"), opcode=0x1)

    def send_binary(self, payload: bytes) -> bool:
        return self.send_frame(payload, opcode=0x2)

    def send_frame(self, payload: bytes, opcode: int) -> bool:
        if not self.alive:
            return False
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length < (1 << 16):
            header.extend(struct.pack("!BH", 126, length))
        else:
            header.extend(struct.pack("!BQ", 127, length))
        try:
            with self._send_lock:
                self.sock.sendall(header)
                if payload:
                    self.sock.sendall(payload)
            return True
        except OSError:
            self.close()
            return False

    def recv_frame(self) -> tuple[int, bytes] | None:
        try:
            head = self._recv_exact(2)
            if not head:
                return None
            b0, b1 = head
            opcode = b0 & 0x0F
            masked = (b1 & 0x80) != 0
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(value ^ mask[idx % 4] for idx, value in enumerate(payload))
            return opcode, payload
        except (OSError, TimeoutError):
            return None

    def _recv_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.sock.recv(size - len(chunks))
            if not chunk:
                raise TimeoutError("socket closed")
            chunks.extend(chunk)
        return bytes(chunks)

    def close(self) -> None:
        if not self.alive:
            return
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass
        self.bridge.remove_client(self)
