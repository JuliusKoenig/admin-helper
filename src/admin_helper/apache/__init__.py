import getpass
from dataclasses import dataclass, field
from pathlib import Path

from admin_helper.render_file import RenderFile
from admin_helper.settings import settings
from admin_helper.supervisor import SupervisorProgram, SupervisorService


@dataclass
class ApacheMimeTypeFile(RenderFile,
                         name="apache_mime_file",
                         src="mime.types.j2",
                         dest=settings.config_directory / "apache" / "mime.types",
                         overwrite=True):
    ...

@dataclass
class _ApacheService(RenderFile,
                     name="apache",
                     src="apache.conf.j2",
                     dest=settings.config_directory / "apache" / "apache.conf",
                     overwrite=True,
                     subfiles=[ApacheMimeTypeFile]):
    __str_name__ = "ApacheService"

    binary_path: Path = field(default=settings.apache.binary_path)
    module_directory_path: Path = field(default=settings.apache.module_directory_path)
    pid_file_path: Path = field(default=settings.run_directory / "apache" / "apache.pid")
    server_root: Path = field(default=settings.var_directory / "lib" / "apache")
    document_root: Path = field(default=settings.var_directory / "www")
    mime_types_file_path: Path = field(default=settings.config_directory / "apache" / "mime.types")
    host: str = field(default=settings.apache.host)
    port: int = field(default=settings.apache.port)
    user: str = field(default=settings.apache.user)
    group: str = field(default=settings.apache.group)

    @property
    def supervisor_program(self) -> SupervisorProgram:
        return SupervisorProgram(name="apache",
                                 command=f"{self.binary_path.absolute()} -DFOREGROUND -f {self.dest.absolute()}",
                                 cwd=self.server_root.absolute(),
                                 user=getpass.getuser(),
                                 autostart=True,
                                 autorestart=True)


ApacheService = _ApacheService()
SupervisorService.add_program(ApacheService.supervisor_program)

__all__ = ["ApacheService"]
