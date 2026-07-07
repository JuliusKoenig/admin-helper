import getpass
import logging
from dataclasses import dataclass, field
from pathlib import Path

from supervisor.options import ServerOptions
from supervisor.states import SupervisorStates
from supervisor.loggers import LevelsByName
from supervisor.supervisord import go as supervisord_go

from admin_helper import __name__ as __package_name__
from admin_helper.helper import render_file
from admin_helper.logger import logger
from admin_helper.settings import settings


class SupervisorServerOptions(ServerOptions):
    logger: logging.Logger

    def make_logger(self):
        self.logger = supervisor.logger  # self.loglevel)
        self.logger.blather = lambda _msg, **kw: self.logger.log(LevelsByName.BLAT, _msg, **kw)
        self.logger.trace = lambda _msg, **kw: self.logger.log(LevelsByName.TRAC, _msg, **kw)
        for msg in self.parse_criticals:
            self.logger.critical(msg)
        for msg in self.parse_warnings:
            self.logger.warning(msg)
        for msg in self.parse_infos:
            self.logger.info(msg)


@dataclass
class SupervisorService:
    @dataclass
    class Program:
        name: str = field()
        command: str = field()
        cwd: str = field(default_factory=Path.cwd)
        user: str = field(default_factory=getpass.getuser)
        autostart: bool = field(default=True)
        autorestart: bool = field(default=True)

        def __post_init__(self):
            supervisor._programs.append(self)

    config_file_path: Path = field(default=settings.config_directory / "supervisord.conf")
    _programs: list[Program] = field(default_factory=list,
                                     init=False)
    pid_file_path: Path = field(default=settings.run_directory / "supervisord" / "supervisord.pid")
    socket_file_path: Path = field(default=settings.run_directory / "supervisord" / "supervisord.sock")
    dashboard: bool = field(default=settings.supervisor.dashboard)
    dashboard_host: str = field(default=settings.supervisor.dashboard_host)
    dashboard_port: int = field(default=settings.supervisor.dashboard_port)

    def __post_init__(self):
        # setup logging
        self.logger = logging.getLogger(f"{__package_name__}.supervisor.main")
        self.logger.parent = logger

    def render_config_files(self):
        self.logger.debug(f"Rendering supervisord config ...")
        render_file(input_file=Path(__file__).parent / "supervisord.conf.j2",
                    output_file=self.config_file_path,
                    overwrite=True,
                    **{"supervisor": self})
        self.logger.debug(f"Supervisord config rendered successfully.")

    @property
    def programs(self) -> tuple[Program, ...]:
        return tuple(self._programs)

    def start(self) -> None:
        self.render_config_files()

        # ensure pid file parent directory exists
        self.pid_file_path.parent.mkdir(parents=True, exist_ok=True)

        first = True
        while 1:
            options = SupervisorServerOptions()
            options.realize(["-c",
                             self.config_file_path,
                             "-n"], doc=__doc__)
            options.first = first
            options.test = False
            self.logger.debug(f"Starting supervisor ...")
            supervisord_go(options)
            options.close_httpservers()
            options.close_logger()
            first = False
            if options.mood < SupervisorStates.RESTARTING:
                break

        # clean up pid file if exist
        if settings.supervisord.pid_file_path.is_file():
            settings.supervisord.pid_file_path.unlink()


supervisor = SupervisorService()


class MyProgram(supervisor.Program):
    ...


my_program = MyProgram(name="test",
                       command="sleep infinity")
