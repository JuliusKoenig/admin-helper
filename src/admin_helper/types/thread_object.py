import logging
import threading
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from admin_helper.types.base_object import BaseObject


@dataclass
class ThreadObject(BaseObject):
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _thread: threading.Thread = field(default=None, init=False)

    __str_name__: str | None = "ThreadObject"

    def __post_init__(self):
        self._thread = threading.Thread(target=self._run,
                                        name=self.name,
                                        daemon=True)
        super().__post_init__()

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    @property
    def thread(self) -> threading.Thread:
        with self.lock:
            return self._thread

    @property
    def logger(self) -> logging.Logger:
        with self.lock:
            return super().logger

    @property
    def parent(self) -> Optional["BaseObject"]:
        with self.lock:
            return super().parent

    @property
    def children(self) -> list["BaseObject"]:
        with self.lock:
            return super().children

    def _run(self):
        first = True
        try:
            while True:
                try:
                    if first:
                        self.logger.info(f"Starting {self} ...")
                    else:
                        self.logger.info(f"Restarting {self} ...")
                    self.run()
                except Exception as e:
                    self.logger.exception(f"Exception occurred: \n{e}")
        except KeyboardInterrupt:
            self.logger.info(f"Stopping {self} ...")

    @abstractmethod
    def run(self):
        ...
