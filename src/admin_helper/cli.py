import typer

from admin_helper import __title__
from admin_helper.settings import settings
from admin_helper.console import console

cli_app = typer.Typer()


@cli_app.command(name="settings", help=f"Show the {__title__} settings")
def settings_command() -> None:
    console.rule("Settings", style="bold blue")
    console.print(settings.model_dump_json(indent=4))


@cli_app.command(name="start", help=f"Start the {__title__} Supervisor")
def supervisor_start_command() -> None:
    from admin_helper import AdminHelper

    console.rule(f"{__title__} Supervisor", style="bold blue")

    AdminHelper.start()


@cli_app.command(name="test", help=f"Check the {__title__} configuration")
def test_command() -> None:
    from admin_helper import AdminHelper

    console.rule(f"{__title__} Configuration Test", style="bold blue")
    result = AdminHelper.test()
    for render_file_name, result_and_message in result.items():
        console.print(f"[slate_blue1]File[/slate_blue1]: {render_file_name} -> {result_and_message[1]}")
    if any(result_and_message[0] for result_and_message in result.values()):
        console.rule("Configuration Test Passed", style="bold green")
    else:
        console.rule("Configuration Test Failed", style="bold red")

    raise typer.Exit(0 if any(result_and_message[0] for result_and_message in result.values()) else 1)


@cli_app.command(name="render", help=f"Render the {__title__} configuration")
def render_command() -> None:
    from admin_helper import AdminHelper

    console.rule(f"{__title__} Rendering", style="bold blue")
    result = AdminHelper.render()
    for render_file_name, result_and_message in result.items():
        console.print(f"[slate_blue1]File[/slate_blue1]: {render_file_name} -> {result_and_message[1]}")
    if any(result_and_message[0] for result_and_message in result.values()):
        console.rule(f"{__title__} Rendering succeeded", style="bold green")
    else:
        console.rule(f"{__title__} Rendering failed", style="bold red")

    raise typer.Exit(0 if any(result_and_message[0] for result_and_message in result.values()) else 1)
