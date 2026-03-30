import logging
import os
import tarfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from admin_helper import __name__ as __package_name__
from admin_helper.console import console
from admin_helper.settings import settings, Settings


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


def get_logger(_settings: Settings.Logger) -> logging.Logger:
    _logger = logging.getLogger(__package_name__)

    # set log level
    _logger.setLevel(_settings.level.value)

    # add null handler
    null_handler = logging.NullHandler()
    _logger.addHandler(null_handler)

    # add console handler
    if _settings.console:
        ch = RichHandler(
            console=console,
            show_time=_settings.console_rich_show_time,
            markup=_settings.console_rich_markup,
            show_level=_settings.console_rich_show_level,
            show_path=_settings.console_rich_show_path
        )
        ch.set_name(_logger.name)
        if _settings.console_level is not None:
            ch.setLevel(_settings.console_level.value)
        ch.setFormatter(logging.Formatter(_settings.console_format))
        _logger.addHandler(ch)

    # add file handler
    if _settings.file:
        # check if log_file_path is set
        if _settings.file_path is None:
            raise ValueError("Log file path not set")

        # check if log_file_path parent directory exists
        if not _settings.file_path.parent.exists():
            raise FileNotFoundError(f"Log file path parent directory not exist: '{_settings.file_path.parent}'")

        fh = TarRotatingFileHandler(
            name=_logger.name,
            filename=_settings.file_path,
            mode=_settings.file_mode,
            max_bytes=_settings.file_max_bytes,
            backup_count=_settings.file_backup_count,
            encoding=_settings.file_encoding,
            delay=_settings.file_delay,
            archive_backup_count=_settings.file_archive_backup_count
        )
        if _settings.file_level is not None:
            fh.setLevel(_settings.file_level.value)
        fh.setFormatter(logging.Formatter(_settings.file_format))
        _logger.addHandler(fh)

    # log first message
    _logger.debug(f"Logger '{_logger.name}' initialized.")

    return _logger


logger = get_logger(settings.logger)
