import platform
from dataclasses import dataclass, field
from pathlib import Path

from admin_helper.supervisor.main import Supervisor
from admin_helper.supervisor.program import SupervisorProgram
from admin_helper.objects import RenderFileObject
from admin_helper.settings import settings


@dataclass
class _Apache(SupervisorProgram, RenderFileObject,
              name="apache",
              parent=Supervisor,
              src="apache.conf.j2",
              dest=settings.config_directory / "apache" / "apache.conf",
              overwrite=True,
              command=f"{settings.apache.binary_path.absolute()} -DFOREGROUND -f {settings.config_directory.absolute() / 'apache' / 'apache.conf'}",
              cwd=settings.var_directory / "lib" / "apache",
              user=settings.apache.user if platform.system() == "Linux" else None,
              autostart=True,
              autorestart=True):
    binary_path: Path = field(default=settings.apache.binary_path,
                              repr=False,
                              metadata={"frozen": True})
    module_directory_path: Path = field(default=settings.apache.module_directory_path,
                                        repr=False,
                                        metadata={"frozen": True})
    pid_file_path: Path = field(default=settings.run_directory / "apache" / "apache.pid",
                                repr=False,
                                metadata={"frozen": True})
    server_root: Path = field(default=settings.var_directory / "lib" / "apache",
                              repr=False,
                              metadata={"frozen": True})
    document_root: Path = field(default=settings.var_directory / "www",
                                repr=False,
                                metadata={"frozen": True})
    mime_types_file_path: Path = field(default=settings.config_directory / "apache" / "mime.types",
                                       repr=False,
                                       metadata={"frozen": True})
    host: str = field(default=settings.apache.host,
                      repr=False,
                      metadata={"frozen": True})
    port: int = field(default=settings.apache.port,
                      repr=False,
                      metadata={"frozen": True})
    group: str = field(default=settings.apache.group,
                       repr=False,
                       metadata={"frozen": True})


Apache = _Apache()

