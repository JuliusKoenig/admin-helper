from dataclasses import dataclass

from admin_helper.objects.admin_helper.logger import AdminHelperLogger
from admin_helper.objects.starter import StartObject
from admin_helper.objects.render_file import RenderFileObject
from admin_helper.settings import AdminHelperSettings


@dataclass
class AdminHelper(StartObject, RenderFileObject,
                  name="admin_helper",
                  logger=AdminHelperLogger,
                  src="README.md.j2",
                  dest=AdminHelperSettings.base_directory / "README.md",
                  overwrite=True):
    ...


AdminHelper: AdminHelper = AdminHelper()
