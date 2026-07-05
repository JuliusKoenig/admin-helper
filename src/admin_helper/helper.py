import getpass
import logging
import os
import platform
import re
import shutil
import signal
import subprocess
import tarfile
import zipfile
from logging import Logger
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from passlib.apache import HtpasswdFile
from wiederverwendbar.functions.download_file import simple_download_file

from admin_helper.log_file_streamer import LogFileStreamer
from admin_helper.logger import logger
from admin_helper.settings import settings, Settings
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

    # set filter
    environment.filters["unix_path"] = lambda path: str(path).replace("\\", "/") if platform.system() == "Windows" else str(path)

    # get template
    template = environment.get_template(input_file.name)

    data["settings"] = settings
    data["environment"] = os.environ
    data["user"] = getpass.getuser()
    data["group"] = os.getgid()
    data["pwd"] = Path.cwd()

    # render template
    logger.debug(f"Data: {data}")
    output = template.render(data)

    logger.debug(f"Rendered output: {output}")

    # write output to file
    with output_file.open(mode="w") as output_file:
        output_file.write(output)

    logger.debug(f"File '{output_file}' rendered successfully.")


def download_binary(name: str,
                    sub_settings: Settings.SupervisorD | Settings.Traefik) -> None:
    logger.debug(f"Downloading {name} binary from '{sub_settings.download_url}' ...")

    # download binary
    settings.temp_directory.mkdir(parents=True, exist_ok=True)
    if not simple_download_file(download_url=sub_settings.download_url,
                                local_file=sub_settings.temp_archive_file_path,
                                overwrite=True):
        raise RuntimeError(f"Failed to download {name} binary from '{sub_settings.download_url}'")

    # extract binary
    logger.debug(f"Extracting {name} binary from '{sub_settings.temp_archive_file_path}' ...")
    if ".tar" in sub_settings.temp_archive_file_path.suffixes and ".gz" in sub_settings.temp_archive_file_path.suffixes:
        # noinspection PyTypeChecker
        with tarfile.open(sub_settings.temp_archive_file_path, "r:gz") as archive:
            archive.extractall(path=settings.temp_directory)
    elif ".zip" in sub_settings.temp_archive_file_path.suffixes:
        with zipfile.ZipFile(sub_settings.temp_archive_file_path, "r") as archive:
            archive.extractall(settings.temp_directory)
    else:
        raise RuntimeError(f"Unsupported archive type: {', '.join([s for s in sub_settings.temp_archive_file_path.suffixes])}")
    if not sub_settings.temp_binary_file_path.is_file():
        raise RuntimeError(f"Binary not found at '{sub_settings.temp_binary_file_path}' after extraction")
    logger.debug(f"{name} binary extracted successfully.")

    # move binary to binary directory
    logger.debug(f"Moving {name} binary to '{sub_settings.binary_file_path}' ...")
    settings.binary_directory.mkdir(parents=True, exist_ok=True)
    shutil.move(str(sub_settings.temp_binary_file_path), str(sub_settings.binary_file_path))
    sub_settings.binary_file_path.chmod(0o755)

    logger.debug(f"{name} binary downloaded and moved successfully to '{sub_settings.binary_file_path}'.")


def render_supervisord_conf() -> None:
    logger.debug(f"Rendering supervisord config ...")

    # render config
    render_file(input_file=TEMPLATE_DIRECTORY_PATH / "supervisord" / "supervisord.conf.j2",
                output_file=settings.supervisord.config_file_path,
                overwrite=True)

    logger.debug(f"Supervisord config rendered successfully.")


def start_supervisor() -> None:
    logger.debug(f"Starting supervisor ...")

    # ensure pid file parent directory exists
    settings.supervisord.pid_file_path.parent.mkdir(parents=True, exist_ok=True)

    # ensure log file parent directory exist
    settings.supervisord.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # ensure child log directory exists
    settings.supervisord.child_log_directory_path.mkdir(parents=True, exist_ok=True)

    # cleanup log file
    if settings.supervisord.log_file_path.is_file():
        settings.supervisord.log_file_path.unlink()

    # cmd
    cmd = ["supervisord",
           "-c",
           str(settings.supervisord.config_file_path),
           "-n"]

    # starting supervisord
    process = subprocess.Popen(cmd,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)

    # create logger
    supervisord_main_logger = Logger(name=f"{logger.name}.supervisord.main")
    supervisord_main_logger.parent = logger

    # start file streamer
    log_file_streamer = LogFileStreamer(logger=supervisord_main_logger,
                                        log_file_path=settings.supervisord.log_file_path,
                                        pattern=re.compile(
                                            r"^(?P<timestamp>\d{4}-\d{2}-\d{2} "
                                            r"\d{2}:\d{2}:\d{2},\d{3}) "
                                            r"(?P<level>[A-Z]+) "
                                            r"(?P<message>.*)$"
                                        ),
                                        timestamp_format="%Y-%m-%d %H:%M:%S,%f",
                                        fallback_function_name="supervisord-main",
                                        filter_messages=["Server 'inet_http_server' running without any HTTP authentication checking"])
    log_file_streamer.start()

    # wait for process
    try:
        process.wait()
    except KeyboardInterrupt:
        logger.debug(f"Stopping supervisor ...")
        process.send_signal(signal.SIGINT)
        process.wait()
        logger.debug(f"Supervisor stopped successfully.")

    # clean up pid file if exist
    if settings.supervisord.pid_file_path.is_file():
        settings.supervisord.pid_file_path.unlink()


def render_traefik_conf() -> None:
    logger.debug(f"Rendering traefik config ...")

    # render static config
    logger.debug(f"Rendering static config to '{settings.traefik.config_file_path}' ...")
    render_file(input_file=TEMPLATE_DIRECTORY_PATH / "traefik" / "traefik.yaml.j2",
                output_file=settings.traefik.config_file_path,
                overwrite=True)

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

    # ensure log file parent directory exist
    settings.traefik.log_file_path.parent.mkdir(parents=True, exist_ok=True)
    settings.traefik.access_log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # cleanup log file
    if settings.traefik.log_file_path.is_file():
        settings.traefik.log_file_path.unlink()
    if settings.traefik.access_log_file_path.is_file():
        settings.traefik.access_log_file_path.unlink()

    # cmd
    cmd = [str(settings.traefik.binary_file_path),
           "--configFile",
           str(settings.traefik.config_file_path)]

    # starting traefik
    process = subprocess.Popen(cmd,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)

    # create logger
    traefik_main_logger = Logger(name=f"{logger.name}.traefik.main")
    traefik_main_logger.parent = logger
    traefik_access_logger = Logger(name=f"{logger.name}.traefik.access")
    traefik_access_logger.parent = logger

    # start file streamer
    log_file_streamer = LogFileStreamer(logger=traefik_main_logger,
                                        log_file_path=settings.traefik.log_file_path,
                                        pattern=re.compile(
                                            r"^(?P<timestamp>\S+)\s+"
                                            r"(?P<level>[A-Z]+)\s+"
                                            r"(?P<function_name>github\.com/\S+:\d+)\s+>\s*"
                                            r"(?P<message>.*)$"
                                        ))
    access_log_file_streamer = LogFileStreamer(logger=traefik_access_logger,
                                               log_file_path=settings.traefik.access_log_file_path,
                                               pattern=re.compile(
                                                   r'^(?P<client_ip>\S+) '
                                                   r'(?P<ident>\S+) '
                                                   r'(?P<user>\S+) '
                                                   r'\[(?P<timestamp>[^\]]+)\] '
                                                   r'"(?P<method>\S+) '
                                                   r'(?P<path>\S+) '
                                                   r'(?P<protocol>[^"]+)" '
                                                   r'(?P<status>\d{3}) '
                                                   r'(?P<size>\d+) '
                                                   r'"(?P<referer>[^"]*)" '
                                                   r'"(?P<user_agent>[^"]*)" '
                                                   r'(?P<request_count>\d+) '
                                                   r'"(?P<router>[^"]*)" '
                                                   r'"(?P<service>[^"]*)" '
                                                   r'(?P<duration>\S+)$'
                                               ),
                                               fixed_level=logging.INFO,
                                               message_format="{method} {path} HTTP {status} service={service} duration={duration}",
                                               timestamp_format="%d/%b/%Y:%H:%M:%S %z",
                                               fallback_function_name="traefik-access-log")
    log_file_streamer.start()
    access_log_file_streamer.start()

    # wait for process
    try:
        process.wait()
    except KeyboardInterrupt:
        logger.debug(f"Stopping traefik ...")
        process.send_signal(signal.SIGINT)
        process.wait()
        logger.debug(f"Traefik stopped successfully.")
        log_file_streamer.shutdown()
