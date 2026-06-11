# web_mapping

Standalone ROS 2 web mapping viewer for LiDAR mapping pipelines.

It serves a static browser UI and bridges ROS 2 topics to the browser over a
small WebSocket protocol. The frontend is based on the point-cloud rendering
approach used in `drone3plot`: point data is kept as typed arrays and rendered
as GPU/browser point layers, with a Canvas 2D fallback for machines without a
usable WebGL context.

## Responsibility Split

`web_mapping` is the browser-side mapping viewer, not the SLAM backend. The
mapping stack, such as `fast_lio_sam_sc_qn_ros2`, is responsible for odometry,
registration, loop correction, and map generation. This project consumes those
ROS 2 outputs and renders them as persistent browser layers:

- global map layer from `corrected_map`
- optimized/current mapping layer from `corrected_current_pcd`
- optional raw scan layer from `/livox/lidar` or `cloud_registered_1`
- path, pose, IMU, and lidar health cards

## Features

- Realtime point cloud view in a browser.
- Persistent multi-layer rendering:
  - map: `corrected_map`
  - optimized scan/map increment: `corrected_current_pcd`
  - optional raw scan: `/livox/lidar` or `cloud_registered_1`
- Pose and path overlay.
- Sensor cards for lidar, IMU, pose, topic state, frequency, point count,
  client count, and optional lidar status text.
- Mock mode for frontend verification without ROS 2 data.
- No npm build step.
- No Python dependencies beyond ROS 2 Python packages and the Python standard
  library.

## Layout

The project root is a small ROS 2 workspace. The runnable package lives under
`src/web_mapping`, matching the cleaner repo layout used by `drone3plot`.

```text
web_mapping/
  README.md
  docs/
    runtime/
      web-mapping-bridge.md
  scripts/
    bin/
      build.sh
  src/
    web_mapping/
      package.xml
      setup.py
      setup.cfg
      launch/
        web_mapping.launch.py
      resource/
        web_mapping
      web_mapping/
        bridge.py
        protocol.py
        pointcloud/
        ros/
        runtime/
        transport/
        web/
          index.html
          main.js
          styles.css
  tests/
    web_mapping_protocol_test.py
```

## Build

Source ROS 2 first:

```bash
source /opt/ros/<distro>/setup.bash
cd /home/chu/Documents/web_mapping
./scripts/bin/build.sh
source install/setup.bash
```

## Run

Start your mapping stack first, then run:

```bash
ros2 launch web_mapping web_mapping.launch.py
```

Open:

```text
http://127.0.0.1:8765
```

From another machine, replace `127.0.0.1` with the robot or workstation IP.

## Mock Frontend

To verify the frontend without ROS 2 data:

```bash
cd /home/chu/Documents/web_mapping
python3 -m http.server 8765 --directory src/web_mapping/web_mapping/web
```

Open:

```text
http://127.0.0.1:8765/?mock=1
```

If WebGL is unavailable:

```text
http://127.0.0.1:8765/?mock=1&renderer=2d
```

## Launch Arguments

- `host`: default `0.0.0.0`
- `port`: default `8765`
- `raw_cloud_topic`: default `cloud_registered_1`
- `livox_custom_topic`: default `/livox/lidar`. If `livox_ros_driver2` is
  available in the sourced environment, this is used as the raw cloud source.
- `optimized_cloud_topic`: default `corrected_current_pcd`
- `map_cloud_topic`: default `corrected_map`
- `pose_topic`: default `pose_stamped`
- `raw_path_topic`: default `ori_path`
- `optimized_path_topic`: default `corrected_path`
- `imu_topic`: default `/livox/imu`
- `lidar_status_topic`: default empty. Set this to a `std_msgs/msg/String`
  topic if your lidar driver or health monitor publishes one.
- `max_points_per_cloud`: default `0`, meaning no per-message sampling. Set a
  positive value to cap points per incoming cloud message.
- `min_cloud_interval_sec`: default `0.08`
- `path_max_points`: default `5000`

Example:

```bash
ros2 launch web_mapping web_mapping.launch.py \
  raw_cloud_topic:=/cloud_registered_1 \
  optimized_cloud_topic:=/corrected_current_pcd \
  lidar_status_topic:=/livox/status
```

## Protocol

The bridge sends JSON WebSocket messages for status, pose, and path updates.
Point clouds are binary WebSocket frames:

```text
uint32 little-endian JSON header length
uint32 little-endian float data offset
JSON header bytes
zero padding to 4-byte alignment
Float32Array payload as x, y, z, intensity
```

Run the protocol check:

```bash
python3 tests/web_mapping_protocol_test.py
```
