# web_mapping

`web_mapping` 是一个独立的 ROS 2 Web 建图可视化项目，用于在浏览器中查看 LiDAR SLAM 的实时点云、地图、轨迹和传感器状态。

它启动一个轻量级 HTTP 服务和 WebSocket 桥接节点，将 ROS 2 topic 转成浏览器可以消费的 JSON/二进制消息。前端使用 Three.js 渲染点云图层，不依赖 npm 构建流程。

## 项目定位

`web_mapping` 只负责可视化、状态展示和 Web 控制接口，不负责 SLAM 算法本身。实际建图程序负责里程计、点云配准、回环优化和地图生成；本项目消费这些 ROS 2 输出并在浏览器中展示。

当前主要图层和数据源：

- 全局优化地图：默认订阅 `/web_mapping/global_map`
- 当前建图帧：默认订阅 `/web_mapping/current_frame`
- 雷达原始扫描：默认订阅 `/web_mapping/raw_cloud`
- 轨迹、位姿、IMU、雷达状态和 topic 频率

## 功能

- 浏览器实时点云渲染。
- 多图层显示：全局优化地图、当前建图帧、雷达原始扫描。
- 图层开关只控制显示/隐藏，不停止后台接收和缓存。
- 位姿和轨迹叠加显示。
- 传感器详情卡片：连接状态、客户端数量、数据延迟、雷达频率、点数、IMU、位姿等。
- topic 状态展示：online、stale、waiting、disconnected。
- 建图控制壳子：左侧栏提供开始建图、停止建图、保存地图和地图名称控件，并通过 WebSocket 暴露状态机接口。
- 历史地图列表：读取已保存地图，支持下载整份地图包或单个地图/位姿文件到本地。
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
          map_history.py
          mapping_manager.py
        transport/
        web/
          index.html
          main.js
          styles.css
  tests/
    map_history_test.py
    topic_stats_test.py
    web_mapping_protocol_test.py
```

## 构建

先加载 ROS 2 环境，再构建本项目：

```bash
source /opt/ros/<distro>/setup.bash
cd <web_mapping_workspace>
./scripts/bin/build.sh
source install/setup.bash
```

## 运行

先启动建图程序或数据源，再启动 Web Mapping：

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
cd <web_mapping_workspace>
python3 -m http.server 8765 --directory src/web_mapping/web_mapping/web
```

打开：

```text
http://127.0.0.1:8765/?mock=1
```

## Launch 参数

- `host`：HTTP/WebSocket 监听地址，默认 `0.0.0.0`
- `port`：HTTP/WebSocket 端口，默认 `8765`
- `raw_cloud_topic`：雷达原始点云 topic，默认 `/web_mapping/raw_cloud`
- `livox_custom_topic`：Livox CustomMsg 原始点云 topic；为空时使用 `raw_cloud_topic`
- `optimized_cloud_topic`：当前建图帧 topic，默认 `/web_mapping/current_frame`
- `map_cloud_topic`：全局优化地图 topic，默认 `/web_mapping/global_map`
- `pose_topic`：位姿 topic，默认 `/web_mapping/pose`
- `raw_path_topic`：原始轨迹 topic，默认 `/web_mapping/raw_path`
- `optimized_path_topic`：优化轨迹 topic，默认 `/web_mapping/optimized_path`
- `imu_topic`：IMU topic，默认 `/web_mapping/imu`
- `lidar_status_topic`：雷达状态文本 topic，默认 `/web_mapping/lidar_status`
- `mapping_command_topic`：Web 发给算法 broker 的建图命令 JSON topic，默认 `/web_mapping/command`
- `mapping_status_topic`：算法 broker 发给 Web 的建图状态 JSON topic，默认 `/web_mapping/status`
- `use_broker_backend`：是否通过 ROS broker topic 转发建图控制，默认 `true`
- `max_points_per_cloud`：单帧点云最大采样点数，默认 `0`，表示不在桥接端采样
- `min_cloud_interval_sec`：非地图点云最小发送间隔，launch 默认 `0.15`
- `min_telemetry_interval_sec`：状态/位姿/IMU 最小发送间隔，默认 `0.1`
- `path_max_points`：轨迹最大下发点数，默认 `5000`
- `map_history_root`：历史地图根目录，默认 `web_mapping/maps`
- `map_history_limit`：历史地图列表最大数量，默认 `20`

示例：

```bash
ros2 launch web_mapping web_mapping.launch.py \
  raw_cloud_topic:=/web_mapping/raw_cloud \
  optimized_cloud_topic:=/web_mapping/current_frame \
  map_cloud_topic:=/web_mapping/global_map \
  pose_topic:=/web_mapping/pose
```

也可以使用根目录的 `web_mapping_bridge.yaml` 作为运行配置参考。

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

历史地图检查：

```bash
python3 tests/map_history_test.py
```

## 建图控制接口

`web_mapping` 通过标准 ROS topic 与算法 broker 通信。Web 自己不关心具体 SLAM 算法，只消费 broker 对齐后的 topic、状态和地图目录。

### Broker Topic Contract

算法 broker 应发布：

- `/web_mapping/raw_cloud`：`sensor_msgs/msg/PointCloud2`
- `/web_mapping/current_frame`：`sensor_msgs/msg/PointCloud2`
- `/web_mapping/global_map`：`sensor_msgs/msg/PointCloud2`
- `/web_mapping/pose`：`geometry_msgs/msg/PoseStamped`
- `/web_mapping/raw_path`：`nav_msgs/msg/Path`
- `/web_mapping/optimized_path`：`nav_msgs/msg/Path`
- `/web_mapping/imu`：`sensor_msgs/msg/Imu`
- `/web_mapping/lidar_status`：`std_msgs/msg/String`
- `/web_mapping/status`：`std_msgs/msg/String`，内容为 JSON

算法 broker 应订阅：

- `/web_mapping/command`：`std_msgs/msg/String`，内容为 JSON

命令 JSON：

浏览器发送：

```json
{
  "type": "mapping_command",
  "command": "start",
  "session_name": "demo",
  "save_directory": ""
}
```

界面里的“地图名称”对应协议里的 `session_name`。`save_directory` 默认不向用户暴露，通常由算法 broker 自己决定。

支持的 `command`：

- `start`：请求开始建图
- `stop`：请求停止建图
- `save`：请求保存地图
- `reset_error`：预留的错误状态复位

状态机：

- `idle`：未开始
- `starting`：正在请求启动
- `mapping`：建图中
- `saving`：正在请求保存
- `stopping`：正在请求停止
- `stopped`：已停止，允许保存当前会话
- `error`：控制接口错误

状态 JSON：

```json
{
  "type": "mapping_status",
  "state": "mapping",
  "message": "正在建图",
  "session_name": "sequence_20260612_110000",
  "map_history_root": "web_mapping/maps",
  "last_command": "start",
  "last_result": "accepted"
}
```

`map_history_root` 由算法 broker 暴露，指向该 SLAM 算法真实保存地图的路径。`web_mapping` 自带的 `map_history_root` 只是没有 broker 时的默认值。

## 历史地图下载

左侧“历史地图”卡片会读取 `map_history_root` 下的保存结果目录。默认结构：

```text
<map_history_root>/<session>/
```

当前允许下载这些文件：

- `map_optimized.pcd`
- `map_raw.pcd`
- `poses_matrix.txt`
- `poses_kitti.txt`
- `poses_tum.txt`

HTTP API：

- `GET /api/maps`：返回历史地图列表
- `GET /api/maps/download?id=<session>&file=<filename>`：下载指定文件
- `GET /api/maps/download_session?id=<session>`：下载整份地图 zip 包
- `DELETE /api/maps/session?id=<session>`：删除指定历史地图

下载和删除接口都限制在 `map_history_root` 内。单文件下载只允许上述白名单文件名；删除只允许删除可识别的历史地图会话目录，避免任意文件读取或误删。
