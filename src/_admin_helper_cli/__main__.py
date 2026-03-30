from typer import Typer

from pydantic import BaseModel, Field

from src._admin_helper_cli.settings import ModuleSettings, settings
from src._admin_helper_cli.console import console
import typer

cli_app = Typer()


@cli_app.command(name="settings", help=f"Show the current settings")
def settings_command() -> None:
    console.rule("Settings", style="bold blue")
    console.print(settings.model_dump_json(indent=4))


@cli_app.command(name="supervisor", help=f"ToDo")
def supervisor_command() -> None:
    console.rule("Supervisor", style="bold blue")
    
    from src._admin_helper_cli.supervisor import supervisor
    supervisor()
    
@cli_app.command(name="traefik", help=f"ToDo")
def traefik_command() -> None:
    console.rule("Traefik", style="bold blue")
    
    from src._admin_helper_cli.traefik import traefik
    traefik()
    
@cli_app.command(name="dashboard", help=f"ToDo")
def dashboard_command() -> None:
    console.rule("Dashboard", style="bold blue")
    
    from src._admin_helper_cli.dashboard import dashboard
    dashboard()
    

module_cli_app = Typer()

@module_cli_app.command(name="list", help=f"List all enabled modules")
def list_modules_command(parameter_name: str = typer.Argument("name", help="The parameter name to show for each module")) -> None:
    for index, module in enumerate(settings.modules_enabled):
        out = str(getattr(module, parameter_name) if hasattr(module, parameter_name) else None)
        if index < len(settings.modules_enabled) - 1:
            out = f"{out}\n"
        console.print(out, end="")
        
        
def get_module_command(module_name: str, param_name: str | None = None) -> None:
    module = settings.get_module(module_name)
    if param_name is not None:
        out = str(getattr(module, param_name) if hasattr(module, param_name) else None)
    else:
        out = module.model_dump_json(indent=4)
    console.print(out)
    
def run_module_command(module_name: str) -> None:
    module = settings.get_module(module_name)
    
    #import the module's entry point and run it
    import importlib
    
    try:
        module_entry_point = importlib.import_module(module.full_entry_point.split(":")[0])
        entry_point_func = getattr(module_entry_point, module.full_entry_point.split(":")[1])
    except Exception as e:
        console.print(f"[red]Error importing module '{module.name}': {e}[/red]")
        raise typer.Exit(1)
    
    try:
        entry_point_func(module_name)
    except Exception as e:
        console.print(f"[red]Error running module '{module.name}': {e}[/red]")
        raise typer.Exit(1)
    
for module in settings.modules_enabled:
    module_module_cli_app = Typer()
    module_module_cli_app.command(name="get", help=f"Get a parameter value for the {module.name} module")(lambda module_name=module.name, param_name=typer.Argument(None, help="The parameter name to get"): get_module_command(module_name, param_name))
    module_module_cli_app.command(name="run", help=f"Run the {module.name} module")(lambda module_name=module.name: run_module_command(module_name))
    module_cli_app.add_typer(module_module_cli_app, name=module.name)

cli_app.add_typer(module_cli_app, name="module")


class Model(BaseModel):
    modules: list[ModuleSettings]    

if __name__ in {"__main__", "__mp_main__"}:    
    cli_app()
