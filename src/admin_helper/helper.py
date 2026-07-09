import os
from pathlib import Path


def is_running_in_docker() -> bool:
    """
    Detect if running inside docker container
    :return: True or False
    """

    # Environment var
    if os.getenv("RUNNING_IN_DOCKER") == "1":
        return True

    # Docker
    if Path("/.dockerenv").exists():
        return True

    # Linux cgroups
    cgroup = Path("/proc/1/cgroup")
    if cgroup.exists():
        text = cgroup.read_text(errors="ignore")
        if any(x in text for x in ("docker",
                                   "containerd",
                                   "kubepods",
                                   "podman",
                                   "cri-o")):
            return True

    return False
