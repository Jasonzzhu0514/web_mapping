#!/usr/bin/env python3
"""Topic health snapshot checks."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "web_mapping"))

from web_mapping.runtime.stats import TopicStats  # noqa: E402


def test_stale_topic_reports_zero_live_metrics() -> None:
    stats = TopicStats("/livox/lidar")
    stats.record(points=20000, sampled_points=20000, stamp_sec=1.0)
    stats.record(points=21000, sampled_points=21000, stamp_sec=1.1)

    stale_snapshot = stats.snapshot(stats.last_received_monotonic + 2.1)

    assert stale_snapshot["state"] == "stale"
    assert stale_snapshot["hz"] == 0.0
    assert stale_snapshot["last_points"] == 0
    assert stale_snapshot["last_sampled_points"] == 0
    assert stale_snapshot["frames"] == 2


def test_online_topic_keeps_live_metrics() -> None:
    stats = TopicStats("/livox/lidar")
    stats.record(points=20000, sampled_points=19000, stamp_sec=1.0)
    stats.record(points=21000, sampled_points=20000, stamp_sec=1.1)

    online_snapshot = stats.snapshot(stats.last_received_monotonic + 0.1)

    assert online_snapshot["state"] == "online"
    assert online_snapshot["hz"] > 0.0
    assert online_snapshot["last_points"] == 21000
    assert online_snapshot["last_sampled_points"] == 20000


if __name__ == "__main__":
    test_stale_topic_reports_zero_live_metrics()
    test_online_topic_keeps_live_metrics()
    print("topic stats ok")
