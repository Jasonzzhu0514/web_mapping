#!/usr/bin/env python3
"""Console entry point for the web mapping bridge."""

from __future__ import annotations

import rclpy

from web_mapping.ros.node import MappingWebBridge


def main() -> None:
    rclpy.init()
    node = MappingWebBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

