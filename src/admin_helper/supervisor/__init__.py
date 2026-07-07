import getpass
import logging
from dataclasses import dataclass, field
from logging import LogRecord
from pathlib import Path

from supervisor.options import ServerOptions
from supervisor.states import SupervisorStates
from supervisor.loggers import LevelsByName
from supervisor.supervisord import go as supervisord_go

from admin_helper import __name__ as __package_name__
from admin_helper.logger import logger as main_logger
from admin_helper.render_file import RenderFile
from admin_helper.settings import settings


class SupervisorLoggerFilter(logging.Filter):
    logger: "SupervisorLogger"

    def filter(self, record: LogRecord) -> bool:
        if record.msg in ["Server 'inet_http_server' running without any HTTP authentication checking",
                          "Server 'unix_http_server' running without any HTTP authentication checking"]:
            return False
        return True

class SupervisorLogger(logging.Logger):
    def __init__(self):
        super().__init__(name=f"{__package_name__}.supervisor.main")
        self.parent = main_logger
        _filter = SupervisorLoggerFilter()
        _filter.logger = self
        self.addFilter(_filter)


        # implement required methods for supervisor logging interface
        self.blather = lambda msg, *a, **kw: self._log(LevelsByName.DEBG, msg, a, **{"stacklevel": 2, **kw})
        self.trace = lambda msg, *a, **kw: self._log(LevelsByName.DEBG, msg, a, **{"stacklevel": 2, **kw})
        self.close = lambda: None

        self.filter_msgs = []


logger = SupervisorLogger()


class SupervisorServerOptions(ServerOptions):
    logger: logging.Logger

    def make_logger(self):
        self.logger = logger
        for msg in self.parse_criticals:
            self.logger.critical(msg)
        for msg in self.parse_warnings:
            self.logger.warning(msg)
        for msg in self.parse_infos:
            self.logger.info(msg)


@dataclass
class SupervisorProgram:
    name: str = field()
    command: str = field()
    cwd: str = field(default_factory=Path.cwd)
    user: str = field(default_factory=getpass.getuser)
    autostart: bool = field(default=True)
    autorestart: bool = field(default=True)


@dataclass
class SupervisorService(RenderFile,
                        name="supervisor",
                        src="supervisord.conf.j2",
                        dest=settings.config_directory / "supervisord.conf",
                        overwrite=True):
    _programs: list[SupervisorProgram] = field(default_factory=list,
                                               init=False)
    pid_file_path: Path = field(default=settings.run_directory / "supervisord" / "supervisord.pid")
    socket_file_path: Path = field(default=settings.run_directory / "supervisord" / "supervisord.sock")
    dashboard: bool = field(default=settings.supervisor.dashboard)
    dashboard_host: str = field(default=settings.supervisor.dashboard_host)
    dashboard_port: int = field(default=settings.supervisor.dashboard_port)

    @property
    def programs(self) -> tuple[SupervisorProgram, ...]:
        return tuple(self._programs)

    def start(self) -> None:
        self.render()

        # ensure pid file parent directory exists
        self.pid_file_path.parent.mkdir(parents=True, exist_ok=True)

        first = True
        while 1:
            options = SupervisorServerOptions()
            options.realize(["-c",
                             self.dest,
                             "-n"], doc=__doc__)
            options.first = first
            options.test = False
            logger.debug(f"Starting supervisor ...")
            supervisord_go(options)
            options.close_httpservers()
            options.close_logger()
            first = False
            if options.mood < SupervisorStates.RESTARTING:
                break

        # clean up pid file if exist
        if self.pid_file_path.is_file():
            self.pid_file_path.unlink()


SupervisorService = SupervisorService()

__all__ = ["SupervisorService", "SupervisorProgram"]

# class MyProgram(SupervisorProgram):
#     ...
#
#
# my_program = MyProgram(name="test",
#                        command="sleep infinity")
