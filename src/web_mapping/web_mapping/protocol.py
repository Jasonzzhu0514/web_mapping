"""Shared browser bridge protocol constants."""

VALID_SOURCES = {"raw", "optimized", "map"}

DEFAULT_SOURCES = ("map", "optimized", "raw")

VALID_MAPPING_STATES = {"idle", "starting", "mapping", "saving", "stopping", "stopped", "error"}

VALID_MAPPING_COMMANDS = {"start", "stop", "save", "reset_error"}

SOURCE_LABELS = {
    "raw": "raw",
    "optimized": "optimized",
    "map": "map",
}
