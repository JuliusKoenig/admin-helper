from ipaddress import IPv4Address
from pathlib import Path
import subprocess
import sys

from passlib.apache import HtpasswdFile
from pydantic import Field, DirectoryPath, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src._admin_helper_cli.helper import render, run_cmd
from src._admin_helper_cli.logger import LoggerSettings, get_logger
from src._admin_helper_cli.settings import settings
from src._admin_helper_cli.dashboard import dashboard_settings

class TraefikSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_TRAEFIK_",
                                      env_nested_delimiter="__")
    path: DirectoryPath = Field(default=...,
                                title="Traefik path",
                                description="The path to the Traefik directory")
    version: str = Field(default=...,
                            title="Traefik version",
                            description="The version of Traefik to use")
    binary_name: str = Field(default=...,
                                title="Traefik binary name",
                                description="The name of the Traefik binary")
    host: IPv4Address = Field(default=...,
                                title="Traefik host",
                                description="The host of the Traefik")
    port: int = Field(default=...,
                        ge=1,
                        le=65535,
                        title="Traefik port",
                        description="The port of the Traefik")
    dashboard: bool = Field(default=True,
                            title="Traefik dashboard",
                            description="Whether to enable the Traefik dashboard")
    logger: LoggerSettings = Field(default_factory=LoggerSettings,
                                   title="Logger settings",
                                   description="Settings for the logger")

    @computed_field(title="Traefik binary path", description="The path to the Traefik binary")
    def binary_path(self) -> Path:
        binary_path: Path = self.path / self.binary_name
        if not binary_path.is_file():
            raise FileNotFoundError(
                f"Traefik binary not found at {binary_path}")
        return binary_path
    
traefik_settings = TraefikSettings()


def traefik() -> None:
    logger = get_logger(settings=traefik_settings.logger)
    template_path = Path(__file__).parent / "templates" / "traefik"
    config_path = traefik_settings.path / "config"
    htpasswd_path = config_path / ".htpasswd"

    # render the traefik configuration files
    kwargs = dict(
        settings=settings,
        traefik_settings=traefik_settings,
        dashboard_settings=dashboard_settings,
        template_path=template_path,
        config_path=config_path,
        htpasswd_path=htpasswd_path
    )
    
    logger.debug("Starting Traefik configuration rendering")
    render(
        logger=logger,
        src=template_path,
        dst=config_path,
        cleanup=True,
        **kwargs)
    
    # render modules configuration files
    logger.debug("Starting Traefik modules configuration rendering")
    for module in settings.modules_enabled:
        if module.traefik_templates_path.is_dir():
            logger.debug(f"Rendering Traefik configuration for module {module.name}")
            render(
                logger=logger,
                src=module.traefik_templates_path,
                dst=config_path,
                cleanup=False,
                module=module,
                **kwargs)
            
    # generate .htpasswd
    logger.debug(f"Generating .htpasswd at {htpasswd_path}")
    ht = HtpasswdFile(str(htpasswd_path), new=True)
    for username, user in settings.users.items():
        logger.debug(f"Adding user {username} to .htpasswd")
        ht.set_password(username, user.password)
    ht.save()
    logger.debug(f".htpasswd generated at {htpasswd_path}")

    logger.debug("Starting Traefik")
    run_cmd(
        logger=logger,
        args=[
            str(traefik_settings.binary_path),
            "--configFile=" + str(config_path / "traefik.yml")
        ]
    )