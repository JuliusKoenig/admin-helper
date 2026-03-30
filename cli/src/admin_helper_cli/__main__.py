from typer import Typer


from admin_helper_cli.settings import settings
from admin_helper_cli.console import console

cli_app = Typer()


@cli_app.command(name="settings", help=f"Show the current settings")
def settings_command() -> None:
    console.rule("Settings", style="bold blue")
    console.print(settings.model_dump_json(indent=4))


@cli_app.command(name="daemon", help=f"ToDo")
def daemon_command() -> None:
    console.rule("Daemon", style="bold blue")
    from admin_helper_cli.daemon import Daemon
    Daemon()


services_cli_app = Typer()


@services_cli_app.command(name="traefik", help=f"ToDo")
def traefik_command() -> None:
    console.rule("Traefik", style="bold blue")
    from admin_helper_cli.modules.traefik import main
    
@services_cli_app.command(name="dashboard", help=f"ToDo")
def dashboard_command() -> None:
    console.rule("Dashboard", style="bold blue")
    from admin_helper_cli.modules.dashboard import main


cli_app.add_typer(services_cli_app, name="services")


if __name__ in {"__main__", "__mp_main__"}:
    cli_app()
