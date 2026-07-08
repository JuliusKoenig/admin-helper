import encodings
import logging
import sys
from enum import Enum
from ipaddress import IPv4Address
from pathlib import Path
from typing import IO, Any

from pydantic import Field, BaseModel, field_validator, FilePath
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_DIRECTORY = Path("var") / "log"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_",
                                      env_nested_delimiter="__")
    debug: bool = Field(default=False, title="Debug", description="Whether to run in debug mode")
    binary_directory: Path = Field(default=Path("usr/local/bin"),
                                   title="Binary Directory",
                                   description="The directory where binaries are stored")
    config_directory: Path = Field(default=Path("etc"),
                                   title="Config Directory",
                                   description="The config directory")
    var_directory: Path = Field(default=Path("var"),
                                title="Var Directory",
                                description="The var directory")
    run_directory: Path = Field(default=Path("var/run"),
                                title="Run Directory",
                                description="The run directory")
    log_directory: Path = Field(default=LOG_DIRECTORY,
                                title="Log Directory",
                                description="The log directory")
    temp_directory: Path = Field(default=Path("tmp"),
                                 title="Temp Directory",
                                 description="The temp directory")

    class Logger(BaseModel):
        disabled: bool = Field(default=False,
                               title="Disable Logging",
                               description="Whether to log to a file")

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
            default=LogLevels.INFO,
            title="Log Level",
            description="The log level")
        console: bool = Field(default=True,
                              title="Console Logging",
                              description="Whether to log to the console")
        console_level: LogLevels | None = Field(default=None,
                                                title="Console Log Level",
                                                description="The log level for the console")
        console_format: str = Field(default="%(name)s - %(message)s",
                                    title="Console Log Format",
                                    description="The log format for the console")
        console_width: int = Field(default=160,
                                   title="Console Width",
                                   ge=0,
                                   description="The width of the console")

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

        console_outfile: OutFiles = Field(default=OutFiles.STDOUT,
                                          title="Console Outfile",
                                          description="The console outfile")
        console_rich_markup: bool = Field(default=True,
                                          title="Rich Markup",
                                          description="Whether to use rich markup in the console")
        console_rich_show_time: bool = Field(default=False,
                                             title="Show Time in Console",
                                             description="Whether to show the time in the console")
        console_rich_show_level: bool = Field(default=True,
                                              title="Show Level in Console",
                                              description="Whether to show the level in the console")
        console_rich_show_path: bool = Field(default=True,
                                             title="Show Path in Console",
                                             description="Whether to show the path in the console")
        file: bool = Field(default=False,
                           title="File Logging",
                           description="Whether to log to a file")
        file_path: Path | None = Field(default=LOG_DIRECTORY / "admin-helper" / "admin-helper.log",
                                       title="Log File Path",
                                       description="The path of the log file")
        file_level: LogLevels | None = Field(default=None,
                                             title="File Log Level",
                                             description="The log level for the file")
        file_format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                                 title="File Log Format",
                                 description="The log format for the file")

        class FileModes(str, Enum):
            """
            File modes
            """

            a = "a"
            w = "w"

        file_mode: FileModes = Field(default=FileModes.a,
                                     title="File Mode",
                                     description="The file mode")
        file_max_bytes: int = Field(default=1024 * 1024 * 10,
                                    title="Max File Size",
                                    ge=1024,
                                    description="The maximum size of the log file. Default is 10MB")
        file_backup_count: int = Field(default=5,
                                       title="Backup Log Files",
                                       description="The number of backup log files to keep")
        file_encoding: str = Field(default="utf-8",
                                   title="File Encoding",
                                   description="The encoding of the log file")
        file_delay: bool = Field(default=False,
                                 title="Delay File Logging",
                                 description="Whether to delay the file logging")
        file_archive_backup_count: int = Field(default=5, title="Backup Log Archives",
                                               ge=0,
                                               description="The number of backup log archives to keep")

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

    class Supervisor(BaseModel):
        dashboard: bool = Field(default=True,
                                title="Supervisor dashboard",
                                description="Whether to enable the Supervisor dashboard")
        dashboard_host: IPv4Address = Field(default=IPv4Address("127.0.0.1"),
                                            title="Supervisor dashboard host",
                                            description="The host of the Supervisor dashboard")
        dashboard_port: int = Field(default=8000,
                                    ge=1,
                                    le=65535,
                                    title="Supervisor dashboard port",
                                    description="The port of the Supervisor dashboard")
        logfile_parent_directory: Path = Field(default=LOG_DIRECTORY / "supervisord",
                                               title="Supervisor Logfile Parent Directory",
                                               description="The parent directory for Supervisor log files")
        default_logfile_maxbytes: int = Field(default=10 * 1024 * 1024,
                                              title="Default Logfile Max Bytes",
                                              description="The default maximum size of log files for Supervisor")
        default_logfile_backups: int = Field(default=5,
                                             title="Default Logfile Backups",
                                             description="The default number of backup log files for Supervisor")

    supervisor: Supervisor = Field(default_factory=Supervisor,
                                   title="Supervisor Settings",
                                   description="The supervisor settings")

    class Apache(BaseModel):
        binary_path: FilePath = Field(default=Path("/usr/sbin/httpd"),
                                      title="Apache Binary Path",
                                      description="Path to the Apache/httpd binary")
        module_directory_path: Path = Field(default=Path("/usr/lib/apache2/modules"),
                                            title="Apache Module Directory Path",
                                            description="Path to the Apache modules directory")
        host: IPv4Address = Field(default=IPv4Address("0.0.0.0"),
                                  title="Apache Host Address",
                                  description="The host address for the Apache server")
        port: int = Field(default=8080,
                          ge=1,
                          le=65535,
                          title="Apache Port",
                          description="The port for the Apache server")

        user: str = Field(default="www-data",
                          title="Apache User",
                          description="The user for the Apache server")
        group: str = Field(default="www-data",
                           title="Apache Group",
                           description="The group for the Apache server")

    apache: Apache = Field(default_factory=Apache,
                           title="Apache Settings",
                           description="The Apache settings")

    def model_post_init(self, context: Any, /):
        if self.debug:
            self.logger.level = self.Logger.LogLevels.DEBUG
            self.logger.console_level = self.Logger.LogLevels.DEBUG
            self.logger.file_level = self.Logger.LogLevels.DEBUG
        super().model_post_init(context)


settings = Settings()
