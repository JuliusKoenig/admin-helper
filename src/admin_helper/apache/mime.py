from dataclasses import dataclass

from admin_helper.apache.main import Apache
from admin_helper.objects import RenderFileObject
from admin_helper.settings import settings


@dataclass
class _ApacheMimeTypeFile(RenderFileObject,
                          name="apache_mime_file",
                          parent=Apache,
                          src="mime.types.j2",
                          dest=settings.config_directory / "apache" / "mime.types",
                          overwrite=True):
    ...


ApacheMimeTypeFile = _ApacheMimeTypeFile()
