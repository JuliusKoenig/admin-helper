import logging
import re
import threading
import time
from collections import defaultdict
from datetime import datetime
from logging import Logger
from pathlib import Path


class LogFileStreamer(threading.Thread):
    def __init__(self,
                 logger: Logger,
                 log_file_path: Path,
                 timeout: int = 10,
                 pattern: re.Pattern[str] = re.compile(""),
                 filter_pattern: re.Pattern[str] = re.compile(""),
                 level_mapping: dict[str, int] | None = None,
                 fixed_level: int | None = None,
                 timestamp_format: str = "%Y-%m-%dT%H:%M:%S%z",
                 message_format: str = "{message}") -> None:
        super().__init__(name=f"{self.__class__.__name__}-{log_file_path.name}",
                         daemon=True)
        self._running = False
        self.stop = threading.Event()
        self.lock = threading.Lock()

        for i in range(timeout):
            if log_file_path.is_file():
                break
            time.sleep(1)
        if not log_file_path.is_file():
            raise FileNotFoundError(f"'{log_file_path}' is not a file")
        self.logger = logger
        self.log_file_path = log_file_path
        self.pattern = pattern
        self.filter_pattern = filter_pattern
        if level_mapping is None:
            level_mapping = {
                "DBG": logging.DEBUG,
                "DEBUG": logging.DEBUG,
                "INF": logging.INFO,
                "INFO": logging.INFO,
                "WRN": logging.WARNING,
                "WARN": logging.WARNING,
                "WARNING": logging.WARNING,
                "ERR": logging.ERROR,
                "ERROR": logging.ERROR,
                "FTL": logging.CRITICAL,
                "FATAL": logging.CRITICAL,
            }
        self.level_mapping = level_mapping
        self.fixed_level = fixed_level
        self.timestamp_format = timestamp_format
        self.message_format = message_format

    @property
    def running(self) -> bool:
        with self.lock:
            return self._running

    def emit_log(self,
                 line: str):
        line = line.strip()
        match = self.pattern.match(line)
        if not match:
            return
        timestamp_raw = match.group("timestamp")
        if self.fixed_level is None:
            level_raw = match.group("level")
            log_level = self.level_mapping.get(level_raw, logging.INFO)
        else:
            log_level = self.fixed_level

        # parse message
        values = defaultdict(str, match.groupdict())
        message = self.message_format.format_map(values)

        # filter message
        message = self.filter_pattern.sub("", message)
        timestamp = datetime.strptime(timestamp_raw, self.timestamp_format)
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=log_level,
            fn="traefik",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        record.created = timestamp.timestamp()
        record.msecs = (record.created - int(record.created)) * 1000
        self.logger.handle(record)

    def run(self) -> None:
        with self.lock:
            self._running = True

        try:
            with self.log_file_path.open("r", encoding="utf-8", errors="replace") as file:
                while not self.stop.is_set():
                    line = file.readline()

                    if line:
                        self.emit_log(line)
                    else:
                        time.sleep(0.2)

        finally:
            with self.lock:
                self._running = False

    def shutdown(self) -> None:
        self.stop.set()
        self.join()
