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


@cli_app.command(name="supervisor", help=f"Start the {__title__} Supervisor")
def supervisor_command() -> None:
    from admin_helper.supervisor import SupervisorService

    console.rule(f"{__title__} Supervisor", style="bold blue")
    logger.debug(f"Starting {__title__} Daemon ...")

    SupervisorService.start()
