# web_mapping

`web_mapping` 是一个独立的 ROS 2 Web 建图可视化项目，用于在浏览器中查看 LiDAR SLAM 的实时点云、地图、轨迹和传感器状态。

它启动一个轻量级 HTTP 服务和 WebSocket 桥接节点，将 ROS 2 topic 转成浏览器可以消费的 JSON/二进制消息。前端使用 Three.js 渲染点云图层，不依赖 npm 构建流程。

## 项目定位

`web_mapping` 只负责可视化、状态展示和 Web 控制接口，不负责 SLAM 算法本身。实际建图程序负责里程计、点云配准、回环优化和地图生成；本项目消费这些 ROS 2 输出并在浏览器中展示。

当前主要图层和数据源：

- 全局优化地图：累计地图点云 topic
- 当前建图帧：当前帧或局部建图点云 topic
- 雷达原始扫描：雷达实时点云 topic
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
- `raw_cloud_topic`：雷达原始点云 topic
- `livox_custom_topic`：Livox CustomMsg 原始点云 topic；为空时使用 `raw_cloud_topic`
- `optimized_cloud_topic`：当前建图帧 topic
- `map_cloud_topic`：全局优化地图 topic
- `pose_topic`：位姿 topic
- `raw_path_topic`：原始轨迹 topic
- `optimized_path_topic`：优化轨迹 topic
- `imu_topic`：IMU topic
- `lidar_status_topic`：雷达状态文本 topic，默认空；可设置为 `std_msgs/msg/String`
- `max_points_per_cloud`：单帧点云最大采样点数，默认 `0`，表示不在桥接端采样
- `min_cloud_interval_sec`：非地图点云最小发送间隔，launch 默认 `0.15`
- `min_telemetry_interval_sec`：状态/位姿/IMU 最小发送间隔，默认 `0.1`
- `path_max_points`：轨迹最大下发点数，默认 `5000`
- `map_history_root`：历史地图根目录，默认 `web_mapping/maps`
- `map_history_limit`：历史地图列表最大数量，默认 `20`

示例：

```bash
ros2 launch web_mapping web_mapping.launch.py \
  raw_cloud_topic:=/points_raw \
  optimized_cloud_topic:=/current_cloud \
  map_cloud_topic:=/global_map \
  pose_topic:=/pose
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

当前版本已经提供 `mapping_manager` 壳子和前端建图卡片，但默认控制接口不会真正启动或停止建图。它的作用是先固定 Web 与控制层之间的接口，后续可以替换或扩展 manager backend 来接入具体建图程序。

浏览器发送：

```json
{
  "type": "mapping_command",
  "command": "start",
  "session_name": "demo",
  "save_directory": ""
}
```

界面里的“地图名称”对应协议里的 `session_name`。`save_directory` 保留给后续真实后端使用，当前界面不向用户暴露保存路径，默认交给后端配置决定。

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

后端会在普通 `status` 消息中附带 `mapping` 字段，也会在命令后返回 `mapping_command_result` 并广播 `mapping_status`。真实接入时建议让 backend 负责进程生命周期、保存调用和错误信息归一化，Web 前端保持只消费状态机。

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
