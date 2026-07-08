import typer

from admin_helper import __title__
from admin_helper.settings import settings
from admin_helper.console import console

cli_app = typer.Typer()
supervisor_cli_app = typer.Typer(name="supervisor", help="Supervisor Commands")


@supervisor_cli_app.command(name="settings", help=f"Show the {__title__} Supervisor settings")
def supervisor_settings_command() -> None:
    console.rule("Settings", style="bold blue")
    console.print(settings.supervisor.model_dump_json(indent=4))


@supervisor_cli_app.command(name="start", help=f"Start the {__title__} Supervisor")
def supervisor_supervisor_command() -> None:
    from admin_helper.supervisor import SupervisorService

    console.rule(f"{__title__} Supervisor", style="bold blue")

    SupervisorService.start()

@supervisor_cli_app.command(name="conftest", help=f"Check the {__title__} Supervisor configuration")
def supervisor_conftest_command() -> None:
    from admin_helper.supervisor import SupervisorService

    console.rule(f"Supervisor Configuration Test", style="bold blue")
    result = SupervisorService.test()
    for render_file_name, result_and_message in result.items():
        console.print(f"[slate_blue1]File[/slate_blue1]: {render_file_name} -> {result_and_message[1]}")
    if any(result_and_message[0] for result_and_message in result.values()):
        console.rule("Supervisor Configuration Test Passed", style="bold green")
    else:
        console.rule("Supervisor Configuration Test Failed", style="bold red")

    raise typer.Exit(0 if any(result_and_message[0] for result_and_message in result.values()) else 1)


@supervisor_cli_app.command(name="render", help=f"Render the {__title__} Supervisor configuration")
def supervisor_render_command() -> None:
    from admin_helper.supervisor import SupervisorService

    console.rule(f"Supervisor Rendering", style="bold blue")
    result = SupervisorService.render()
    for render_file_name, result_and_message in result.items():
        console.print(f"[slate_blue1]File[/slate_blue1]: {render_file_name} -> {result_and_message[1]}")
    if any(result_and_message[0] for result_and_message in result.values()):
        console.rule("Supervisor Rendering succeeded", style="bold green")
    else:
        console.rule("Supervisor Rendering failed", style="bold red")

    raise typer.Exit(0 if any(result_and_message[0] for result_and_message in result.values()) else 1)



cli_app.add_typer(supervisor_cli_app)

apache_cli_app = typer.Typer(name="apache", help="Apache Commands")

@apache_cli_app.command(name="settings", help=f"Show the {__title__} Apache settings")
def apache_settings_command() -> None:
    console.rule("Settings", style="bold blue")
    console.print(settings.apache.model_dump_json(indent=4))


@apache_cli_app.command(name="conftest", help=f"Check the {__title__} Apache configuration")
def apache_conftest_command() -> None:
    from admin_helper.apache import ApacheService

    console.rule(f"Apache Configuration Test", style="bold blue")
    result = ApacheService.test()
    for render_file_name, result_and_message in result.items():
        console.print(f"[slate_blue1]File[/slate_blue1]: {render_file_name} -> {result_and_message[1]}")
    if any(result_and_message[0] for result_and_message in result.values()):
        console.rule("Apache Configuration Test Passed", style="bold green")
    else:
        console.rule("Apache Configuration Test Failed", style="bold red")

    raise typer.Exit(0 if any(result_and_message[0] for result_and_message in result.values()) else 1)


@apache_cli_app.command(name="render", help=f"Render the {__title__} Apache configuration")
def apache_render_command() -> None:
    from admin_helper.apache import ApacheService

    console.rule(f"Apache Rendering", style="bold blue")
    result = ApacheService.render()
    for render_file_name, result_and_message in result.items():
        console.print(f"[slate_blue1]File[/slate_blue1]: {render_file_name} -> {result_and_message[1]}")
    if any(result_and_message[0] for result_and_message in result.values()):
        console.rule("Apache Rendering succeeded", style="bold green")
    else:
        console.rule("Apache Rendering failed", style="bold red")

    raise typer.Exit(0 if any(result_and_message[0] for result_and_message in result.values()) else 1)

cli_app.add_typer(apache_cli_app)
