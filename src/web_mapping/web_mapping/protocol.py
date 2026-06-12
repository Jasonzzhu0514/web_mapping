"""Shared browser bridge protocol constants."""

VALID_SOURCES = {"raw", "optimized", "map"}

DEFAULT_SOURCES = ("map", "optimized", "raw")

VALID_MAPPING_STATES = {"idle", "starting", "mapping", "saving", "stopping", "stopped", "error"}

VALID_MAPPING_COMMANDS = {"start", "stop", "save", "reset_error"}

WEB_MAPPING_TOPICS = {
    "raw_cloud": "/web_mapping/raw_cloud",
    "current_frame": "/web_mapping/current_frame",
    "global_map": "/web_mapping/global_map",
    "pose": "/web_mapping/pose",
    "raw_path": "/web_mapping/raw_path",
    "optimized_path": "/web_mapping/optimized_path",
    "imu": "/web_mapping/imu",
    "lidar_status": "/web_mapping/lidar_status",
    "mapping_command": "/web_mapping/command",
    "mapping_status": "/web_mapping/status",
}

DEFAULT_MAP_HISTORY_ROOT = "maps"

SOURCE_LABELS = {
    "raw": "raw",
    "optimized": "optimized",
    "map": "map",
}
