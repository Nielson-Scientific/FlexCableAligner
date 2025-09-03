from setuptools import setup

plugin_identifier = "flex_cable_aligner"
plugin_package = "octoprint_" + plugin_identifier
plugin_name = "OctoPrint-FlexCableAligner"
plugin_version = "0.1.0"
plugin_description = "Joystick-based jogging control for dual-carriage printers (XYZ/ABC)"
plugin_author = "Nielson Scientific"
plugin_author_email = ""
plugin_url = "https://github.com/Nielson-Scientific/FlexCableAligner"
plugin_license = "AGPLv3"

plugin_requires = [
    "octoprint>=1.8.0",
    "pygame>=2.3.0",
]

def package_data_dirs(root, subdirs):
    import os
    data = []
    for sub in subdirs:
        for dirpath, _, filenames in os.walk(os.path.join(root, sub)):
            for f in filenames:
                data.append(os.path.relpath(os.path.join(dirpath, f), root))
    return data

setup(
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    author_email=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    packages=[plugin_package],
    package_dir={plugin_package: plugin_package},
    include_package_data=True,
    install_requires=plugin_requires,
    entry_points={
        "octoprint.plugin": [f"{plugin_identifier} = {plugin_package}"]
    },
    zip_safe=False,
)
