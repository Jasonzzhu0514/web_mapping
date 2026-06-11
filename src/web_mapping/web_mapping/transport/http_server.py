"""Static file server and WebSocket upgrade handler."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from ament_index_python.packages import get_package_share_directory

from web_mapping.protocol import VALID_SOURCES
from web_mapping.transport.websocket import WebSocketClient


WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class MappingDemoHttpHandler(BaseHTTPRequestHandler):
    server_version = "FastLioSamWebDemo/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/ws":
            self._handle_websocket()
            return
        self._serve_static(parsed.path)

    def log_message(self, fmt: str, *args: Any) -> None:
        node = getattr(self.server, "bridge_node", None)
        if node is not None and node.log_http_requests:
            node.get_logger().info(f"{self.address_string()} - {fmt % args}")

    def _serve_static(self, request_path: str) -> None:
        static_dir: Path = self.server.static_dir  # type: ignore[attr-defined]
        if request_path in {"", "/"}:
            relative = Path("index.html")
        else:
            request_relative = PurePosixPath(unquote(request_path.lstrip("/")))
            if request_relative.is_absolute() or any(part in {"", ".", ".."} for part in request_relative.parts):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            relative = Path(*request_relative.parts)
        candidate = static_dir / relative
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        payload = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _handle_websocket(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing Sec-WebSocket-Key")
            return
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")
        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        bridge = self.server.bridge_node  # type: ignore[attr-defined]
        client = WebSocketClient(self.connection, self.client_address, bridge)
        bridge.add_client(client)
        client.send_json(
            {
                "type": "hello",
                "sources": sorted(VALID_SOURCES),
                "selected_source": client.selected_source,
                "selected_sources": sorted(client.selected_sources),
                "server_time": time.time(),
            }
        )
        client.send_json(bridge.make_status_payload(client.selected_source))

        while client.alive:
            frame = client.recv_frame()
            if frame is None:
                break
            opcode, payload = frame
            if opcode == 0x8:
                break
            if opcode == 0x9:
                client.send_frame(payload, opcode=0xA)
                continue
            if opcode != 0x1:
                continue
            try:
                message = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            bridge.handle_client_message(client, message)
        client.close()


def create_http_server(host: str, port: int, bridge: Any) -> ThreadingHTTPServer:
    httpd = ReusableThreadingHTTPServer((host, port), MappingDemoHttpHandler)
    httpd.bridge_node = bridge  # type: ignore[attr-defined]
    httpd.static_dir = resolve_static_dir()  # type: ignore[attr-defined]
    return httpd


def resolve_static_dir() -> Path:
    source_candidate = Path(__file__).resolve().parents[1] / "web"
    if source_candidate.exists() and (source_candidate / "vendor" / "three.core.js").exists():
        return source_candidate
    try:
        share_dir = Path(get_package_share_directory("web_mapping"))
        candidate = share_dir / "web_mapping" / "web"
        if (candidate / "index.html").exists():
            return candidate
    except Exception:
        pass
    if source_candidate.exists():
        return source_candidate
    return Path.cwd()
