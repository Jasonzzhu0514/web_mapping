from pathlib import Path

from setuptools import find_packages, setup


package_name = "web_mapping"


def data_files_for_tree(root: str):
    entries = []
    root_path = Path(root)
    for path in root_path.rglob("*"):
        if path.is_file():
            destination = Path("share") / package_name / path.parent
            entries.append((str(destination), [str(path)]))
    return entries


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["tests"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml", "README.md"]),
        (f"share/{package_name}/launch", ["launch/web_mapping.launch.py"]),
        *data_files_for_tree("web_mapping/web"),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="chu",
    maintainer_email="chu@example.com",
    description="Standalone browser-based ROS 2 realtime point cloud mapping viewer.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "web_mapping_bridge = web_mapping.bridge:main",
        ],
    },
)
