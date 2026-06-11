"""Topic health and rate tracking."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TopicStats:
    topic: str
    frames: int = 0
    last_received_monotonic: float = 0.0
    last_stamp_sec: float | None = None
    last_points: int = 0
    last_sampled_points: int = 0
    times: deque[float] = field(default_factory=lambda: deque(maxlen=120))

    def record(self, points: int = 0, sampled_points: int = 0, stamp_sec: float | None = None) -> None:
        now = time.monotonic()
        self.frames += 1
        self.last_received_monotonic = now
        self.last_stamp_sec = stamp_sec
        self.last_points = int(points)
        self.last_sampled_points = int(sampled_points)
        self.times.append(now)

    def hz(self) -> float:
        if len(self.times) < 2:
            return 0.0
        elapsed = self.times[-1] - self.times[0]
        if elapsed <= 0:
            return 0.0
        return (len(self.times) - 1) / elapsed

    def snapshot(self, now: float) -> dict[str, Any]:
        age = None
        state = "waiting"
        if self.last_received_monotonic > 0:
            age = max(0.0, now - self.last_received_monotonic)
            state = "online" if age < 2.0 else "stale"
        is_online = state == "online"
        return {
            "topic": self.topic,
            "frames": self.frames,
            "hz": round(self.hz(), 2) if is_online else 0.0,
            "age_sec": None if age is None else round(age, 3),
            "last_stamp_sec": self.last_stamp_sec,
            "last_points": self.last_points if is_online else 0,
            "last_sampled_points": self.last_sampled_points if is_online else 0,
            "state": state,
        }
