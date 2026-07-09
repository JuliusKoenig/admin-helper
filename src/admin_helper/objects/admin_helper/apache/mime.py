from dataclasses import dataclass

from admin_helper.settings import AdminHelperSettings
from admin_helper.objects.admin_helper.apache.main import Apache
from admin_helper.objects.render_file import RenderFileObject


@dataclass
class ApacheMimeTypeFile(RenderFileObject,
                         name="apache_mime_file",
                         parent=Apache,
                         src="mime.types.j2",
                         dest=AdminHelperSettings.config_directory / "apache" / "mime.types",
                         overwrite=True):
    ...


ApacheMimeTypeFile: ApacheMimeTypeFile = ApacheMimeTypeFile()
