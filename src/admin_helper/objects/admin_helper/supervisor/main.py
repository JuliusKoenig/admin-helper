import logging
from dataclasses import dataclass, field
from pathlib import Path

from supervisor.options import ServerOptions
from supervisor.states import SupervisorStates
from supervisor.supervisord import go as supervisord_go

from admin_helper.settings import AdminHelperSettings
from admin_helper.objects.admin_helper.main import AdminHelper
from admin_helper.objects.admin_helper.supervisor.logger import SupervisorLogger
from admin_helper.objects.admin_helper.supervisor.program import SupervisorProgram
from admin_helper.objects.render_file import RenderFileObject


@dataclass
class Supervisor(RenderFileObject,
                 name="supervisor",
                 parent=AdminHelper,
                 logger=SupervisorLogger,
                 src="supervisord.conf.j2",
                 dest=AdminHelperSettings.config_directory / "supervisord.conf",
                 overwrite=True):
    class SupervisorServerOptions(ServerOptions):
        logger: SupervisorLogger | logging.Logger

        def make_logger(self):
            self.logger = Supervisor.logger
            for msg in self.parse_criticals:
                self.logger.critical(msg)
            for msg in self.parse_warnings:
                self.logger.warning(msg)
            for msg in self.parse_infos:
                self.logger.info(msg)

    pid_file_path: Path = field(default=AdminHelperSettings.run_directory / "supervisord" / "supervisord.pid",
                                repr=False,
                                metadata={"frozen": True})
    socket_file_path: Path = field(default=AdminHelperSettings.run_directory / "supervisord" / "supervisord.sock",
                                   repr=False,
                                   metadata={"frozen": True})
    dashboard: bool = field(default=AdminHelperSettings.supervisor.dashboard,
                            repr=False,
                            metadata={"frozen": True})
    dashboard_host: str = field(default=AdminHelperSettings.supervisor.dashboard_host,
                                repr=False,
                                metadata={"frozen": True})
    dashboard_port: int = field(default=AdminHelperSettings.supervisor.dashboard_port,
                                repr=False,
                                metadata={"frozen": True})
    log_listener_script_path: Path = field(default=Path(__file__).parent / "log_listener.py",
                                           repr=False,
                                           metadata={"frozen": True})

    @property
    def programs(self) -> dict[str, SupervisorProgram]:
        subfiles = {}
        for child in self.root_parent.children_flat:
            if not isinstance(child, SupervisorProgram):
                continue
            subfiles[child.name] = child
        return subfiles

    def start(self) -> None:
        self.broadcast_call("start")

        # ensure pid file parent directory exists
        self.pid_file_path.parent.mkdir(parents=True, exist_ok=True)

        first = True
        while 1:
            options = self.SupervisorServerOptions()
            options.realize(["-c",
                             str(self.dest),
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
        if self.pid_file_path.is_file():
            self.pid_file_path.unlink()


Supervisor: Supervisor = Supervisor()
