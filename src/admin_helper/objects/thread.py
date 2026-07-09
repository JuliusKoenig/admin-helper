import threading
import time
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Union, Any

from admin_helper.objects.starter import StartObject


@dataclass
class ThreadObject(StartObject):
    lock: threading.Lock = field(default_factory=threading.Lock,
                                 init=False,
                                 repr=False,
                                 metadata={"frozen": True})
    thread: threading.Thread = field(default=None,
                                     init=False,
                                     repr=False,
                                     metadata={"frozen": True})
    loop: bool = field(init=False,
                       repr=False,
                       metadata={"frozen": True})
    loop_delay: int = field(init=False,
                            repr=False,
                            metadata={"frozen": True})

    def __init_subclass__(cls,
                          *,
                          loop: bool = False,
                          loop_delay: int = 1,
                          **kwargs):
        super().__init_subclass__(**kwargs)

        # loop
        cls.loop = loop

        # loop_delay
        cls.loop_delay = loop_delay

    def __post_init__(self):
        self.thread = threading.Thread(target=self._run,
                                       name=self.name,
                                       daemon=True)
        super().__post_init__()

    def _run(self):
        self.logger.info(f"Starting {self} ...")
        try:
            while True:
                start_time = time.perf_counter()
                try:
                    self.run()
                except Exception as e:
                    self.logger.exception(f"Exception occurred: \n{e}")
                if not self.loop:
                    break
                elapsed_time = time.perf_counter() - start_time
                if self.loop_delay > elapsed_time:
                    time.sleep(self.loop_delay - elapsed_time)
        except KeyboardInterrupt:
            self.logger.info(f"Stopping {self} ...")

    @abstractmethod
    def run(self):
        ...

    def start(self) -> None:
        super().start()
        self.thread.start()
