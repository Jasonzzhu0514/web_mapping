"""ROS 2 node that bridges mapping topics to the browser UI."""

from __future__ import annotations

import json
import math
import threading
import time
from http.server import ThreadingHTTPServer
from typing import Any

from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path as RosPath
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu, PointCloud2
from std_msgs.msg import String

from web_mapping.pointcloud.codec import (
    extract_cloud_xyzi,
    extract_livox_custom_xyzi,
    make_binary_cloud_payload,
    stamp_to_float,
)
from web_mapping.protocol import DEFAULT_MAP_HISTORY_ROOT, WEB_MAPPING_TOPICS, VALID_SOURCES
from web_mapping.runtime.map_history import MapHistory
from web_mapping.runtime.mapping_manager import MappingManager
from web_mapping.runtime.ros_broker import RosBrokerBackend
from web_mapping.runtime.stats import TopicStats
from web_mapping.transport.http_server import create_http_server
from web_mapping.transport.websocket import WebSocketClient

try:
    from livox_ros_driver2.msg import CustomMsg as LivoxCustomMsg
except Exception:  # noqa: BLE001
    LivoxCustomMsg = None


class MappingWebBridge(Node):
    def __init__(self) -> None:
        super().__init__("web_mapping_bridge")
        self._declare_parameters()

        self.host = str(self.get_parameter("host").value)
        self.port = int(self.get_parameter("port").value)
        self.max_points_per_cloud = int(self.get_parameter("max_points_per_cloud").value)
        self.min_cloud_interval_sec = float(self.get_parameter("min_cloud_interval_sec").value)
        self.min_telemetry_interval_sec = float(self.get_parameter("min_telemetry_interval_sec").value)
        self.path_max_points = int(self.get_parameter("path_max_points").value)
        self.map_history_root = str(self.get_parameter("map_history_root").value)
        self.map_history_limit = int(self.get_parameter("map_history_limit").value)
        self.mapping_command_topic = str(self.get_parameter("mapping_command_topic").value)
        self.mapping_status_topic = str(self.get_parameter("mapping_status_topic").value)
        self.use_broker_backend = bool(self.get_parameter("use_broker_backend").value)
        self.log_http_requests = bool(self.get_parameter("log_http_requests").value)

        self.raw_cloud_topic = str(self.get_parameter("raw_cloud_topic").value)
        self.livox_custom_topic = str(self.get_parameter("livox_custom_topic").value)
        self.optimized_cloud_topic = str(self.get_parameter("optimized_cloud_topic").value)
        self.map_cloud_topic = str(self.get_parameter("map_cloud_topic").value)
        self.pose_topic = str(self.get_parameter("pose_topic").value)
        self.raw_path_topic = str(self.get_parameter("raw_path_topic").value)
        self.optimized_path_topic = str(self.get_parameter("optimized_path_topic").value)
        self.imu_topic = str(self.get_parameter("imu_topic").value)
        self.lidar_status_topic = str(self.get_parameter("lidar_status_topic").value)

        self._lock = threading.Lock()
        self._clients: set[WebSocketClient] = set()
        self._last_cloud_sent_at = {source: 0.0 for source in VALID_SOURCES}
        self._last_telemetry_sent_at = {"pose": 0.0, "imu": 0.0, "path_raw": 0.0, "path_optimized": 0.0}
        self._pose: dict[str, Any] | None = None
        self._imu: dict[str, Any] | None = None
        self._lidar_status_text = ""
        self._seq = 0
        self.map_history = MapHistory(self.map_history_root, self.map_history_limit)

        self.stats = {
            "raw": TopicStats(self.livox_custom_topic or self.raw_cloud_topic),
            "optimized": TopicStats(self.optimized_cloud_topic),
            "map": TopicStats(self.map_cloud_topic),
            "pose": TopicStats(self.pose_topic),
            "raw_path": TopicStats(self.raw_path_topic),
            "optimized_path": TopicStats(self.optimized_path_topic),
            "imu": TopicStats(self.imu_topic),
            "lidar_status": TopicStats(self.lidar_status_topic),
        }

        cloud_qos = QoSProfile(depth=5)
        cloud_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        reliable_qos = QoSProfile(depth=10)
        status_qos = QoSProfile(depth=1)
        status_qos.reliability = ReliabilityPolicy.RELIABLE
        status_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        sensor_qos = QoSProfile(depth=50)
        sensor_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.mapping_command_pub = None
        if self.use_broker_backend and self.mapping_command_topic:
            self.mapping_command_pub = self.create_publisher(String, self.mapping_command_topic, reliable_qos)
            self.mapping_manager = MappingManager(RosBrokerBackend(self.mapping_command_pub))
        else:
            self.mapping_manager = MappingManager()

        if self.livox_custom_topic and LivoxCustomMsg is not None:
            self.create_subscription(
                LivoxCustomMsg,
                self.livox_custom_topic,
                lambda msg: self._livox_custom_callback("raw", msg),
                reliable_qos,
            )
        else:
            if self.livox_custom_topic and LivoxCustomMsg is None:
                self.get_logger().warning(
                    "livox_custom_topic is set but livox_ros_driver2 is not available; "
                    f"falling back to PointCloud2 raw_cloud_topic={self.raw_cloud_topic}"
                )
                self.stats["raw"].topic = self.raw_cloud_topic
            self.create_subscription(
                PointCloud2,
                self.raw_cloud_topic,
                lambda msg: self._cloud_callback("raw", msg),
                cloud_qos,
            )
        self.create_subscription(
            PointCloud2,
            self.optimized_cloud_topic,
            lambda msg: self._cloud_callback("optimized", msg),
            cloud_qos,
        )
        self.create_subscription(PointCloud2, self.map_cloud_topic, lambda msg: self._cloud_callback("map", msg), map_qos)
        self.create_subscription(PoseStamped, self.pose_topic, self._pose_callback, reliable_qos)
        self.create_subscription(RosPath, self.raw_path_topic, lambda msg: self._path_callback("raw", msg), reliable_qos)
        self.create_subscription(
            RosPath,
            self.optimized_path_topic,
            lambda msg: self._path_callback("optimized", msg),
            reliable_qos,
        )
        if self.imu_topic:
            self.create_subscription(Imu, self.imu_topic, self._imu_callback, sensor_qos)
        if self.lidar_status_topic:
            self.create_subscription(String, self.lidar_status_topic, self._lidar_status_callback, status_qos)
        if self.mapping_status_topic:
            self.create_subscription(String, self.mapping_status_topic, self._mapping_status_callback, status_qos)

        self._status_timer = self.create_timer(1.0, self._broadcast_status)
        self._httpd = self._start_http_server()

        self.get_logger().info(f"Web mapping demo: http://{self.host_for_display()}:{self.port}")
        self.get_logger().info(
            "Cloud topics: "
            f"raw={self.stats['raw'].topic} "
            f"optimized={self.optimized_cloud_topic} "
            f"map={self.map_cloud_topic} "
            f"imu={self.imu_topic or '-'}"
        )

    def _declare_parameters(self) -> None:
        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 8765)
        self.declare_parameter("raw_cloud_topic", WEB_MAPPING_TOPICS["raw_cloud"])
        self.declare_parameter("livox_custom_topic", "")
        self.declare_parameter("optimized_cloud_topic", WEB_MAPPING_TOPICS["current_frame"])
        self.declare_parameter("map_cloud_topic", WEB_MAPPING_TOPICS["global_map"])
        self.declare_parameter("pose_topic", WEB_MAPPING_TOPICS["pose"])
        self.declare_parameter("raw_path_topic", WEB_MAPPING_TOPICS["raw_path"])
        self.declare_parameter("optimized_path_topic", WEB_MAPPING_TOPICS["optimized_path"])
        self.declare_parameter("imu_topic", WEB_MAPPING_TOPICS["imu"])
        self.declare_parameter("lidar_status_topic", WEB_MAPPING_TOPICS["lidar_status"])
        self.declare_parameter("max_points_per_cloud", 0)
        self.declare_parameter("min_cloud_interval_sec", 0.08)
        self.declare_parameter("min_telemetry_interval_sec", 0.1)
        self.declare_parameter("path_max_points", 5000)
        self.declare_parameter("map_history_root", DEFAULT_MAP_HISTORY_ROOT)
        self.declare_parameter("map_history_limit", 20)
        self.declare_parameter("mapping_command_topic", WEB_MAPPING_TOPICS["mapping_command"])
        self.declare_parameter("mapping_status_topic", WEB_MAPPING_TOPICS["mapping_status"])
        self.declare_parameter("use_broker_backend", True)
        self.declare_parameter("log_http_requests", False)

    def host_for_display(self) -> str:
        if self.host in {"0.0.0.0", "::"}:
            return "127.0.0.1"
        return self.host

    def add_client(self, client: WebSocketClient) -> None:
        with self._lock:
            self._clients.add(client)
        self.get_logger().info(f"Web client connected: {client.address[0]}:{client.address[1]}")

    def remove_client(self, client: WebSocketClient) -> None:
        with self._lock:
            self._clients.discard(client)

    def handle_client_message(self, client: WebSocketClient, message: dict[str, Any]) -> None:
        if message.get("type") == "select_source":
            source = str(message.get("source", "")).strip()
            if source in VALID_SOURCES:
                client.selected_source = source
                client.selected_sources = {source}
                client.send_json({"type": "selected_source", "source": source})
                client.send_json(self.make_status_payload(source))
        elif message.get("type") == "set_sources":
            requested = message.get("sources", [])
            if not isinstance(requested, list):
                return
            sources = {str(source).strip() for source in requested if str(source).strip() in VALID_SOURCES}
            client.selected_sources = sources
            client.selected_source = next(iter(sources), "")
            client.send_json({"type": "selected_sources", "selected_sources": sorted(sources)})
            client.send_json(self.make_status_payload(client.selected_source or None))
        elif message.get("type") == "mapping_command":
            command = str(message.get("command", "")).strip()
            result = self.mapping_manager.handle_command(command, message)
            payload = {
                "type": "mapping_command_result",
                "command": result.command,
                "accepted": result.accepted,
                "state": result.state,
                "message": result.message,
                "details": result.details or {},
                "mapping": self.mapping_manager.snapshot(),
            }
            client.send_json(payload)
            self._broadcast_mapping_status()

    def make_status_payload(self, selected_source: str | None = None) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            client_count = len(self._clients)
            pose = dict(self._pose) if self._pose else None
            imu = dict(self._imu) if self._imu else None
            lidar_status = self._lidar_status_text
        return {
            "type": "status",
            "server_time": time.time(),
            "selected_source": selected_source,
            "client_count": client_count,
            "lidar": {
                "state": self._lidar_state(now),
                "status_text": lidar_status,
                "raw_topic": self.stats["raw"].topic,
            },
            "topics": {name: stat.snapshot(now) for name, stat in self.stats.items() if stat.topic},
            "mapping": self.mapping_manager.snapshot(),
            "pose": pose,
            "imu": imu,
        }

    def destroy_node(self) -> bool:
        if hasattr(self, "_httpd"):
            self._httpd.shutdown()
            self._httpd.server_close()
        return super().destroy_node()

    def _start_http_server(self) -> ThreadingHTTPServer:
        httpd = create_http_server(self.host, self.port, self)
        thread = threading.Thread(target=httpd.serve_forever, name="web-mapping-http", daemon=True)
        thread.start()
        return httpd

    def _cloud_callback(self, source: str, msg: PointCloud2) -> None:
        now = time.monotonic()
        point_count = int(msg.width * msg.height)
        stamp_sec = stamp_to_float(msg.header.stamp)
        if source != "map" and now - self._last_cloud_sent_at[source] < self.min_cloud_interval_sec:
            self.stats[source].record(point_count, 0, stamp_sec)
            return

        clients = self._clients_for_source(source)
        if not clients:
            self.stats[source].record(point_count, 0, stamp_sec)
            return

        try:
            cloud = extract_cloud_xyzi(msg, self.max_points_per_cloud)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warning(f"Failed to encode {source} cloud: {exc}")
            self.stats[source].record(point_count, 0, stamp_sec)
            return

        self.stats[source].record(point_count, cloud["point_count"], stamp_sec)
        if cloud["point_count"] <= 0:
            return

        self._last_cloud_sent_at[source] = now
        with self._lock:
            self._seq += 1
            seq = self._seq
        header = {
            "type": "cloud",
            "source": SOURCE_LABELS[source],
            "topic": self.stats[source].topic,
            "seq": seq,
            "frame_id": msg.header.frame_id,
            "stamp_sec": stamp_sec,
            "point_count": cloud["point_count"],
            "source_point_count": point_count,
            "sample_every": cloud["sample_every"],
            "stride": 4,
            "layout": "float32_xyzi",
            "has_intensity": cloud["has_intensity"],
            "bounds": cloud["bounds"],
            "intensity_range": cloud["intensity_range"],
        }
        payload = make_binary_cloud_payload(header, cloud["values"])
        for client in clients:
            client.send_binary(payload)

    def _livox_custom_callback(self, source: str, msg: Any) -> None:
        now = time.monotonic()
        point_count = int(getattr(msg, "point_num", len(getattr(msg, "points", []))) or 0)
        stamp_sec = stamp_to_float(msg.header.stamp)
        if now - self._last_cloud_sent_at[source] < self.min_cloud_interval_sec:
            self.stats[source].record(point_count, 0, stamp_sec)
            return

        clients = self._clients_for_source(source)
        if not clients:
            self.stats[source].record(point_count, 0, stamp_sec)
            return

        try:
            cloud = extract_livox_custom_xyzi(msg, self.max_points_per_cloud)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warning(f"Failed to encode Livox custom cloud: {exc}")
            self.stats[source].record(point_count, 0, stamp_sec)
            return

        self.stats[source].record(point_count, cloud["point_count"], stamp_sec)
        if cloud["point_count"] <= 0:
            return

        self._last_cloud_sent_at[source] = now
        with self._lock:
            self._seq += 1
            seq = self._seq
        header = {
            "type": "cloud",
            "source": SOURCE_LABELS[source],
            "topic": self.stats[source].topic,
            "seq": seq,
            "frame_id": msg.header.frame_id,
            "stamp_sec": stamp_sec,
            "point_count": cloud["point_count"],
            "source_point_count": point_count,
            "sample_every": cloud["sample_every"],
            "stride": 4,
            "layout": "float32_xyzi",
            "has_intensity": cloud["has_intensity"],
            "bounds": cloud["bounds"],
            "intensity_range": cloud["intensity_range"],
        }
        payload = make_binary_cloud_payload(header, cloud["values"])
        for client in clients:
            client.send_binary(payload)

    def _pose_callback(self, msg: PoseStamped) -> None:
        pose = msg.pose
        payload = {
            "type": "pose",
            "frame_id": msg.header.frame_id,
            "stamp_sec": stamp_to_float(msg.header.stamp),
            "x": pose.position.x,
            "y": pose.position.y,
            "z": pose.position.z,
            "yaw": _yaw_from_quaternion(
                pose.orientation.x,
                pose.orientation.y,
                pose.orientation.z,
                pose.orientation.w,
            ),
        }
        with self._lock:
            self._pose = payload
        self.stats["pose"].record(1, 1, payload["stamp_sec"])
        if not self._should_send_telemetry("pose"):
            return
        self._broadcast_json(payload)

    def _imu_callback(self, msg: Imu) -> None:
        angular_velocity = [
            float(msg.angular_velocity.x),
            float(msg.angular_velocity.y),
            float(msg.angular_velocity.z),
        ]
        linear_acceleration = [
            float(msg.linear_acceleration.x),
            float(msg.linear_acceleration.y),
            float(msg.linear_acceleration.z),
        ]
        orientation = [
            float(msg.orientation.x),
            float(msg.orientation.y),
            float(msg.orientation.z),
            float(msg.orientation.w),
        ]
        stamp_sec = stamp_to_float(msg.header.stamp)
        payload = {
            "type": "imu",
            "topic": self.imu_topic,
            "frame_id": msg.header.frame_id,
            "stamp_sec": stamp_sec,
            "angular_velocity": angular_velocity,
            "linear_acceleration": linear_acceleration,
            "orientation": orientation,
            "gyro_norm": math.sqrt(sum(value * value for value in angular_velocity)),
            "accel_norm": math.sqrt(sum(value * value for value in linear_acceleration)),
        }
        with self._lock:
            self._imu = payload
        self.stats["imu"].record(1, 1, stamp_sec)
        if not self._should_send_telemetry("imu"):
            return
        self._broadcast_json(payload)

    def _path_callback(self, source: str, msg: RosPath) -> None:
        poses = msg.poses
        if not poses:
            points: list[list[float]] = []
        else:
            sample_every = max(1, math.ceil(len(poses) / max(1, self.path_max_points)))
            points = [
                [pose.pose.position.x, pose.pose.position.y, pose.pose.position.z]
                for pose in poses[::sample_every]
            ]
        stat_key = "raw_path" if source == "raw" else "optimized_path"
        stamp_sec = stamp_to_float(msg.header.stamp)
        self.stats[stat_key].record(len(poses), len(points), stamp_sec)
        if not self._should_send_telemetry(f"path_{source}"):
            return
        self._broadcast_json(
            {
                "type": "path",
                "source": source,
                "topic": self.stats[stat_key].topic,
                "frame_id": msg.header.frame_id,
                "stamp_sec": stamp_sec,
                "point_count": len(points),
                "source_point_count": len(poses),
                "points": points,
            }
        )

    def _lidar_status_callback(self, msg: String) -> None:
        with self._lock:
            self._lidar_status_text = msg.data
        self.stats["lidar_status"].record(1, 1, None)

    def _mapping_status_callback(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring invalid mapping status JSON from broker")
            return
        if not isinstance(payload, dict):
            return
        map_history_root = str(payload.get("map_history_root", "")).strip()
        if map_history_root and map_history_root != self.map_history_root:
            self.map_history_root = map_history_root
            self.map_history = MapHistory(self.map_history_root, self.map_history_limit)
        self.mapping_manager.apply_status(payload)
        self._broadcast_mapping_status()

    def _broadcast_status(self) -> None:
        clients = self._all_clients()
        for client in clients:
            client.send_json(self.make_status_payload(client.selected_source))

    def _broadcast_mapping_status(self) -> None:
        payload = {
            "type": "mapping_status",
            "mapping": self.mapping_manager.snapshot(),
        }
        self._broadcast_json(payload)

    def _broadcast_json(self, payload: dict[str, Any]) -> None:
        for client in self._all_clients():
            client.send_json(payload)

    def _should_send_telemetry(self, key: str) -> bool:
        now = time.monotonic()
        last_sent = self._last_telemetry_sent_at.get(key, 0.0)
        if now - last_sent < self.min_telemetry_interval_sec:
            return False
        self._last_telemetry_sent_at[key] = now
        return True

    def _all_clients(self) -> list[WebSocketClient]:
        with self._lock:
            return [client for client in self._clients if client.alive]

    def _clients_for_source(self, source: str) -> list[WebSocketClient]:
        with self._lock:
            return [client for client in self._clients if client.alive and source in client.selected_sources]

    def _lidar_state(self, now: float) -> str:
        raw_age = None
        if self.stats["raw"].last_received_monotonic > 0:
            raw_age = now - self.stats["raw"].last_received_monotonic
        if raw_age is None:
            return "waiting"
        return "online" if raw_age < 2.0 else "stale"


def _yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)
