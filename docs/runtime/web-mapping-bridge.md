# Web Mapping Bridge

The bridge is a small ROS 2 Python node plus a static browser UI.

## Runtime Shape

- `web_mapping.ros.node` owns ROS 2 subscriptions, topic statistics, source
  selection, and status aggregation.
- `web_mapping.transport` serves static frontend files and implements the
  minimal WebSocket framing used by browsers.
- `web_mapping.pointcloud` extracts `PointCloud2` `x/y/z/intensity` data and
  packs it into the binary browser payload.
- `web_mapping.runtime` contains non-ROS runtime helpers such as topic rate and
  freshness tracking.
- `web_mapping.web` contains the no-build frontend.

## Browser Protocol

JSON WebSocket messages carry status, pose, and path updates. Point clouds use a
binary WebSocket frame:

```text
uint32 little-endian JSON header length
uint32 little-endian float data offset
JSON header bytes
zero padding to 4-byte alignment
Float32Array payload as x, y, z, intensity
```

The frontend can also run in mock mode without ROS 2:

```bash
python3 -m http.server 8765 --directory src/web_mapping/web_mapping/web
```

