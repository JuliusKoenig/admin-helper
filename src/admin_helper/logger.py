import logging
import os
import tarfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from admin_helper import __name__ as __package_name__
from admin_helper.console import console
from admin_helper.settings import settings, Settings


class Formatter(logging.Formatter):
    def format(self, record) -> str:
        if hasattr(record, "markup"):
            return str(record.msg)
        return super().format(record)

class TarRotatingFileHandler(RotatingFileHandler):
    """
    RotatingFileHandler that archives old log files as tar.gz files
    """

    def __init__(self,
                 name: str,
                 filename: str | Path,
                 mode: Settings.Logger.FileModes = Settings.Logger.FileModes.a,
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

logger = logging.getLogger(__package_name__)

# set log level
logger.setLevel(settings.logger.level.value)

# add null handler
null_handler = logging.NullHandler()
logger.addHandler(null_handler)

# add console handler
if not settings.logger.disabled and settings.logger.console:
    ch = RichHandler(
        console=console,
        show_time=settings.logger.console_rich_show_time,
        markup=settings.logger.console_rich_markup,
        show_level=settings.logger.console_rich_show_level,
        show_path=settings.logger.console_rich_show_path
    )
    ch.set_name(logger.name)
    if settings.logger.console_level is not None:
        ch.setLevel(settings.logger.console_level.value)
    ch.setFormatter(Formatter(settings.logger.console_format))
    logger.addHandler(ch)

# add file handler
if not settings.logger.disabled and settings.logger.file:
    # check if log_file_path is set
    if settings.logger.file_path is None:
        raise ValueError("Log file path not set")

    # check if log_file_path parent directory exists
    if not settings.logger.file_path.parent.exists():
        raise FileNotFoundError(f"Log file path parent directory not exist: '{settings.logger.file_path.parent}'")

    fh = TarRotatingFileHandler(
        name=logger.name,
        filename=settings.logger.file_path,
        mode=settings.logger.file_mode,
        max_bytes=settings.logger.file_max_bytes,
        backup_count=settings.logger.file_backup_count,
        encoding=settings.logger.file_encoding,
        delay=settings.logger.file_delay,
        archive_backup_count=settings.logger.file_archive_backup_count
    )
    if settings.logger.file_level is not None:
        fh.setLevel(settings.logger.file_level.value)
    fh.setFormatter(Formatter(settings.logger.file_format))
    logger.addHandler(fh)

# log first message
logger.debug(f"Logger '{logger.name}' initialized.")

