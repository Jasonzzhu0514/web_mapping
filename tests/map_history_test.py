#!/usr/bin/env python3
"""Saved map history discovery checks."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import zipfile
import io
import os
import json
import struct


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
        (session / "frontend_accumulated.pcd").write_text("legacy")
        (session / "result.pcd").write_text("result")
        (session / "sequence_20260612_100000_map.pcd").write_text("compat")
        (session / "poses_kitti.txt").write_text("kitti")
        (session / "poses_matrix.txt").write_text("matrix")
        (session / "poses_tum.txt").write_text("tum")
        (session / "debug.log").write_text("ignore")

        payload = MapHistory(str(root)).list_sessions()

        assert payload["available"]
        assert len(payload["sessions"]) == 1
        files = payload["sessions"][0]["files"]
        assert [file["name"] for file in files] == [
            "poses_kitti.txt",
            "poses_matrix.txt",
            "poses_tum.txt",
            "sequence_20260612_100000_map.pcd",
        ]
        assert all(file["download_url"].startswith("/api/maps/download?") for file in files)
        assert payload["sessions"][0]["archive_url"] == "/api/maps/download_session?id=sequence_20260612_100000"


def test_map_history_download_resolution_is_restricted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "session"
        session.mkdir()
        (session / "map_optimized.pcd").write_text("optimized")
        (session / "frontend_accumulated.pcd").write_text("legacy")
        (session / "session_map.pcd").write_text("compat")
        (session / "secret.txt").write_text("secret")

        history = MapHistory(str(root))

        assert history.resolve_download("session", "map_optimized.pcd") is None
        assert history.resolve_download("session", "frontend_accumulated.pcd") is None
        assert history.resolve_download("session", "session_map.pcd") == session / "session_map.pcd"
        assert history.resolve_download("session", "secret.txt") is None
        assert history.resolve_download("../session", "session_map.pcd") is None
        assert history.resolve_download("session", "../session_map.pcd") is None


def test_map_history_preview_samples_pcd_payload() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "session"
        session.mkdir()
        (session / "session_map.pcd").write_text(
            "\n".join(
                [
                    "# .PCD v0.7",
                    "VERSION 0.7",
                    "FIELDS x y z intensity",
                    "SIZE 4 4 4 4",
                    "TYPE F F F F",
                    "COUNT 1 1 1 1",
                    "WIDTH 3",
                    "HEIGHT 1",
                    "POINTS 3",
                    "DATA ascii",
                    "0 0 0 1",
                    "1 2 3 5",
                    "4 5 6 9",
                    "",
                ]
            )
        )

        history = MapHistory(str(root))
        listed_file = history.list_sessions()["sessions"][0]["files"][0]
        assert listed_file["preview_url"] == "/api/maps/preview?id=session&file=session_map.pcd"

        payload = history.make_preview_payload("session", "session_map.pcd", max_points=2)
        assert payload is not None
        header_length, data_offset = struct.unpack_from("<II", payload, 0)
        header = json.loads(payload[8 : 8 + header_length])
        assert header["source"] == "map"
        assert header["source_point_count"] == 3
        assert header["point_count"] == 2
        assert header["bounds"] == {"min": [1.0, 2.0, 3.0], "max": [4.0, 5.0, 6.0]}
        assert len(payload[data_offset:]) == 2 * 4 * 4
        assert history.make_preview_payload("session", "poses_tum.txt") is None


def test_map_history_session_archive_contains_only_allowed_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "session"
        session.mkdir()
        (session / "map_optimized.pcd").write_text("optimized")
        (session / "map_raw.pcd").write_text("raw")
        (session / "frontend_accumulated.pcd").write_text("legacy")
        (session / "result.pcd").write_text("result")
        (session / "session_map.pcd").write_text("compat")
        (session / "secret.txt").write_text("secret")

        archive = MapHistory(str(root)).make_session_archive("session")

        assert archive is not None
        filename, payload = archive
        assert filename == "session.zip"
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zip_file:
            assert sorted(zip_file.namelist()) == [
                "session_map.pcd",
            ]
        assert MapHistory(str(root)).make_session_archive("../session") is None


def test_map_history_delete_session_is_restricted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = root / "session"
        unrelated = root / "unrelated"
        session.mkdir()
        unrelated.mkdir()
        (session / "map_optimized.pcd").write_text("optimized")
        (session / "session_map.pcd").write_text("map")
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
    test_map_history_preview_samples_pcd_payload()
    test_map_history_session_archive_contains_only_allowed_files()
    test_map_history_delete_session_is_restricted()
    test_map_history_project_relative_root()
    print("map history ok")
