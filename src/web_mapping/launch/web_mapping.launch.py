from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


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
    max_points_per_cloud = LaunchConfiguration("max_points_per_cloud")
    min_cloud_interval_sec = LaunchConfiguration("min_cloud_interval_sec")
    min_telemetry_interval_sec = LaunchConfiguration("min_telemetry_interval_sec")
    path_max_points = LaunchConfiguration("path_max_points")

    return LaunchDescription([
        DeclareLaunchArgument("host", default_value="0.0.0.0"),
        DeclareLaunchArgument("port", default_value="8765"),
        DeclareLaunchArgument("raw_cloud_topic", default_value="cloud_registered_1"),
        DeclareLaunchArgument("livox_custom_topic", default_value="/livox/lidar"),
        DeclareLaunchArgument("optimized_cloud_topic", default_value="corrected_current_pcd"),
        DeclareLaunchArgument("map_cloud_topic", default_value="corrected_map"),
        DeclareLaunchArgument("pose_topic", default_value="pose_stamped"),
        DeclareLaunchArgument("raw_path_topic", default_value="ori_path"),
        DeclareLaunchArgument("optimized_path_topic", default_value="corrected_path"),
        DeclareLaunchArgument("imu_topic", default_value="/livox/imu"),
        DeclareLaunchArgument("lidar_status_topic", default_value=""),
        DeclareLaunchArgument("max_points_per_cloud", default_value="0"),
        DeclareLaunchArgument("min_cloud_interval_sec", default_value="0.15"),
        DeclareLaunchArgument("min_telemetry_interval_sec", default_value="0.1"),
        DeclareLaunchArgument("path_max_points", default_value="5000"),
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
                "max_points_per_cloud": ParameterValue(max_points_per_cloud, value_type=int),
                "min_cloud_interval_sec": ParameterValue(min_cloud_interval_sec, value_type=float),
                "min_telemetry_interval_sec": ParameterValue(min_telemetry_interval_sec, value_type=float),
                "path_max_points": ParameterValue(path_max_points, value_type=int),
            }],
        ),
    ])
