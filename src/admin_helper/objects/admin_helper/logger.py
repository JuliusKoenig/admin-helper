import logging
import os
import tarfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from admin_helper.console import AdminHelperConsole
from admin_helper.settings import AdminHelperSettings


class AdminHelperLogger(logging.Logger):
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
                     mode: AdminHelperSettings.Logger.FileModes = AdminHelperSettings.Logger.FileModes.a,
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

                    # noinspection PyTypeChecker
                    with tarfile.open(archive_filename, 'w:gz') as tar:
                        for log in backup_logs:
                            tar.add(log, arcname=log.name)
                            os.remove(log)

    def __init__(self, name: str):
        super().__init__(name)

        # set log level
        self.setLevel(AdminHelperSettings.logger.level.value)

        # add null handler
        null_handler = logging.NullHandler()
        self.addHandler(null_handler)

        # add console handler
        if not AdminHelperSettings.logger.disabled and AdminHelperSettings.logger.console:
            ch = RichHandler(
                console=AdminHelperConsole,
                show_time=AdminHelperSettings.logger.console_rich_show_time,
                markup=AdminHelperSettings.logger.console_rich_markup,
                show_level=AdminHelperSettings.logger.console_rich_show_level,
                show_path=AdminHelperSettings.logger.console_rich_show_path
            )
            ch.set_name(self.name)
            if AdminHelperSettings.logger.console_level is not None:
                ch.setLevel(AdminHelperSettings.logger.console_level.value)
            ch.setFormatter(self.Formatter(AdminHelperSettings.logger.console_format))
            self.addHandler(ch)

        # add file handler
        if not AdminHelperSettings.logger.disabled and AdminHelperSettings.logger.file:
            # check if log_file_path is set
            if AdminHelperSettings.logger.file_path is None:
                raise ValueError("Log file path not set")

            # check if log_file_path parent directory exists
            if not AdminHelperSettings.logger.file_path.parent.exists():
                raise FileNotFoundError(f"Log file path parent directory not exist: '{AdminHelperSettings.logger.file_path.parent}'")

            fh = self.TarRotatingFileHandler(
                name=self.name,
                filename=AdminHelperSettings.logger.file_path,
                mode=AdminHelperSettings.logger.file_mode,
                max_bytes=AdminHelperSettings.logger.file_max_bytes,
                backup_count=AdminHelperSettings.logger.file_backup_count,
                encoding=AdminHelperSettings.logger.file_encoding,
                delay=AdminHelperSettings.logger.file_delay,
                archive_backup_count=AdminHelperSettings.logger.file_archive_backup_count
            )
            if AdminHelperSettings.logger.file_level is not None:
                fh.setLevel(AdminHelperSettings.logger.file_level.value)
            fh.setFormatter(self.Formatter(AdminHelperSettings.logger.file_format))
            self.addHandler(fh)

        # log first message
        self.debug(f"Logger '{self.name}' initialized.")
