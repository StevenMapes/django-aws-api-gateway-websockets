#!/usr/bin/env python
import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    os.environ["CUSTOM_COMPILE_COMMAND"] = "requirements/compile.py"
    common_args = [
        "-m",
        "piptools",
        "compile",
        "--generate-hashes",
        "--allow-unsafe",
    ] + sys.argv[1:]
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=2.2,<2.3",
            "-P",
            "typing-extensions==3.10.0.2",
            "-o",
            "py36-django22.txt",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=2.2,<2.3",
            "-o",
            "py38-django22.txt",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=3.0a1,<3.1",
            "-o",
            "py38-django30.txt",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=3.1a1,<3.2",
            "-o",
            "py38-django31.txt",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=3.2a1,<3.3",
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
            "Django>=4.0a1,<4.1",
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
            "Django>=2.2,<2.3",
            "-o",
            "py39-django22.txt",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=3.0a1,<3.1",
            "-o",
            "py39-django30.txt",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=3.1a1,<3.2",
            "-o",
            "py39-django31.txt",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "python",
            *common_args,
            "-P",
            "Django>=3.2a1,<3.3",
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
            "Django>=4.0a1,<4.1",
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
            "Django>=4.0a1,<4.1",
            "-o",
            "py310-django40.txt",
        ],
        check=True,
        capture_output=True,
    )

    # Use SED to remove the --extra-index-url lines from every file
    sed_args = ["sed", "-i", "-e", 's/--extra-index-url .*$//g']
    [subprocess.run([*sed_args, x.name]) for x in Path('.').iterdir() if not x.is_dir() and '.txt' in x.name]

    # Remove backports from Python3.10
    sed_args = ["sed", "-i", "-e", '/backports/,/via django/d']
    [subprocess.run([*sed_args, x.name]) for x in Path('.').iterdir() if not x.is_dir() and 'py310-' in x.name]
