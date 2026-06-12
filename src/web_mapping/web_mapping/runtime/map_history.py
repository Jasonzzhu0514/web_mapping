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

from web_mapping.runtime.pcd_preview import build_pcd_preview_payload


ALLOWED_MAP_FILENAMES = {
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
    preview_url: str


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
        if not self._is_allowed_filename(filename):
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

    def resolve_preview(self, session_id: str, filename: str) -> Optional[Path]:
        if not filename.endswith(".pcd"):
            return None
        return self.resolve_download(session_id, filename)

    def make_preview_payload(self, session_id: str, filename: str, max_points: int = 1_000_000) -> Optional[bytes]:
        path = self.resolve_preview(session_id, filename)
        if path is None:
            return None
        return build_pcd_preview_payload(
            path,
            session_id=session_id,
            filename=filename,
            max_points=max_points,
        )

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
        for filename in self._session_filenames(session_path):
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
                    preview_url=self._preview_url(session_path.name, filename) if filename.endswith(".pcd") else "",
                )
            )
        return files

    def _session_filenames(self, session_path: Path) -> list[str]:
        filenames = set(ALLOWED_MAP_FILENAMES)
        for path in session_path.glob("*_map.pcd"):
            if path.is_file() and self._is_allowed_filename(path.name):
                filenames.add(path.name)
        return sorted(filenames)

    @staticmethod
    def _is_allowed_filename(filename: str) -> bool:
        path = Path(filename)
        if path.name != filename:
            return False
        return filename in ALLOWED_MAP_FILENAMES or filename.endswith("_map.pcd")

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
    def _preview_url(session_id: str, filename: str) -> str:
        return f"/api/maps/preview?id={quote(session_id)}&file={quote(filename)}"

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
                    "preview_url": file.preview_url,
                }
                for file in session.files
            ],
        }
