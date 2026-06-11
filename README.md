# web_mapping

`web_mapping` 是一个独立的 ROS 2 Web 建图可视化项目，用于在浏览器中查看 LiDAR SLAM 的实时点云、地图、轨迹和传感器状态。

它启动一个轻量级 HTTP 服务和 WebSocket 桥接节点，将 ROS 2 topic 转成浏览器可以消费的 JSON/二进制消息。前端使用 Three.js 渲染点云图层，不依赖 npm 构建流程。

## 项目定位

`web_mapping` 只负责可视化和状态展示，不负责 SLAM 算法本身。建图后端，例如 `fast_lio_sam_sc_qn_ros2`，负责里程计、点云配准、回环优化和地图生成；本项目消费这些 ROS 2 输出并在浏览器中展示。

当前主要图层和数据源：

- 全局优化地图：默认来自 `corrected_map`，对应优化后关键帧累计地图
- 当前建图帧：默认来自 `corrected_current_pcd`，对应当前帧点云在优化位姿下的结果
- 雷达原始扫描：默认优先来自 `/livox/lidar`，不可用时回退到 `cloud_registered_1`
- 轨迹、位姿、IMU、雷达状态和 topic 频率

## 功能

- 浏览器实时点云渲染。
- 多图层显示：全局优化地图、当前建图帧、雷达原始扫描。
- 图层开关只控制显示/隐藏，不停止后台接收和缓存，避免隐藏后停止建图导致数据丢失。
- 位姿和轨迹叠加显示。
- 传感器详情卡片：连接状态、客户端数量、数据延迟、雷达频率、点数、IMU、位姿等。
- 后端 topic 状态展示：online、stale、waiting、disconnected。
- 前端 mock 模式，可在没有 ROS 2 数据时验证界面。
- 无 npm 构建步骤。
- Python 侧除 ROS 2 Python 包和标准库外，没有额外运行时依赖。

## 目录结构

项目根目录本身是一个小型 ROS 2 workspace，可运行包位于 `src/web_mapping`。

```text
web_mapping/
  README.md
  web_mapping_bridge.yaml
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
    topic_stats_test.py
    web_mapping_protocol_test.py
```

## 构建

先加载 ROS 2 环境，再构建本项目：

```bash
source /opt/ros/<distro>/setup.bash
cd /home/chu/Documents/web_mapping
./scripts/bin/build.sh
source install/setup.bash
```

如果需要接入 `fast_lio_sam_sc_qn_ros2` 的 topic，请先加载对应工作区：

```bash
source /home/chu/Documents/fast_lio_sam_sc_qn_ros2/install/setup.bash
source /home/chu/Documents/web_mapping/install/setup.bash
```

## 运行

先启动建图后端，再启动 Web Mapping：

```bash
ros2 launch web_mapping web_mapping.launch.py
```

浏览器打开：

```text
http://127.0.0.1:8765
```

如果从另一台机器访问，把 `127.0.0.1` 换成运行该节点的机器人或工作站 IP。

## 前端 mock 模式

没有 ROS 2 数据时，可以单独验证前端：

```bash
cd /home/chu/Documents/web_mapping
python3 -m http.server 8765 --directory src/web_mapping/web_mapping/web
```

打开：

```text
http://127.0.0.1:8765/?mock=1
```

## Launch 参数

- `host`：HTTP/WebSocket 监听地址，默认 `0.0.0.0`
- `port`：HTTP/WebSocket 端口，默认 `8765`
- `raw_cloud_topic`：PointCloud2 原始扫描 topic，默认 `cloud_registered_1`
- `livox_custom_topic`：Livox CustomMsg 原始扫描 topic，默认 `/livox/lidar`
- `optimized_cloud_topic`：当前建图帧 topic，默认 `corrected_current_pcd`
- `map_cloud_topic`：全局优化地图 topic，默认 `corrected_map`
- `pose_topic`：位姿 topic，默认 `pose_stamped`
- `raw_path_topic`：原始轨迹 topic，默认 `ori_path`
- `optimized_path_topic`：优化轨迹 topic，默认 `corrected_path`
- `imu_topic`：IMU topic，默认 `/livox/imu`
- `lidar_status_topic`：雷达状态文本 topic，默认空；可设置为 `std_msgs/msg/String`
- `max_points_per_cloud`：单帧点云最大采样点数，默认 `0`，表示不在后端采样
- `min_cloud_interval_sec`：非地图点云最小发送间隔，launch 默认 `0.15`
- `min_telemetry_interval_sec`：状态/位姿/IMU 最小发送间隔，默认 `0.1`
- `path_max_points`：轨迹最大下发点数，默认 `5000`

示例：

```bash
ros2 launch web_mapping web_mapping.launch.py \
  raw_cloud_topic:=/cloud_registered_1 \
  optimized_cloud_topic:=/corrected_current_pcd \
  lidar_status_topic:=/livox/status
```

也可以使用根目录的 `web_mapping_bridge.yaml` 作为运行配置参考。

注意：`fast_lio_sam_sc_qn2` 保存结果里的 `map_raw.pcd` 目前没有对应的实时 ROS topic。本项目现在实时显示的是 `corrected_map`、`corrected_current_pcd` 和雷达原始扫描。如果后续后端发布 `raw_map` topic，Web 侧可以再加入真正的“原始地图”图层。

## 浏览器协议

WebSocket 中的状态、位姿和轨迹使用 JSON 消息。点云使用二进制帧，格式如下：

```text
uint32 little-endian JSON header length
uint32 little-endian float data offset
JSON header bytes
zero padding to 4-byte alignment
Float32Array payload as x, y, z, intensity
```

协议检查：

```bash
python3 tests/web_mapping_protocol_test.py
```

topic 状态统计检查：

```bash
python3 tests/topic_stats_test.py
```
