import getpass
from enum import Enum
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SupervisorSettings(BaseModel):
    config_file_name: str = Field(default="supervisord.conf",
                                  title="SupervisorD Config File name",
                                  description="The name of the supervisord config file.")
    pid_file_name: str = Field(default="supervisord.pid",
                               title="SupervisorD PID File name",
                               description="The name of the supervisord pidfile.")
    log_file_name: str = Field(default="main.log",
                               title="SupervisorD Log File name",
                               description="The name of the supervisord log file.")
    socket_file_name: str = Field(default="supervisord.sock",
                                  title="SupervisorD Socket File name",
                                  description="The name of the supervisord socket file.")

    class LogLevel(str, Enum):
        ERROR = "ERROR"
        WARNING = "WARNING"
        INFO = "INFO"
        DEBUG = "DEBUG"

        def __str__(self):
            return str(self.value).lower()

    log_level: LogLevel = Field(default=LogLevel.DEBUG,
                                title="Logger level",
                                description="The level of the logger")
    host: IPv4Address = Field(default=IPv4Address("127.0.0.1"),
                              title="SupervisorD host",
                              description="The host of the SupervisorD")
    port: int = Field(default=8000,
                      ge=1,
                      le=65535,
                      title="SupervisorD port",
                      description="The port of the SupervisorD")
    dashboard: bool = Field(default=True,
                            title="SupervisorD dashboard",
                            description="Whether to enable the SupervisorD dashboard")

    class _Programs(BaseModel):
        name: str = Field(default=...,
                          title="SupervisorD Programs",
                          description="The programs name")
        subcommand: str = Field(default=...,
                                title="SupervisorD Programs Subcommand",
                                description="The programs subcommand")
        directory: Path = Field(default_factory=Path.cwd,
                                title="SupervisorD Program Directory",
                                description="The directory of the SupervisorD program")
        user: str = Field(default_factory=getpass.getuser,
                          title="SupervisorD Program User",
                          description="The user of the SupervisorD program")
        autostart: bool = Field(default=True,
                                title="SupervisorD Program Autostart",
                                description="Whether the SupervisorD program autostart")
        autorestart: bool = Field(default=True,
                                  title="SupervisorD Program Autorestart",
                                  description="Whether the SupervisorD program autorestart")
        environment: dict[str, str] = Field(default_factory=dict,
                                            title="SupervisorD Program Environment",
                                            description="The environment of the SupervisorD program")

        def __init__(self, /, **data: Any):
            super().__init__(**data)

        @property
        def command(self) -> str:
            return f"python -m {__module_name__} {self.subcommand}"

    @property
    def config_file_path(self) -> Path:
        return settings.config_directory / self.config_file_name

    @property
    def pid_file_path(self) -> Path:
        return settings.run_directory / "supervisord" / self.pid_file_name

    @property
    def log_file_path(self) -> Path:
        return LOG_DIRECTORY / "supervisord" / self.log_file_name

    @property
    def socket_file_path(self) -> Path:
        return settings.run_directory / "supervisord" / self.socket_file_name

    @property
    def child_log_directory_path(self) -> Path:
        return self.log_file_path.parent / "child-log"

    @property
    def programs(self) -> list[_Programs]:
        programs = [
            self._Programs(name="Traefik",
                           subcommand="traefik")
        ]
        return programs

class Supervisor:
    def __init__(self):
        ...

