import logging
import os
import platform
from pathlib import Path
from typing import Any


def as_path(path: str | Path) -> Path:
    return Path(path) if isinstance(path, str) else path


def raise_is_not_file(path: str | Path) -> str | Path:
    if not Path(path).is_file():
        raise FileNotFoundError(f"'{path}' is not a file")
    return path


def raise_is_not_dir(path: str | Path) -> str | Path:
    if not Path(path).is_dir():
        raise NotADirectoryError(f"'{path}' is not a directory")
    return path


def as_str(path: str | Path) -> str:
    """
    Format the Path as Unix Path

    :param path: Path
    :return: Formatted Path
    """

    if isinstance(path, Path):
        path = str(path)
    return path.replace("\\", "/") if platform.system() == "Windows" else path


def ensure_path(path: str | Path,
                dry_run: bool = False,
                logger: logging.Logger | Any | None = None) -> str | Path:
    """
    Ensure the Path exists. If not, create it.

    :param logger:
    :param path: Path
    :param dry_run: Dry run
    :return: Path
    """


    if not Path(path).is_dir():
        if dry_run:
            if logger:
                logger.debug(f"[DRY-RUN] Creating directory '{Path(path)}' ...")
        else:
            if logger:
                logger.debug(f"Creating directory '{Path(path)}' ...")
            Path(path).mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent_path(path: str | Path,
                       dry_run: bool = False,
                       logger: logging.Logger | Any | None = None) -> Path:
    ensure_path(Path(path).parent, dry_run, logger)
    return Path(path)


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
