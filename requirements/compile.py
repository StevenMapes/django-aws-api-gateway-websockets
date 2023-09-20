#!/usr/bin/env python
import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    py_version = sys.version_info[:3]

    os.chdir(Path(__file__).parent)
    os.environ["CUSTOM_COMPILE_COMMAND"] = "requirements/compile.py"
    os.environ["PIP_REQUIRE_VIRTUALENV"] = "0"
    common_args = [
        "-m",
        "piptools",
        "compile",
        "--generate-hashes",
        "--allow-unsafe",
    ] + sys.argv[1:]

    if (3, 8, 0) <= py_version < (3, 10, 0):
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=3.2,<3.3",
                "-o",
                "py38-django32.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.0,<4.1",
                "-o",
                "py38-django40.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.1,<4.2",
                "-o",
                "py38-django41.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=3.2,<3.3",
                "-o",
                "py39-django32.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.0,<4.1",
                "-o",
                "py39-django40.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.1,<4.2",
                "-o",
                "py39-django41.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.0,<4.1",
                "-o",
                "py310-django40.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.1,<4.2",
                "-o",
                "py310-django41.txt",
            ],
            check=True,
            capture_output=True,
        )
    if (3, 11, 0) <= py_version < (3, 12, 0):
        subprocess.run(
            [
                "python3.11",
                *common_args,
                "-P",
                "Django>=4.1.8,<4.2",
                "-o",
                "py311-django41.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.2,<5",
                "-o",
                "py310-django42.txt",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django>=4.2,<5",
                "-o",
                "py311-django42.txt",
            ],
            check=True,
            capture_output=True,
        )
        # Django 5 required Python 3.10+
        subprocess.run(
            [
                "python",
                *common_args,
                "-P",
                "Django==5.0a1",
                "-o",
                "py311-django50.txt",
            ],
            check=True,
            capture_output=True,
        )
    # Use SED to remove the --extra-index-url lines from every file
    sed_args = ["sed", "-i", "-e", "s/--extra-index-url .*$//g"]
    [
        subprocess.run([*sed_args, x.name])
        for x in Path(".").iterdir()
        if not x.is_dir() and ".txt" in x.name
    ]

    # Remove backports from Python3.10 and Python 3.11
    sed_args = ["sed", "-i", "-e", "/backports/,/via django/d"]
    [
        subprocess.run([*sed_args, x.name])
        for x in Path(".").iterdir()
        if not x.is_dir() and ("py310-" in x.name or "py311-" in x.name)
    ]
