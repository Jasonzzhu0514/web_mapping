#!/usr/bin/env python3
"""Cross-package checks for Web Mapping integration logic."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB_MAIN = ROOT / "src" / "web_mapping" / "src" / "web_mapping" / "web_mapping" / "web" / "main.js"
WEB_NODE = ROOT / "src" / "web_mapping" / "src" / "web_mapping" / "web_mapping" / "ros" / "node.py"
BROKER = ROOT / "src" / "fast_lio_sam_sc_qn2" / "scripts" / "fast_lio_web_broker.py"
WEB_CONTROL_LAUNCH = ROOT / "src" / "fast_lio_sam_sc_qn2" / "launch" / "web_mapping_control.launch.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_layer_led_availability_uses_live_topic_state_not_cached_points() -> None:
    main_js = _text(WEB_MAIN)

    assert "button.classList.toggle('is-available', online)" in main_js
    assert "button.classList.toggle('has-cache', hasCachedPoints)" in main_js
    assert "button.disabled = !online && !hasCachedPoints" in main_js
    assert "online || hasCachedPoints" not in main_js


def test_start_acceptance_clears_previous_live_mapping_scene() -> None:
    main_js = _text(WEB_MAIN)

    assert "if (payload.command === 'start')" in main_js
    assert "resetLiveMappingScene()" in main_js
    assert "state.paths.raw = []" in main_js
    assert "state.paths.optimized = []" in main_js
    assert "optimized: '/web_mapping/current_frame'" in main_js
    assert "optimized: 'corrected_map'" not in main_js


def test_stop_waits_for_backend_completion_before_history_refresh() -> None:
    main_js = _text(WEB_MAIN)
    broker = _text(BROKER)

    assert "state.mapHistory.pendingStopRefresh = true" in main_js
    assert "state.mapping.state = 'stopping'" in main_js
    assert "state.mapping.state = 'stopped'" not in main_js
    assert "state.mapping.state === 'stopped'" in main_js
    assert "handleStopCompleted()" in main_js
    assert "mappingState === 'saving' || mappingState === 'starting'" not in main_js
    assert '"雷达与建图节点正在退出，等待输出停止"' in broker
    assert "processes exited: {processes_exited}" in broker
    assert "output quiet: {output_quiet}" in broker
    assert "count_publishers(topic) == 0" in broker


def test_current_frame_stream_has_no_global_map_stale_fallback() -> None:
    broker = _text(BROKER)

    assert "current_frame_fallback_sec" not in broker
    assert "_current_frame_is_stale" not in broker
    assert "if self.current_frame_uses_global_map:" in broker
    assert "or self._current_frame_is_stale()" not in broker
    assert "livox_lidar_topic" not in broker
    assert "fast_lio_raw_cloud_topic" not in broker


def test_web_control_uses_fast_lio_realtime_frame_for_accumulation() -> None:
    launch = _text(WEB_CONTROL_LAUNCH)

    assert "'optimized_cloud_topic': '/web_mapping/current_frame'" in launch
    assert "fast_lio_current_frame_topic:=/cloud_registered_1" in launch
    assert "DeclareLaunchArgument('fast_lio_current_frame_topic', default_value='/cloud_registered_1')" in launch


def test_websocket_clients_do_not_shadow_rclpy_node_clients() -> None:
    node = _text(WEB_NODE)

    assert "self._websocket_clients" in node
    assert "self._clients:" not in node
    assert "self._clients =" not in node


if __name__ == "__main__":
    test_layer_led_availability_uses_live_topic_state_not_cached_points()
    test_start_acceptance_clears_previous_live_mapping_scene()
    test_stop_waits_for_backend_completion_before_history_refresh()
    test_current_frame_stream_has_no_global_map_stale_fallback()
    test_web_control_uses_fast_lio_realtime_frame_for_accumulation()
    test_websocket_clients_do_not_shadow_rclpy_node_clients()
    print("integration logic ok")
