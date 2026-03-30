from typer import Typer

from admin_helper import __title__
from admin_helper.logger import logger
from admin_helper.settings import settings
from admin_helper.console import console

cli_app = Typer()


@cli_app.command(name="settings", help=f"Show the current settings")
def settings_command() -> None:
    console.rule("Settings", style="bold blue")
    console.print(settings.model_dump_json(indent=4))


@cli_app.command(name="daemon", help=f"Start the {__title__} Daemon")
def supervisor_command() -> None:
    from admin_helper.helper import render_supervisord_conf, start_supervisor

    console.rule(f"{__title__} Daemon", style="bold blue")
    logger.debug(f"Starting {__title__} Daemon ...")

    # rendering supervisord config
    config_file = render_supervisord_conf()

    # starting supervisord
    start_supervisor(config_file=config_file)
