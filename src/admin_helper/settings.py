import encodings
import logging
import platform
import sys
from enum import Enum
from ipaddress import IPv4Address
from pathlib import Path
from typing import IO, Any

from pydantic import Field, BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_DIRECTORY = Path("var") / "log"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_",
                                      env_nested_delimiter="__")
    binary_directory: Path = Field(default=Path("usr/local/bin"),
                                   title="Binary Directory",
                                   description="The directory where binaries are stored")
    config_directory: Path = Field(default=Path("etc"),
                                   title="Config Directory",
                                   description="The config directory")
    run_directory: Path = Field(default=Path("var/run"),
                                title="Run Directory",
                                description="The run directory")
    temp_directory: Path = Field(default=Path("tmp"),
                                 title="Temp Directory",
                                 description="The temp directory")

    class Logger(BaseModel):
        class LogLevels(str, Enum):
            """
            Log levels
            """

            CRITICAL = "CRITICAL"
            FATAL = "FATAL"
            ERROR = "ERROR"
            WARNING = "WARNING"
            INFO = "INFO"
            DEBUG = "DEBUG"

            def get_level_number(self) -> int:
                return int(logging.getLevelName(self.value))

        level: LogLevels = Field(
            default=LogLevels.DEBUG, title="Log Level", description="The log level")
        console: bool = Field(default=True, title="Console Logging",
                              description="Whether to log to the console")
        console_level: LogLevels | None = Field(
            default=None, title="Console Log Level", description="The log level for the console")
        console_format: str = Field(default="%(name)s - %(message)s",
                                    title="Console Log Format", description="The log format for the console")
        console_width: int = Field(
            default=80, title="Console Width", ge=0, description="The width of the console")

        class OutFiles(str, Enum):
            """
            Output files
            """

            STDOUT = "stdout"
            STDERR = "stderr"

            def get_file(self) -> IO[str] | Any:
                if self == Settings.Logger.OutFiles.STDOUT:
                    return sys.stdout
                elif self == Settings.Logger.OutFiles.STDERR:
                    return sys.stderr
                raise ValueError(f"Unknown outfile '{self}'.")

        console_outfile: OutFiles = Field(
            default=OutFiles.STDOUT, title="Console Outfile", description="The console outfile")
        console_rich_markup: bool = Field(
            default=True, title="Rich Markup", description="Whether to use rich markup in the console")
        console_rich_show_time: bool = Field(
            default=False, title="Show Time in Console", description="Whether to show the time in the console")
        console_rich_show_level: bool = Field(
            default=True, title="Show Level in Console", description="Whether to show the level in the console")
        console_rich_show_path: bool = Field(
            default=True, title="Show Path in Console", description="Whether to show the path in the console")
        file: bool = Field(default=False, title="File Logging",
                           description="Whether to log to a file")
        file_path: Path | None = Field(
            default=LOG_DIRECTORY / "admin-helper", title="Log File Path", description="The path of the log file")
        file_level: LogLevels | None = Field(
            default=None, title="File Log Level", description="The log level for the file")
        file_format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                                 title="File Log Format", description="The log format for the file")

        class FileModes(str, Enum):
            """
            File modes
            """

            a = "a"
            w = "w"

        file_mode: FileModes = Field(
            default=FileModes.a, title="File Mode", description="The file mode")
        file_max_bytes: int = Field(default=1024 * 1024 * 10, title="Max File Size",
                                    ge=1024, description="The maximum size of the log file. Default is 10MB")
        file_backup_count: int = Field(
            default=5, title="Backup Log Files", description="The number of backup log files to keep")
        file_encoding: str = Field(
            default="utf-8", title="File Encoding", description="The encoding of the log file")
        file_delay: bool = Field(default=False, title="Delay File Logging",
                                 description="Whether to delay the file logging")
        file_archive_backup_count: int = Field(
            default=5, title="Backup Log Archives", ge=0, description="The number of backup log archives to keep")

        def model_post_init(self, context: Any, /):
            if self.console_level is None:
                self.console_level = self.level
            if self.file_level is None:
                self.file_level = self.level

            super().model_post_init(context)

        @field_validator("level", "console_level", "file_level", mode="before")
        def validate_level(cls, value: int | str) -> str:
            if isinstance(value, int):
                value = logging.getLevelName(value)
            return str(value)

        @field_validator("file_encoding")
        def validate_file_encoding(cls, value):
            # check if encoding is available
            available_encodings = [encoding_name.replace(
                "_", "-") for encoding_name in encodings.aliases.aliases.values()]
            if value not in available_encodings:
                raise ValueError(
                    f"Encoding '{value}' is not available. Available encodings: {', '.join(available_encodings)}")
            return value

    logger: Logger = Field(default_factory=Logger,
                           title="Logger Settings",
                           description="The logger settings")

    class User(BaseModel):
        password: str = Field(..., title="Password",
                              description="The password of the user")
        is_admin: bool = Field(
            default=False, title="Is Admin", description="Whether the user is an admin")

    users: dict[str, User] = Field(default_factory=dict,
                                   title="Users",
                                   description="List of users")

    class SupervisorD(BaseModel):
        download_base_url: str = Field(default="https://github.com/ochinchina/supervisord/releases/download",
                                       title="Base download URL to SupervisorD",
                                       description="The base download URL to the SupervisorD binary")

        version: str = Field(...,
                             title="SupervisorD Version",
                             description="The SupervisorD version")
        binary_name: str = Field(default_factory=lambda: "supervisord" if platform.system() == "Linux" else "supervisord.exe",
                                 title="SupervisorD Binary name",
                                 description="The name of the SupervisorD binary")
        temp_binary_file_name: str = Field(default_factory=lambda: "supervisord" if platform.system().lower() == "linux" else "supervisord.exe",
                                           title="SupervisorD Temp binary name",
                                           description="The name of the SupervisorD temp binary file")
        temp_archive_file_name: str = Field(default_factory=lambda: "supervisord.tar.gz" if platform.system().lower() == "linux" else "supervisord.zip",
                                            title="SupervisorD Temp archive name",
                                            description="The name of the SupervisorD temp archive file")
        config_file_name: str = Field(default="supervisord.conf",
                                      title="SupervisorD Config File name",
                                      description="The name of the supervisord config file.")
        pid_file_name: str = Field(default="supervisord.pid",
                                   title="SupervisorD PID File name",
                                   description="The name of the supervisord pidfile.")
        log_file_name: str = Field(default="main.log",
                                   title="SupervisorD Log File name",
                                   description="The name of the supervisord log file.")

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
            ...

        @property
        def os(self):
            os_name = platform.system()
            if os_name not in ["Linux", "Darwin", "Windows"]:
                raise RuntimeError(f"Unsupported operating system: {os_name}")
            if os_name == "Darwin":
                os_name = "macOS"
            return os_name

        @property
        def arch(self) -> str:
            arch = platform.machine().lower()
            if arch == "x86_64" or arch == "amd64":
                arch = "64-bit"
            elif arch == "arm64" or arch == "aarch64":
                arch = "ARM64"
            else:
                raise RuntimeError(f"Unsupported architecture: {arch}")
            return arch

        @property
        def archive_type(self) -> str:
            archive_type = "tar.gz"
            if self.os == "Windows":
                archive_type = "zip"
            return archive_type

        @property
        def download_url(self) -> str:
            return f"{self.download_base_url}/v{self.version}/supervisord_{self.version}_{self.os}_{self.arch}.{self.archive_type}"

        @property
        def binary_file_path(self) -> Path:
            return settings.binary_directory / self.binary_name

        @property
        def temp_binary_file_path(self):
            return settings.temp_directory / f"supervisord_{self.version}_{self.os}_{self.arch}" / self.temp_binary_file_name

        @property
        def temp_archive_file_path(self):
            return settings.temp_directory / self.temp_archive_file_name

        @property
        def config_file_path(self) -> Path:
            return settings.config_directory / "supervisord" / self.config_file_name

        @property
        def pid_file_path(self) -> Path:
            return settings.run_directory / "supervisord" / self.pid_file_name

        @property
        def log_file_path(self) -> Path:
            return LOG_DIRECTORY / "supervisord" / self.log_file_name

        @property
        def programs(self) -> list[_Programs]:
            return []

    supervisord: SupervisorD = Field(default_factory=SupervisorD,
                                     title="SupervisorD Settings",
                                     description="The supervisord settings")

    class Traefik(BaseModel):
        download_base_url: str = Field(default="https://github.com/traefik/traefik/releases/download",
                                       title="Base download URL to Traefik",
                                       description="The base download URL to the Traefik binary.")
        version: str = Field(...,
                             title="Traefik Version",
                             description="The Traefik version")
        binary_name: str = Field(default_factory=lambda: "traefik" if platform.system() == "Linux" else "traefik.exe",
                                 title="Traefik Binary name",
                                 description="The name of the Traefik binary")
        temp_binary_file_name: str = Field(default_factory=lambda: "traefik" if platform.system().lower() == "linux" else "traefik.exe",
                                           title="Traefik Temp binary name",
                                           description="The name of the Traefik temp binary file")
        temp_archive_file_name: str = Field(default_factory=lambda: "traefik.tar.gz" if platform.system().lower() == "linux" else "traefik.zip",
                                            title="Traefik Temp archive name",
                                            description="The name of the Traefik temp archive file")
        config_file_name: str = Field(default="traefik.yaml",
                                      title="Traefik static config File name",
                                      description="The name of the Traefik static config file")
        dynamic_file_name: str = Field(default="dynamic.yaml",
                                       title="Traefik Dynamic Config File name",
                                       description="The name of the Traefik dynamic config file")
        htpasswd_file_name: str = Field(default=".htpasswd",
                                        title="Traefik htpasswd File name",
                                        description="The name of the Traefik htpasswd file")
        log_file_name: str = Field(default="main.log",
                                   title="Traefik Log File name",
                                   description="The name of the Traefik log file.")
        access_log_file_name: str = Field(default="access.log",
                                          title="Traefik Access Log File name",
                                          description="The name of the Traefik access log file")

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
                                  title="Traefik host",
                                  description="The host of the Traefik")
        port: int = Field(default=8080,
                          ge=1,
                          le=65535,
                          title="Traefik port",
                          description="The port of the Traefik")
        dashboard: bool = Field(default=False,
                                title="Traefik dashboard",
                                description="Whether to enable the Traefik dashboard")

        class _Router(BaseModel):
            name: str = Field(default=...,
                              title="Router Name",
                              description="The name of the router")
            rule: str = Field(default=...,
                              title="Router Rule",
                              description="The router rule")
            middlewares: list[str] = Field(default=...,
                                           title="Router Middlewares",
                                           description="The router middlewares")
            service: str = Field(default=...,
                                 title="Router Service",
                                 description="The router service")
            entry_points: list[str] = Field(default=...,
                                            title="Router Entrypoints",
                                            description="The router entrypoints")

        class _Service(BaseModel):
            name: str = Field(default=...,
                              title="Service Name",
                              description="The name of the service")
            protocol: str = Field(default=...,
                                  title="Service Protocol",
                                  description="The protocol of the service")
            host: str = Field(default=...,
                              title="Service Host",
                              description="The host of the service")
            port: int = Field(default=...,
                              ge=1,
                              le=65535,
                              title="Service Port",
                              description="The port of the service")

        @property
        def os(self):
            os_name = platform.system()
            if os_name not in ["Linux", "Darwin", "Windows"]:
                raise RuntimeError(f"Unsupported operating system: {os_name}")
            return os_name.lower()

        @property
        def arch(self) -> str:
            arch = platform.machine().lower()
            if arch == "x86_64" or arch == "amd64":
                arch = "amd64"
            elif arch == "arm64" or arch == "aarch64":
                arch = "arm64"
            else:
                raise RuntimeError(f"Unsupported architecture: {arch}")
            return arch

        @property
        def archive_type(self) -> str:
            archive_type = "tar.gz"
            if self.os == "windows":
                archive_type = "zip"
            return archive_type

        @property
        def download_url(self) -> str:
            return f"{self.download_base_url}/v{self.version}/traefik_v{self.version}_{self.os}_{self.arch}.{self.archive_type}"

        @property
        def binary_file_path(self) -> Path:
            return settings.binary_directory / self.binary_name

        @property
        def temp_binary_file_path(self):
            return settings.temp_directory / self.temp_binary_file_name

        @property
        def temp_archive_file_path(self):
            return settings.temp_directory / self.temp_archive_file_name

        @property
        def config_file_path(self) -> Path:
            return settings.config_directory / "traefik" / self.config_file_name

        @property
        def dynamic_file_path(self) -> Path:
            return settings.config_directory / "traefik" / self.dynamic_file_name

        @property
        def htpasswd_file_path(self) -> Path:
            return settings.config_directory / "traefik" / self.htpasswd_file_name

        @property
        def log_file_path(self) -> Path:
            return LOG_DIRECTORY / "traefik" / self.log_file_name

        @property
        def access_log_file_path(self) -> Path:
            return LOG_DIRECTORY / "traefik" / self.access_log_file_name

        @property
        def routers(self) -> list[Any]:
            routers = []
            if settings.traefik.dashboard:
                routers.append(Settings.Traefik._Router(
                    name="dashboard",
                    rule="PathPrefix(`/api`) || PathPrefix(`/dashboard`)",
                    middlewares=["auth-basic"],
                    service="api@internal",
                    entry_points=["http"]
                ))
            return routers

        @property
        def services(self) -> list[Any]:
            services = []
            return services

    traefik: Traefik = Field(default_factory=Traefik,
                             title="Traefik Settings",
                             description="The Traefik settings")


settings = Settings(users={"admin": Settings.User(password="admin", is_admin=True)})
