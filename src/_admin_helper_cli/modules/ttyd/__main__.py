import subprocess
import sys
import time

from src._admin_helper_cli.helper import run_cmd
import typer

from src._admin_helper_cli.logger import get_logger
from src._admin_helper_cli.settings import settings
from src._admin_helper_cli.console import console
from src._admin_helper_cli.modules.ttyd.settings import TtydModuleSettings, ttyd_settings

def main(module_name: str):
    module = settings.get_module(module_name)
    logger = get_logger(module.logger)
    
    if module is None:
        logger.error(f"Module '{module_name}' not found in settings.")
        raise typer.Exit(1)
    if not isinstance(module, TtydModuleSettings):
        logger.error(f"Module '{module_name}' is not a Ttyd module.")
        raise typer.Exit(1)  
         
    logger.info("Starting Ttyd ...")
    run_cmd(logger=logger, 
                        cwd=ttyd_settings.path,
                        args=[
        str(ttyd_settings.binary_path),
        "-i",
        str(module.host),
        "-p",
        str(module.port),
        "-b",
        str(module.path),
        "-W",
        module.shell,
        "-e"
    ])