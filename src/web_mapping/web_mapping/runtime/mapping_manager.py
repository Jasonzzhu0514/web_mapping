"""Mapping control state machine for the browser bridge.

The default backend is intentionally a no-op shell. It keeps the WebSocket
contract stable while the real SLAM launch/service integration is added by the
host project.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Optional

from web_mapping.protocol import VALID_MAPPING_COMMANDS, VALID_MAPPING_STATES


@dataclass(frozen=True)
class MappingCommandRequest:
    command: str
    session_name: str = ""
    save_directory: str = ""


@dataclass(frozen=True)
class MappingBackendResult:
    accepted: bool
    message: str
    details: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class MappingCommandResult:
    command: str
    accepted: bool
    state: str
    message: str
    details: Optional[dict[str, Any]] = None


class MappingBackend:
    """Backend control hook to be replaced by the owning SLAM workspace."""

    name = "stub"
    available = False

    def start(self, request: MappingCommandRequest) -> MappingBackendResult:
        return MappingBackendResult(True, "已进入建图模式，实际启动功能待接入。")

    def stop(self, request: MappingCommandRequest) -> MappingBackendResult:
        return MappingBackendResult(True, "已停止建图，实际停止功能待接入。")

    def save(self, request: MappingCommandRequest) -> MappingBackendResult:
        return MappingBackendResult(True, "已请求保存地图，实际保存功能待接入。")


class MappingManager:
    """Small state machine used by the Web UI mapping controls."""

    def __init__(self, backend: Optional[MappingBackend] = None) -> None:
        self._backend = backend or MappingBackend()
        self._lock = threading.Lock()
        self._state = "idle"
        self._message = "等待开始"
        self._session_name = ""
        self._save_directory = ""
        self._last_command = ""
        self._last_result = ""
        self._seq = 0
        self._updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "message": self._message,
                "session_name": self._session_name,
                "save_directory": self._save_directory,
                "last_command": self._last_command,
                "last_result": self._last_result,
                "command_seq": self._seq,
                "updated_at": self._updated_at,
                "backend": {
                    "name": self._backend.name,
                    "available": self._backend.available,
                },
                "allowed_commands": sorted(self._allowed_commands_unlocked()),
                "states": sorted(VALID_MAPPING_STATES),
            }

    def handle_command(self, command: str, payload: Optional[dict[str, Any]] = None) -> MappingCommandResult:
        normalized = command.strip()
        if normalized not in VALID_MAPPING_COMMANDS:
            return self._reject(normalized, "未知建图指令")

        request = MappingCommandRequest(
            command=normalized,
            session_name=str((payload or {}).get("session_name", "")).strip(),
            save_directory=str((payload or {}).get("save_directory", "")).strip(),
        )
        if normalized == "start":
            return self._start(request)
        if normalized == "stop":
            return self._stop(request)
        if normalized == "save":
            return self._save(request)
        return self._reset_error(request)

    def _start(self, request: MappingCommandRequest) -> MappingCommandResult:
        with self._lock:
            if self._state not in {"idle", "stopped", "error"}:
                return self._reject_unlocked(request.command, f"当前不能开始建图")
            self._session_name = request.session_name
            self._save_directory = request.save_directory
            self._transition_unlocked("starting", "正在请求启动建图")
        result = self._backend.start(request)
        with self._lock:
            next_state = "mapping" if result.accepted else "error"
            self._transition_unlocked(next_state, result.message, request.command, result)
            return self._result_unlocked(request.command, result.accepted, result.message, result.details)

    def _stop(self, request: MappingCommandRequest) -> MappingCommandResult:
        with self._lock:
            if self._state not in {"starting", "mapping", "saving"}:
                return self._reject_unlocked(request.command, f"当前不能停止建图")
            self._transition_unlocked("stopping", "正在请求停止建图")
        result = self._backend.stop(request)
        with self._lock:
            next_state = "stopped" if result.accepted else "error"
            self._transition_unlocked(next_state, result.message, request.command, result)
            return self._result_unlocked(request.command, result.accepted, result.message, result.details)

    def _save(self, request: MappingCommandRequest) -> MappingCommandResult:
        with self._lock:
            if self._state != "stopped":
                return self._reject_unlocked(request.command, f"当前不能保存地图")
            if request.save_directory:
                self._save_directory = request.save_directory
            self._transition_unlocked("saving", "正在请求保存地图")
        result = self._backend.save(request)
        with self._lock:
            next_state = "stopped" if result.accepted else "error"
            self._transition_unlocked(next_state, result.message, request.command, result)
            return self._result_unlocked(request.command, result.accepted, result.message, result.details)

    def _reset_error(self, request: MappingCommandRequest) -> MappingCommandResult:
        with self._lock:
            if self._state != "error":
                return self._reject_unlocked(request.command, f"当前没有异常需要重置")
            self._transition_unlocked("idle", "异常已清除", request.command)
            return self._result_unlocked(request.command, True, self._message)

    def _reject(self, command: str, message: str) -> MappingCommandResult:
        with self._lock:
            return self._reject_unlocked(command, message)

    def _reject_unlocked(self, command: str, message: str) -> MappingCommandResult:
        self._last_command = command
        self._last_result = message
        self._message = message
        self._seq += 1
        self._updated_at = time.time()
        return self._result_unlocked(command, False, message)

    def _transition_unlocked(
        self,
        state: str,
        message: str,
        command: Optional[str] = None,
        result: Optional[MappingBackendResult] = None,
    ) -> None:
        if state not in VALID_MAPPING_STATES:
            raise ValueError(f"invalid mapping state: {state}")
        self._state = state
        self._message = message
        if command:
            self._last_command = command
            self._last_result = result.message if result else message
        self._seq += 1
        self._updated_at = time.time()

    def _result_unlocked(
        self,
        command: str,
        accepted: bool,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> MappingCommandResult:
        return MappingCommandResult(
            command=command,
            accepted=accepted,
            state=self._state,
            message=message,
            details=details,
        )

    def _allowed_commands_unlocked(self) -> set[str]:
        if self._state in {"idle", "stopped", "error"}:
            commands = {"start"}
        elif self._state in {"starting", "mapping", "saving"}:
            commands = {"stop"}
        else:
            commands = set()
        if self._state == "stopped":
            commands.add("save")
        if self._state == "error":
            commands.add("reset_error")
        return commands
