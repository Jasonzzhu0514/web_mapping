"""Saved map discovery and download helpers."""

from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import shutil
import time
from typing import Optional
from urllib.parse import quote
import zipfile


ALLOWED_MAP_FILENAMES = {
    "map_optimized.pcd",
    "map_raw.pcd",
    "poses_matrix.txt",
    "poses_kitti.txt",
    "poses_tum.txt",
}


@dataclass(frozen=True)
class MapFile:
    name: str
    size: int
    modified_at: float
    download_url: str


@dataclass(frozen=True)
class MapSession:
    id: str
    name: str
    path: str
    modified_at: float
    files: list[MapFile]


class MapHistory:
    def __init__(self, root: str, max_sessions: int = 20) -> None:
        self.root = self._normalize_root(root)
        self.max_sessions = max(1, int(max_sessions))

    def list_sessions(self) -> dict:
        if not self.root.exists():
            return {
                "root": str(self.root),
                "available": False,
                "sessions": [],
                "message": "暂无历史地图",
            }
        if not self.root.is_dir():
            return {
                "root": str(self.root),
                "available": False,
                "sessions": [],
                "message": "历史地图路径不是目录",
            }
        sessions = sorted(
            (session for session in self._iter_sessions()),
            key=lambda session: session.modified_at,
            reverse=True,
        )
        return {
            "root": str(self.root),
            "available": True,
            "sessions": [self._session_to_dict(session) for session in sessions[: self.max_sessions]],
            "message": "ok",
        }

    def resolve_download(self, session_id: str, filename: str) -> Optional[Path]:
        if filename not in ALLOWED_MAP_FILENAMES:
            return None
        session_path = self._resolve_session_path(session_id)
        if session_path is None:
            return None
        candidate = (session_path / filename).resolve()
        try:
            candidate.relative_to(session_path)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def make_session_archive(self, session_id: str) -> Optional[tuple[str, bytes]]:
        session_path = self._resolve_session_path(session_id)
        if session_path is None:
            return None
        files = self._session_files(session_path)
        if not files:
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                path = session_path / file.name
                if path.is_file():
                    archive.write(path, arcname=file.name)
        return f"{session_path.name}.zip", buffer.getvalue()

    def delete_session(self, session_id: str) -> bool:
        session_path = self._resolve_session_path(session_id)
        if session_path is None or not self._session_files(session_path):
            return False
        try:
            shutil.rmtree(session_path)
        except OSError:
            return False
        return True

    def _iter_sessions(self):
        root = self._resolved_root()
        if root is None:
            return
        for path in root.iterdir():
            if not path.is_dir():
                continue
            files = self._session_files(path)
            if not files:
                continue
            yield MapSession(
                id=path.name,
                name=path.name,
                path=str(path),
                modified_at=max((file.modified_at for file in files), default=path.stat().st_mtime),
                files=files,
            )

    def _session_files(self, session_path: Path) -> list[MapFile]:
        files = []
        for filename in sorted(ALLOWED_MAP_FILENAMES):
            path = session_path / filename
            if not path.is_file():
                continue
            stat = path.stat()
            files.append(
                MapFile(
                    name=filename,
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                    download_url=self._download_url(session_path.name, filename),
                )
            )
        return files

    def _resolve_session_path(self, session_id: str) -> Optional[Path]:
        if not session_id or Path(session_id).name != session_id:
            return None
        root = self._resolved_root()
        if root is None:
            return None
        session_path = (root / session_id).resolve()
        if session_path == root:
            return None
        try:
            session_path.relative_to(root)
        except ValueError:
            return None
        if not session_path.is_dir():
            return None
        return session_path

    def _resolved_root(self) -> Optional[Path]:
        try:
            return self.root.resolve()
        except OSError:
            return None

    @staticmethod
    def _normalize_root(root: str) -> Path:
        path = Path(root).expanduser()
        if path.is_absolute():
            return path
        project_root = MapHistory._project_root()
        if project_root is not None and path.parts:
            if path.parts[0] == project_root.name:
                return project_root.joinpath(*path.parts[1:])
            if path.parts[0] == "maps":
                return project_root / path
        cwd = Path.cwd()
        return cwd / path

    @staticmethod
    def _project_root() -> Optional[Path]:
        starts = [Path.cwd(), Path(__file__).resolve()]
        for start in starts:
            base = start if start.is_dir() else start.parent
            for candidate in (base, *base.parents):
                if (candidate / "web_mapping_bridge.yaml").is_file() and (candidate / "src" / "web_mapping" / "package.xml").is_file():
                    return candidate
        return None

    @staticmethod
    def _download_url(session_id: str, filename: str) -> str:
        return f"/api/maps/download?id={quote(session_id)}&file={quote(filename)}"

    @staticmethod
    def _archive_url(session_id: str) -> str:
        return f"/api/maps/download_session?id={quote(session_id)}"

    @staticmethod
    def _delete_url(session_id: str) -> str:
        return f"/api/maps/session?id={quote(session_id)}"

    @staticmethod
    def _session_to_dict(session: MapSession) -> dict:
        return {
            "id": session.id,
            "name": session.name,
            "path": session.path,
            "modified_at": session.modified_at,
            "modified_label": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session.modified_at)),
            "archive_url": MapHistory._archive_url(session.id),
            "delete_url": MapHistory._delete_url(session.id),
            "files": [
                {
                    "name": file.name,
                    "size": file.size,
                    "modified_at": file.modified_at,
                    "download_url": file.download_url,
                }
                for file in session.files
            ],
        }
