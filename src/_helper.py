import getpass
import logging
import os
import platform
import shutil

import tarfile
import zipfile
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from wiederverwendbar.functions.download_file import simple_download_file


from admin_helper.logger import logger
from admin_helper.settings import settings, Settings




# def download_binary(name: str,
#                     sub_settings: Settings.Supervisor | Settings.Traefik) -> None:
#     logger.debug(f"Downloading {name} binary from '{sub_settings.download_url}' ...")
#
#     # download binary
#     settings.temp_directory.mkdir(parents=True, exist_ok=True)
#     if not simple_download_file(download_url=sub_settings.download_url,
#                                 local_file=sub_settings.temp_archive_file_path,
#                                 overwrite=True):
#         raise RuntimeError(f"Failed to download {name} binary from '{sub_settings.download_url}'")
#
#     # extract binary
#     logger.debug(f"Extracting {name} binary from '{sub_settings.temp_archive_file_path}' ...")
#     if ".tar" in sub_settings.temp_archive_file_path.suffixes and ".gz" in sub_settings.temp_archive_file_path.suffixes:
#         # noinspection PyTypeChecker
#         with tarfile.open(sub_settings.temp_archive_file_path, "r:gz") as archive:
#             archive.extractall(path=settings.temp_directory)
#     elif ".zip" in sub_settings.temp_archive_file_path.suffixes:
#         with zipfile.ZipFile(sub_settings.temp_archive_file_path, "r") as archive:
#             archive.extractall(settings.temp_directory)
#     else:
#         raise RuntimeError(f"Unsupported archive type: {', '.join([s for s in sub_settings.temp_archive_file_path.suffixes])}")
#     if not sub_settings.temp_binary_file_path.is_file():
#         raise RuntimeError(f"Binary not found at '{sub_settings.temp_binary_file_path}' after extraction")
#     logger.debug(f"{name} binary extracted successfully.")
#
#     # move binary to binary directory
#     logger.debug(f"Moving {name} binary to '{sub_settings.binary_file_path}' ...")
#     settings.binary_directory.mkdir(parents=True, exist_ok=True)
#     shutil.move(str(sub_settings.temp_binary_file_path), str(sub_settings.binary_file_path))
#     sub_settings.binary_file_path.chmod(0o755)
#
#     logger.debug(f"{name} binary downloaded and moved successfully to '{sub_settings.binary_file_path}'.")

