import os
import platform
import shutil
import signal
import subprocess
import tarfile
from pathlib import Path
from typing import Union, Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from passlib.apache import HtpasswdFile
from wiederverwendbar.functions.download_file import simple_download_file

from admin_helper.logger import logger
from admin_helper.settings import settings
from admin_helper.templates import TEMPLATE_DIRECTORY_PATH


def render_file(input_file: str | Path,
                output_file: str | Path,
                overwrite: bool = False,
                environment_options: dict[str, Any] | None = None,
                **data) -> None:
    input_file = Path(input_file)
    output_file = Path(output_file)

    logger.debug(f"Rendering file from '{input_file}' to '{output_file}' ...")

    # check if input file exist
    if not input_file.is_file():
        raise FileNotFoundError(input_file)

    # check if output file already exist
    if output_file.is_file():
        if not overwrite:
            raise FileExistsError(output_file)
        output_file.unlink()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # set default environment options
    if environment_options is None:
        environment_options = {
            "undefined": StrictUndefined,
        }

    # create file system loader
    environment_options["loader"] = FileSystemLoader(input_file.parent)

    # create environment
    logger.debug(f"Environment options: {environment_options}")
    environment = Environment(**environment_options)

    # get template
    template = environment.get_template(input_file.name)

    # render template
    logger.debug(f"Data: {data}")
    output = template.render(data)

    logger.debug(f"Rendered output: {output}")

    # write output to file
    with output_file.open(mode="w") as output_file:
        output_file.write(output)

    logger.debug(f"File '{output_file}' rendered successfully.")


def render_supervisord_conf() -> None:
    logger.debug(f"Rendering supervisord config ...")

    # render config
    render_file(input_file=TEMPLATE_DIRECTORY_PATH / "supervisord" / "supervisord.conf.j2",
                output_file=settings.supervisord.config_file_path,
                overwrite=True,
                **{"settings": settings,
                   "environment": os.environ})

    logger.debug(f"Supervisord config rendered successfully.")


def start_supervisor() -> None:
    logger.debug(f"Starting supervisor ...")

    cmd = ["supervisord",
           "-c",
           str(settings.supervisord.config_file_path),
           "-n"]

    process = subprocess.Popen(cmd, )

    try:
        process.wait()
    except KeyboardInterrupt:
        logger.debug(f"Stopping supervisor ...")
        process.send_signal(signal.SIGINT)
        process.wait()
        logger.debug(f"Supervisor stopped successfully.")


def download_traefik() -> None:
    # get os
    if platform.system() not in ["Linux", "Darwin", "Windows"]:
        raise RuntimeError(f"Unsupported operating system: {platform.system()}")
    os_name = platform.system().lower()

    # get arch
    if platform.machine() == "x86_64" or platform.machine() == "amd64":
        arch = "amd64"
    elif platform.machine() == "arm64" or platform.machine() == "aarch64":
        arch = "arm64"
    else:
        raise RuntimeError(f"Unsupported architecture: {platform.machine()}")

    # format download url
    download_url = settings.traefik.download_url.format(
        version=settings.traefik.version,
        os=os_name,
        arch=arch,
    )

    logger.debug(f"Downloading Traefik binary from '{download_url}' ...\n"
                 f"Version: {settings.traefik.version}\n"
                 f"OS: {os_name}\n"
                 f"Architecture: {arch}\n")

    # download binary
    settings.temp_directory.mkdir(parents=True, exist_ok=True)
    if not simple_download_file(download_url=download_url,
                                local_file=settings.temp_directory / "traefik.tar.gz",
                                overwrite=True):
        raise RuntimeError(f"Failed to download Traefik binary from '{download_url}'")

    # extract binary
    logger.debug(f"Extracting Traefik binary to '{settings.temp_directory}' ...")
    with tarfile.open(settings.temp_directory / "traefik.tar.gz") as tar:
        tar.extractall(path=settings.temp_directory)
    if not settings.temp_directory / "traefik":
        raise RuntimeError(f"Binary not found at '{settings.temp_directory}/traefik'")
    logger.debug(f"Traefik binary extracted successfully.")

    # move binary to binary directory
    logger.debug(f"Moving Traefik binary to '{settings.traefik.binary_file_path}' ...")
    settings.binary_directory.mkdir(parents=True, exist_ok=True)
    shutil.move(str(settings.temp_directory / "traefik"), str(settings.traefik.binary_file_path))
    settings.traefik.binary_file_path.chmod(0o755)

    logger.debug(f"Traefik binary downloaded and moved successfully to '{settings.traefik.binary_file_path}'.")


def render_traefik_conf() -> None:
    logger.debug(f"Rendering traefik config ...")

    # render static config
    logger.debug(f"Rendering static config to '{settings.traefik.config_file_path}' ...")
    render_file(input_file=TEMPLATE_DIRECTORY_PATH / "traefik" / "traefik.yaml.j2",
                output_file=settings.traefik.config_file_path,
                overwrite=True,
                **{"settings": settings,
                   "environment": os.environ})

    # render dynamic config
    logger.debug(f"Rendering dynamic config to '{settings.traefik.dynamic_file_path}' ...")
    render_file(input_file=TEMPLATE_DIRECTORY_PATH / "traefik" / "dynamic.yaml.j2",
                output_file=settings.traefik.dynamic_file_path,
                overwrite=True,
                **{"settings": settings,
                   "environment": os.environ})

    # generate .htpasswd
    logger.debug(f"Generating .htpasswd at '{settings.traefik.htpasswd_file_path}' ...")
    ht = HtpasswdFile(str(settings.traefik.htpasswd_file_path), new=True)
    for username, user in settings.users.items():
        logger.debug(f"Adding user {username} to .htpasswd")
        ht.set_password(username, user.password)
    ht.save()

    logger.debug(f"Traefik config rendered successfully.")


def start_traefik() -> None:
    logger.debug(f"Starting traefik ...")

    cmd = [str(settings.traefik.binary_file_path),
           "--configFile",
           str(settings.traefik.config_file_path)]

    process = subprocess.Popen(cmd)

    try:
        process.wait()
    except KeyboardInterrupt:
        logger.debug(f"Stopping traefik ...")
        process.send_signal(signal.SIGINT)
        process.wait()
        logger.debug(f"Traefik stopped successfully.")
