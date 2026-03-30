import logging
import os
import tarfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from enum import Enum
import sys
import encodings.aliases
from typing import IO, Any

from rich.logging import RichHandler
from pydantic import BaseModel, Field, field_validator

from src._admin_helper_cli import __name__ as __package_name__
from src._admin_helper_cli.console import console


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

    level: LogLevels = Field(
        default=LogLevels.WARNING, title="Log Level", description="The log level")
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
            if self == LoggerSettings.OutFiles.STDOUT:
                return sys.stdout
            elif self == LoggerSettings.OutFiles.STDERR:
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
        default=None, title="Log File Path", description="The path of the log file")
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


class TarRotatingFileHandler(RotatingFileHandler):
    """
    RotatingFileHandler that archives old log files as tar.gz files
    """

    def __init__(self,
                 name: str,
                 filename: str | Path,
                 mode: LoggerSettings.FileModes = LoggerSettings.FileModes.a,
                 max_bytes: int = 0,
                 backup_count: int = 0,
                 encoding: str | None = None,
                 delay: bool = False,
                 archive_backup_count: int = 0):
        super().__init__(filename, mode.value, max_bytes, backup_count, encoding, delay)
        self.set_name(name)
        self.archiveBackupCount = archive_backup_count
        self.archiveBaseFilename = self.baseFilename[:self.baseFilename.rfind('.')]

    def doRollover(self):
        # rotate and delete old log files
        super().doRollover()

        # archive old log files if backupCount limit is reached
        if self.backupCount > 0:
            backup_log_pattern = self.baseFilename + '.%d'
            # get all existing backup logs
            backup_logs = [Path(backup_log_pattern % i) for i in range(1, self.backupCount + 1)]
            backup_logs = [log for log in backup_logs if log.exists()]

            # check if backup count limit is reached
            if len(backup_logs) >= self.backupCount:
                archive_filename_pattern = self.archiveBaseFilename + '_logs.%d.tar.gz'
                archive_count = 0
                # add all backup logs to tar archive
                archive_filename = archive_filename_pattern % archive_count
                while Path(archive_filename).exists():
                    archive_count += 1
                    archive_filename = archive_filename_pattern % archive_count

                    # if archive count limit is reached, delete oldest archive
                    if archive_count > self.archiveBackupCount:
                        archive_count = 0
                        archive_filename = archive_filename_pattern % archive_count
                        os.remove(archive_filename)
                        break

                with tarfile.open(archive_filename, 'w:gz') as tar:
                    for log in backup_logs:
                        tar.add(log, arcname=log.name)
                        os.remove(log)

def get_logger(settings: LoggerSettings) -> logging.Logger:
    logger = logging.getLogger(__package_name__)

    # set log level
    logger.setLevel(settings.level.value)

    # add null handler
    null_handler = logging.NullHandler()
    logger.addHandler(null_handler)

    # add console handler
    if settings.console:
        ch = RichHandler(
            console=console,
            show_time=settings.console_rich_show_time,
            markup=settings.console_rich_markup,
            show_level=settings.console_rich_show_level,
            show_path=settings.console_rich_show_path
        )
        ch.set_name(logger.name)
        if settings.console_level is not None:
            ch.setLevel(settings.console_level.value)
        ch.setFormatter(logging.Formatter(settings.console_format))
        logger.addHandler(ch)

    # add file handler
    if settings.file:
        # check if log_file_path is set
        if settings.file_path is None:
            raise ValueError("Log file path not set")

        # check if log_file_path parent directory exists
        if not settings.file_path.parent.exists():
            raise FileNotFoundError(f"Log file path parent directory not exist: '{settings.file_path.parent}'")

        fh = TarRotatingFileHandler(
            name=logger.name,
            filename=settings.file_path,
            mode=settings.file_mode,
            max_bytes=settings.file_max_bytes,
            backup_count=settings.file_backup_count,
            encoding=settings.file_encoding,
            delay=settings.file_delay,
            archive_backup_count=settings.file_archive_backup_count
        )
        if settings.file_level is not None:
            fh.setLevel(settings.file_level.value)
        fh.setFormatter(logging.Formatter(settings.file_format))
        logger.addHandler(fh)


    # log first message
    logger.debug(f"Logger '{logger.name}' initialized.")
    
    return logger