from ipaddress import IPv4Address
from pathlib import Path
import subprocess
import sys

from passlib.apache import HtpasswdFile
from pydantic import Field, DirectoryPath, FilePath
from pydantic_settings import BaseSettings, SettingsConfigDict

from src._admin_helper_cli.helper import render, run_cmd
from src._admin_helper_cli.logger import LoggerSettings, get_logger
from src._admin_helper_cli.settings import settings
from src._admin_helper_cli.traefik import traefik_settings
from src._admin_helper_cli.dashboard import dashboard_settings

class SupervisorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_SUPERVISOR_",
                                      env_nested_delimiter="__")
    config_path: DirectoryPath = Field(default=...,
                                title="Supervisor config path",
                                description="The path to the Supervisor configuration directory")
    binary_path: FilePath = Field(default=...,
                                title="Supervisor binary path",
                                description="The path to the Supervisor binary")

    logger: LoggerSettings = Field(default_factory=LoggerSettings,
                                   title="Logger settings",
                                   description="Settings for the logger")

    
supervisor_settings = SupervisorSettings()


def supervisor() -> None:
    logger = get_logger(settings=supervisor_settings.logger)
    template_path = Path(__file__).parent / "templates" / "supervisor"
    admin_help_cli_cmd = f"{sys.executable} -m admin_helper_cli"

    # render the supervisor configuration files
    kwargs = dict(
        settings=settings,
        supervisor_settings=supervisor_settings,
        traefik_settings=traefik_settings,
        dashboard_settings=dashboard_settings,
        template_path=template_path,
        admin_help_cli_cmd=admin_help_cli_cmd,
    )
    
    logger.debug("Starting Supervisor configuration rendering")
    render(
        logger=logger,
        src=template_path,
        dst=supervisor_settings.config_path,
        cleanup=True,
        **kwargs)
    
    # render modules configuration files
    logger.debug("Starting Supervisor modules configuration rendering")
    for module in settings.modules_enabled:
        if module.supervisor_templates_path.is_dir():
            logger.debug(f"Rendering Supervisor configuration for module {module.name}")
            render(
                logger=logger,
                src=module.supervisor_templates_path,
                dst=supervisor_settings.config_path,
                cleanup=False,
                module=module,
                **kwargs)

    logger.debug("Starting Supervisor")
    run_cmd(
        logger=logger,
        args=[
            str(supervisor_settings.binary_path),
            "-c",
            str(supervisor_settings.config_path / "base.conf")
        ]
    )