import encodings
import logging
import os
import sys
from enum import Enum
from pathlib import Path
from typing import IO, Any

from admin_helper_cli.modules.dashboard.settings import DashboardSettings
from admin_helper_cli.modules.traefik.settings import TraefikSettings
from pydantic import Field, BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_",
                                      env_nested_delimiter="__")
    
    class LoggerSettings(BaseModel):
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

        level: LogLevels = Field(default=LogLevels.WARNING, title="Log Level", description="The log level")
        console: bool = Field(default=True, title="Console Logging", description="Whether to log to the console")
        console_level: LogLevels | None = Field(default=None, title="Console Log Level", description="The log level for the console")
        console_format: str = Field(default="%(name)s - %(message)s", title="Console Log Format", description="The log format for the console")
        console_width: int = Field(default=80, title="Console Width", ge=0, description="The width of the console")

        class OutFiles(str, Enum):
            """
            Output files
            """

            STDOUT = "stdout"
            STDERR = "stderr"

            def get_file(self) -> IO[str] | Any:
                if self == Settings.LoggerSettings.OutFiles.STDOUT:
                    return sys.stdout
                elif self == Settings.LoggerSettings.OutFiles.STDERR:
                    return sys.stderr
                raise ValueError(f"Unknown outfile '{self}'.")

        console_outfile: OutFiles = Field(default=OutFiles.STDOUT, title="Console Outfile", description="The console outfile")
        console_rich_markup: bool = Field(default=True, title="Rich Markup", description="Whether to use rich markup in the console")
        console_rich_show_time: bool = Field(default=False, title="Show Time in Console", description="Whether to show the time in the console")
        console_rich_show_level: bool = Field(default=True, title="Show Level in Console", description="Whether to show the level in the console")
        console_rich_show_path: bool = Field(default=True, title="Show Path in Console", description="Whether to show the path in the console")
        file: bool = Field(default=False, title="File Logging", description="Whether to log to a file")
        file_path: Path | None = Field(default=None, title="Log File Path", description="The path of the log file")
        file_level: LogLevels | None = Field(default=None, title="File Log Level", description="The log level for the file")
        file_format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", title="File Log Format", description="The log format for the file")

        class FileModes(str, Enum):
            """
            File modes
            """

            a = "a"
            w = "w"

        file_mode: FileModes = Field(default=FileModes.a, title="File Mode", description="The file mode")
        file_max_bytes: int = Field(default=1024 * 1024 * 10, title="Max File Size", ge=1024, description="The maximum size of the log file. Default is 10MB")
        file_backup_count: int = Field(default=5, title="Backup Log Files", description="The number of backup log files to keep")
        file_encoding: str = Field(default="utf-8", title="File Encoding", description="The encoding of the log file")
        file_delay: bool = Field(default=False, title="Delay File Logging", description="Whether to delay the file logging")
        file_archive_backup_count: int = Field(default=5, title="Backup Log Archives", ge=0, description="The number of backup log archives to keep")

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
            available_encodings = [encoding_name.replace("_", "-") for encoding_name in encodings.aliases.aliases.values()]
            if value not in available_encodings:
                raise ValueError(f"Encoding '{value}' is not available. Available encodings: {', '.join(available_encodings)}")
            return value

    logger: LoggerSettings = Field(default_factory=LoggerSettings,
                                   title="Logger settings",
                                   description="Settings for the logger")

    class Daemon(BaseModel):
        pass

    daemon: Daemon = Field(default_factory=Daemon,
                           title="Daemon settings",
                           description="Settings for the daemon")

    traefik: TraefikSettings = Field(default_factory=TraefikSettings,
                                   title="Traefik settings",
                                   description="Settings for the Traefik")

    dashboard: DashboardSettings = Field(default_factory=DashboardSettings,
                           title="Dashboard settings",
                           description="Settings for the dashboard")

env = dict(os.environ)

settings = Settings()
