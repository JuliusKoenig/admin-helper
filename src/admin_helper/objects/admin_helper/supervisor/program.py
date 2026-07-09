import getpass
from dataclasses import dataclass, field
from pathlib import Path

from admin_helper.settings import settings
from admin_helper.objects.base import BaseObject


@dataclass
class SupervisorProgram(BaseObject,
                        abstract=True):
    command: str = field(init=False,
                         metadata={"frozen": True})
    stdout_logfile_maxbytes: int = field(init=False,
                                         repr=False,
                                         metadata={"frozen": True})
    stdout_logfile_backups: int = field(init=False,
                                        repr=False,
                                        metadata={"frozen": True})
    cwd: Path = field(init=False,
                      repr=False,
                      metadata={"frozen": True})
    user: str = field(init=False,
                      repr=False,
                      metadata={"frozen": True})
    autostart: bool = field(init=False,
                            repr=False,
                            metadata={"frozen": True})
    autorestart: bool = field(init=False,
                              repr=False,
                              metadata={"frozen": True})

    def __init_subclass__(cls,
                          *,
                          command: str,
                          stdout_logfile_maxbytes: int | None = None,
                          stdout_logfile_backups: int | None = None,
                          cwd: Path | None = None,
                          user: str | None = None,
                          autostart: bool = True,
                          autorestart: bool = True,
                          **kwargs):
        super().__init_subclass__(**kwargs)

        # command
        cls.command = command

        # stdout_logfile_maxbytes
        if stdout_logfile_maxbytes is None:
            stdout_logfile_maxbytes = settings.supervisor.default_logfile_maxbytes
        cls.stdout_logfile_maxbytes = stdout_logfile_maxbytes

        # stdout_logfile_backups
        if stdout_logfile_backups is None:
            stdout_logfile_backups = settings.supervisor.default_logfile_backups
        cls.stdout_logfile_backups = stdout_logfile_backups

        # cwd
        if cwd is None:
            cwd = Path.cwd()
        cls.cwd = cwd

        # user
        if user is None:
            user = getpass.getuser()
        cls.user = user

        # autostart
        cls.autostart = autostart

        # autorestart
        cls.autorestart = autorestart

    @property
    def stdout_logfile_path(self):
        return settings.supervisor.logfile_parent_directory / "programs" / f"{self.name}.log"
