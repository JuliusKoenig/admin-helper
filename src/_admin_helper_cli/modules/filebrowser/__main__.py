from pathlib import Path
import time

import typer

from src._admin_helper_cli.logger import get_logger
from src._admin_helper_cli.settings import settings
from src._admin_helper_cli.helper import render, run_cmd
from src._admin_helper_cli.modules.filebrowser.settings import file_browser_settings, FileBrowserModuleSettings


def main(module_name: str):
    module = settings.get_module(module_name)
    logger = get_logger(module.logger)

    if module is None:
        logger.error(f"Module '{module_name}' not found in settings.")
        raise typer.Exit(1)
    if not isinstance(module, FileBrowserModuleSettings):
        logger.error(f"Module '{module_name}' is not a File Browser module.")
        raise typer.Exit(1)

    config_path = file_browser_settings.path / "config"
    template_path = Path(__file__).parent / "templates"
    
    # delete filebrowser.db if exist
    db_path = file_browser_settings.path / "filebrowser.db"
    if db_path.is_file():
        logger.debug(f"Deleting existing File Browser database at {db_path}")
        db_path.unlink()

    # render the supervisor configuration files
    kwargs = dict(
        settings=settings,
        module=module,
        file_browser_settings=file_browser_settings,
        config_path=config_path,
        template_path=template_path,
    )

    logger.debug("Starting Supervisor configuration rendering")
    render(
        logger=logger,
        src=template_path,
        dst=config_path,
        cleanup=True,
        **kwargs)
    
    # import the configuration file
    logger.info("Importing File Browser configuration ...")
    run_cmd(logger=logger,
            cwd=file_browser_settings.path,
            args=[
                str(file_browser_settings.binary_path),
                "config",
                "import",
                str(config_path / "settings.json")
            ])

    # start the File Browser process
    logger.info("Starting File Browser ...")
    run_cmd(logger=logger,
            cwd=file_browser_settings.path,
            args=[
                str(file_browser_settings.binary_path)
                ])
