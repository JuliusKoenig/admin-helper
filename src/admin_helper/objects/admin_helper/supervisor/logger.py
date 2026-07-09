import logging
from logging import LogRecord

from supervisor.loggers import LevelsByName


class SupervisorLogger(logging.Logger):
    class SupervisorLoggerFilter(logging.Filter):
        logger: "SupervisorLogger"

        def filter(self, record: LogRecord) -> bool:
            if record.msg in ["Server 'inet_http_server' running without any HTTP authentication checking",
                              "Server 'unix_http_server' running without any HTTP authentication checking"]:
                return False
            return True

    def __init__(self, name: str):
        super().__init__(name=name)
        _filter = self.SupervisorLoggerFilter()
        _filter.logger = self
        self.addFilter(_filter)

        # implement required methods for supervisor logging interface
        self.blather = lambda msg, *a, **kw: self._log(LevelsByName.DEBG, msg, a, **{"stacklevel": 3, **kw})
        self.trace = lambda msg, *a, **kw: self._log(LevelsByName.DEBG, msg, a, **{"stacklevel": 3, **kw})
        self.close = lambda: None

        self.filter_msgs = []

    def _log(self,
             level,
             msg: str,
             args,
             exc_info=None,
             extra=None,
             stack_info=False,
             stacklevel=2,
             dispatcher=None):
        if extra is None:
            extra = {}
        if dispatcher is not None:
            extra["dispatcher"] = dispatcher

        # replace vars in msg
        try:
            msg = msg % extra
        except KeyError:
            pass
        super()._log(level, msg, args, exc_info, {"markup": False, **(extra or {})}, stack_info, stacklevel)


