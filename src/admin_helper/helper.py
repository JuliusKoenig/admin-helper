import os
import signal
import subprocess
from pathlib import Path
from typing import Union, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape, StrictUndefined

from admin_helper.logger import logger
from admin_helper.settings import settings
from admin_helper.templates import TEMPLATE_DIRECTORY_PATH

TreeObject = dict[str, Union["TreeObject", Union[str, Path]]]


def render_file(input_file: Union[str, Path],
                output_file: Union[str, Path],
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


def render_filetree(output: Path | str,
                    tree: TreeObject,
                    overwrite: bool = False,
                    environment_options: dict[str, Any] | None = None,
                    **data) -> None:
    logger.debug(f"Rendering filetree to '{output}' ...")

    output = Path(output)

    # create directory
    output.mkdir(parents=True, exist_ok=True)

    for key, value in tree.items():
        if isinstance(value, dict):
            render_filetree(output=output / key,
                            tree=value,
                            overwrite=overwrite,
                            environment_options=environment_options,
                            **data)
        else:
            render_file(input_file=value,
                        output_file=output / key,
                        overwrite=overwrite,
                        environment_options=environment_options,
                        **data)

    logger.debug(f"Filetree '{output}' rendered successfully.")


def render_supervisord_conf() -> Path:
    logger.debug(f"Rendering supervisord config ...")

    render_filetree(output=settings.config_directory,
                    tree={
                        settings.supervisord.config_file_name: TEMPLATE_DIRECTORY_PATH / "supervisord" / "supervisord.conf.j2",
                    },
                    overwrite=True,
                    **{"settings": settings,
                       "environment": os.environ})

    logger.debug(f"Supervisord config rendered successfully.")

    return settings.supervisord.config_file_path


def start_supervisor(config_file: Path) -> None:
    logger.debug(f"Starting supervisor ...")

    cmd = ["supervisord",
           "-c",
           str(config_file),
           "-n"]

    process = subprocess.Popen(cmd,)

    try:
        process.wait()
    except KeyboardInterrupt:
        logger.debug(f"Stopping supervisor ...")
        process.send_signal(signal.SIGINT)
        process.wait()
        logger.debug(f"Supervisor stopped successfully.")
