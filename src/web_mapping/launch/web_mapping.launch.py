from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from web_mapping.protocol import DEFAULT_MAP_HISTORY_ROOT, WEB_MAPPING_TOPICS


def generate_launch_description():
    host = LaunchConfiguration("host")
    port = LaunchConfiguration("port")
    raw_cloud_topic = LaunchConfiguration("raw_cloud_topic")
    livox_custom_topic = LaunchConfiguration("livox_custom_topic")
    optimized_cloud_topic = LaunchConfiguration("optimized_cloud_topic")
    map_cloud_topic = LaunchConfiguration("map_cloud_topic")
    pose_topic = LaunchConfiguration("pose_topic")
    raw_path_topic = LaunchConfiguration("raw_path_topic")
    optimized_path_topic = LaunchConfiguration("optimized_path_topic")
    imu_topic = LaunchConfiguration("imu_topic")
    lidar_status_topic = LaunchConfiguration("lidar_status_topic")
    mapping_command_topic = LaunchConfiguration("mapping_command_topic")
    mapping_status_topic = LaunchConfiguration("mapping_status_topic")
    use_broker_backend = LaunchConfiguration("use_broker_backend")
    max_points_per_cloud = LaunchConfiguration("max_points_per_cloud")
    max_raw_points_per_cloud = LaunchConfiguration("max_raw_points_per_cloud")
    max_optimized_points_per_cloud = LaunchConfiguration("max_optimized_points_per_cloud")
    max_map_points_per_cloud = LaunchConfiguration("max_map_points_per_cloud")
    min_cloud_interval_sec = LaunchConfiguration("min_cloud_interval_sec")
    min_map_interval_sec = LaunchConfiguration("min_map_interval_sec")
    min_telemetry_interval_sec = LaunchConfiguration("min_telemetry_interval_sec")
    path_max_points = LaunchConfiguration("path_max_points")
    map_history_root = LaunchConfiguration("map_history_root")
    map_history_limit = LaunchConfiguration("map_history_limit")

    return LaunchDescription([
        DeclareLaunchArgument("host", default_value="0.0.0.0"),
        DeclareLaunchArgument("port", default_value="8765"),
        DeclareLaunchArgument("raw_cloud_topic", default_value=WEB_MAPPING_TOPICS["raw_cloud"]),
        DeclareLaunchArgument("livox_custom_topic", default_value=""),
        DeclareLaunchArgument("optimized_cloud_topic", default_value=WEB_MAPPING_TOPICS["current_frame"]),
        DeclareLaunchArgument("map_cloud_topic", default_value=WEB_MAPPING_TOPICS["global_map"]),
        DeclareLaunchArgument("pose_topic", default_value=WEB_MAPPING_TOPICS["pose"]),
        DeclareLaunchArgument("raw_path_topic", default_value=WEB_MAPPING_TOPICS["raw_path"]),
        DeclareLaunchArgument("optimized_path_topic", default_value=WEB_MAPPING_TOPICS["optimized_path"]),
        DeclareLaunchArgument("imu_topic", default_value=WEB_MAPPING_TOPICS["imu"]),
        DeclareLaunchArgument("lidar_status_topic", default_value=WEB_MAPPING_TOPICS["lidar_status"]),
        DeclareLaunchArgument("max_points_per_cloud", default_value="0"),
        DeclareLaunchArgument("max_raw_points_per_cloud", default_value="5000"),
        DeclareLaunchArgument("max_optimized_points_per_cloud", default_value="8000"),
        DeclareLaunchArgument("max_map_points_per_cloud", default_value="50000"),
        DeclareLaunchArgument("min_cloud_interval_sec", default_value="0.15"),
        DeclareLaunchArgument("min_map_interval_sec", default_value="0.5"),
        DeclareLaunchArgument("min_telemetry_interval_sec", default_value="0.1"),
        DeclareLaunchArgument("path_max_points", default_value="5000"),
        DeclareLaunchArgument("map_history_root", default_value=DEFAULT_MAP_HISTORY_ROOT),
        DeclareLaunchArgument("map_history_limit", default_value="20"),
        DeclareLaunchArgument("mapping_command_topic", default_value=WEB_MAPPING_TOPICS["mapping_command"]),
        DeclareLaunchArgument("mapping_status_topic", default_value=WEB_MAPPING_TOPICS["mapping_status"]),
        DeclareLaunchArgument("use_broker_backend", default_value="true"),
        Node(
            package="web_mapping",
            executable="web_mapping_bridge",
            name="web_mapping_bridge",
            output="screen",
            parameters=[{
                "host": host,
                "port": ParameterValue(port, value_type=int),
                "raw_cloud_topic": raw_cloud_topic,
                "livox_custom_topic": livox_custom_topic,
                "optimized_cloud_topic": optimized_cloud_topic,
                "map_cloud_topic": map_cloud_topic,
                "pose_topic": pose_topic,
                "raw_path_topic": raw_path_topic,
                "optimized_path_topic": optimized_path_topic,
                "imu_topic": imu_topic,
                "lidar_status_topic": lidar_status_topic,
                "mapping_command_topic": mapping_command_topic,
                "mapping_status_topic": mapping_status_topic,
                "use_broker_backend": ParameterValue(use_broker_backend, value_type=bool),
                "max_points_per_cloud": ParameterValue(max_points_per_cloud, value_type=int),
                "max_raw_points_per_cloud": ParameterValue(max_raw_points_per_cloud, value_type=int),
                "max_optimized_points_per_cloud": ParameterValue(max_optimized_points_per_cloud, value_type=int),
                "max_map_points_per_cloud": ParameterValue(max_map_points_per_cloud, value_type=int),
                "min_cloud_interval_sec": ParameterValue(min_cloud_interval_sec, value_type=float),
                "min_map_interval_sec": ParameterValue(min_map_interval_sec, value_type=float),
                "min_telemetry_interval_sec": ParameterValue(min_telemetry_interval_sec, value_type=float),
                "path_max_points": ParameterValue(path_max_points, value_type=int),
                "map_history_root": map_history_root,
                "map_history_limit": ParameterValue(map_history_limit, value_type=int),
            }],
        ),
    ])
