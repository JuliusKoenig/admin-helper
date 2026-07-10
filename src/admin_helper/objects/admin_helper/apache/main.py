from dataclasses import dataclass, field
from pathlib import Path

from admin_helper.objects.admin_helper.apache.route import ApacheRoute, StaticFilesApacheRoute
from admin_helper.settings import AdminHelperSettings
from admin_helper.objects.admin_helper.supervisor.main import Supervisor
from admin_helper.objects.admin_helper.supervisor.program import SupervisorProgram
from admin_helper.objects.render_file import RenderFileObject


@dataclass
class Apache(SupervisorProgram, RenderFileObject,
             name="apache",
             parent=Supervisor,
             src="apache.conf.j2",
             dest=AdminHelperSettings.config_directory / "apache" / "apache.conf",
             overwrite=True,
             command=f"{AdminHelperSettings.apache.binary_path.absolute()} -DFOREGROUND -f {AdminHelperSettings.config_directory.absolute() / 'apache' / 'apache.conf'}",
             cwd=AdminHelperSettings.var_directory / "lib" / "apache",
             user=AdminHelperSettings.apache.user,
             autostart=True,
             autorestart=True):
    binary_path: Path = field(default=AdminHelperSettings.apache.binary_path,
                              repr=False,
                              metadata={"frozen": True})
    module_directory_path: Path = field(default=AdminHelperSettings.apache.module_directory_path,
                                        repr=False,
                                        metadata={"frozen": True})
    pid_file_path: Path = field(default=AdminHelperSettings.run_directory / "apache" / "apache.pid",
                                repr=False,
                                metadata={"frozen": True})
    server_root: Path = field(default=AdminHelperSettings.var_directory / "lib" / "apache",
                              repr=False,
                              metadata={"frozen": True})
    document_root: Path = field(default=AdminHelperSettings.var_directory / "www",
                                repr=False,
                                metadata={"frozen": True})
    mime_types_file_path: Path = field(default=AdminHelperSettings.config_directory / "apache" / "mime.types",
                                       repr=False,
                                       metadata={"frozen": True})
    host: str = field(default=AdminHelperSettings.apache.host,
                      repr=False,
                      metadata={"frozen": True})
    port: int = field(default=AdminHelperSettings.apache.port,
                      repr=False,
                      metadata={"frozen": True})
    group: str = field(default=AdminHelperSettings.apache.group,
                       repr=False,
                       metadata={"frozen": True})

    @property
    def routes(self) -> dict[str, ApacheRoute]:
        routes = {}
        for child in self.root_parent.children_flat:
            if isinstance(child, ApacheRoute):
                routes[child.name] = child
        return routes


Apache: Apache = Apache()


@dataclass
class TestStaticRoute(StaticFilesApacheRoute,
                      name="apache_test_static",
                      parent=Apache,
                      path="/test",
                      document_root=AdminHelperSettings.var_directory / "www" / "test",
                      auth_required=False):
    ...
#
#
# TestStaticRoute: TestStaticRoute = TestStaticRoute()
