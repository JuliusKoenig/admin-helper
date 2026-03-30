from ipaddress import IPv4Address
import logging

import uvicorn
from fastapi import FastAPI
from nicegui import ui
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src._admin_helper_cli.logger import LoggerSettings, get_logger
from src._admin_helper_cli.settings import settings

class DashboardSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_DASHBOARD_",
                                      env_nested_delimiter="__")
    host: IPv4Address = Field(default=IPv4Address("127.0.0.1"),
                                title="Dashboard host",
                                description="The host of the dashboard")
    port: int = Field(default=8000,
                        ge=1,
                        le=65535,
                        title="Dashboard port",
                        description="The port of the dashboard")
    logger: LoggerSettings = Field(default_factory=LoggerSettings,
                                   title="Logger settings",
                                   description="Settings for the logger")


dashboard_settings = DashboardSettings()

api = FastAPI()


@ui.page("/")
async def root():
    return ui.label("Hello World")


def dashboard() -> None:
    logger = get_logger(settings=dashboard_settings.logger)
    logging.getLogger("uvicorn.error").parent = logger
    logging.getLogger("uvicorn.access").parent = logger    
    ui.run_with(app=api)

    uvicorn.run(api,
                host=str(dashboard_settings.host),
                port=dashboard_settings.port,
                log_config={
                    "version": 1,
                    "loggers": {
                        "uvicorn.error": {
                            "level": logger.level,
                        },
                        "uvicorn.access": {
                            "level": logger.level
                        }
                    }
                })