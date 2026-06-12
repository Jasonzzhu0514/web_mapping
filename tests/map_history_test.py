#!/usr/bin/env python3
"""Saved map history discovery checks."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import zipfile
import io
import os


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "web_mapping"))

from web_mapping.runtime.map_history import MapHistory  # noqa: E402


def test_map_history_lists_downloadable_map_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "sequence_20260612_100000"
        session.mkdir()
        (session / "map_optimized.pcd").write_text("optimized")
        (session / "map_raw.pcd").write_text("raw")
        (session / "debug.log").write_text("ignore")

        payload = MapHistory(str(root)).list_sessions()

        assert payload["available"]
        assert len(payload["sessions"]) == 1
        files = payload["sessions"][0]["files"]
        assert [file["name"] for file in files] == ["map_optimized.pcd", "map_raw.pcd"]
        assert all(file["download_url"].startswith("/api/maps/download?") for file in files)
        assert payload["sessions"][0]["archive_url"] == "/api/maps/download_session?id=sequence_20260612_100000"


def test_map_history_download_resolution_is_restricted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "session"
        session.mkdir()
        (session / "map_optimized.pcd").write_text("optimized")
        (session / "secret.txt").write_text("secret")

        history = MapHistory(str(root))

        assert history.resolve_download("session", "map_optimized.pcd") == session / "map_optimized.pcd"
        assert history.resolve_download("session", "secret.txt") is None
        assert history.resolve_download("../session", "map_optimized.pcd") is None


def test_map_history_session_archive_contains_only_allowed_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "session"
        session.mkdir()
        (session / "map_optimized.pcd").write_text("optimized")
        (session / "map_raw.pcd").write_text("raw")
        (session / "secret.txt").write_text("secret")

        archive = MapHistory(str(root)).make_session_archive("session")

        assert archive is not None
        filename, payload = archive
        assert filename == "session.zip"
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zip_file:
            assert sorted(zip_file.namelist()) == ["map_optimized.pcd", "map_raw.pcd"]
        assert MapHistory(str(root)).make_session_archive("../session") is None


def test_map_history_delete_session_is_restricted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "session"
        unrelated = root / "unrelated"
        session.mkdir()
        unrelated.mkdir()
        (session / "map_optimized.pcd").write_text("optimized")
        (session / "debug.log").write_text("remove with session")
        (unrelated / "notes.txt").write_text("keep")

        history = MapHistory(str(root))

        assert history.delete_session("../session") is False
        assert history.delete_session("") is False
        assert history.delete_session("unrelated") is False
        assert unrelated.is_dir()
        assert history.delete_session("session") is True
        assert not session.exists()


def test_map_history_project_relative_root() -> None:
    project_root = ROOT
    expected = project_root / "maps"
    old_cwd = Path.cwd()
    try:
        os.chdir(project_root)
        assert MapHistory("maps").root == expected
        os.chdir(project_root.parent)
        assert MapHistory("maps").root == expected
        os.chdir(Path.home())
        assert MapHistory("maps").root == expected
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    test_map_history_lists_downloadable_map_files()
    test_map_history_download_resolution_is_restricted()
    test_map_history_session_archive_contains_only_allowed_files()
    test_map_history_delete_session_is_restricted()
    test_map_history_project_relative_root()
    print("map history ok")
