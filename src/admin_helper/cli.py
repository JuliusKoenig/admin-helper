import typer

from admin_helper import (__title__,
                          AdminHelper,
                          RenderResult,
                          TestResult,
                          AdminHelperSettings, AdminHelperConsole)

cli_app = typer.Typer()


@cli_app.command(name="settings", help=f"Show the {__title__} settings")
def settings_command() -> None:
    AdminHelperConsole.rule("Settings", style="bold blue")
    AdminHelperConsole.print(AdminHelperSettings.model_dump_json(indent=4))


@cli_app.command(name="start", help=f"Start the {__title__} Supervisor")
def supervisor_start_command() -> None:

    AdminHelperConsole.rule(f"{__title__} Supervisor", style="bold blue")

    AdminHelper.start()

def print_result(title: str,
                 result: RenderResult | TestResult) -> bool:
    AdminHelperConsole.rule(f"{__title__} {title}", style="bold blue")
    for i, (r, obj, msg) in enumerate(result):
        AdminHelperConsole.print(f"{i+1}. {f'✅ ([green]{msg}[/green])' if r else f'❌ ([red]{msg}[/red])'}\t-> {obj}")
    if any(r for r, obj, message in result):
        AdminHelperConsole.rule(f"{__title__} {title} Passed", style="bold green")
    else:
        AdminHelperConsole.rule(f"{__title__} {title} Failed", style="bold red")
    return any(r for r, obj, msg in result)


@cli_app.command(name="test", help=f"Check the {__title__} configuration")
def test_command() -> None:
    raise typer.Exit(0 if print_result(title="Configuration Test", result=AdminHelper.test()) else 1)


@cli_app.command(name="render", help=f"Render the {__title__} configuration")
def render_command() -> None:
    raise typer.Exit(0 if print_result(title="Rendering Configuration", result=AdminHelper.render()) else 1)

