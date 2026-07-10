from dataclasses import dataclass, field
from pathlib import Path

from admin_helper.objects.base import BaseObject, is_abstract


@dataclass
class ApacheRoute(BaseObject, abstract=True):
    type: str = field(default=False,
                      init=False,
                      metadata={"frozen": True})
    path: str = field(init=False,
                      metadata={"frozen": True})
    auth_required: bool = field(init=False,
                                metadata={"frozen": True})

    def __init_subclass__(cls,
                          *,
                          type: str | None = None,
                          path: str | None = None,
                          auth_required: bool = True,
                          **kwargs):
        super().__init_subclass__(**kwargs)

        # type
        if type is None:
            raise AttributeError(f"Attribute 'type' of '{cls.__name__}' is required.")
        cls.type = type

        # abstract
        if is_abstract(cls):
            return

        # path
        if path is None:
            raise AttributeError(f"Attribute 'path' of '{cls.__name__}' is required.")
        cls.path = path.rstrip("/") or "/"

        # auth_required
        cls.auth_required = auth_required


@dataclass
class ReverseProxyApacheRoute(ApacheRoute,
                              abstract=True,
                              type="reverse_proxy"):
    target_url: str = field(init=False,
                            metadata={"frozen": True})
    websocket: bool = field(init=False,
                            metadata={"frozen": True})

    def __init_subclass__(cls,
                          *,
                          type: str = "reverse_proxy",
                          target_url: str | None = None,
                          websocket: bool = False,
                          **kwargs):
        super().__init_subclass__(type=type,
                                  **kwargs)

        # abstract
        if is_abstract(cls):
            return

        # target_url
        if target_url is None:
            raise AttributeError(f"Attribute 'target_url' of '{cls.__name__}' is required.")
        cls.target_url = target_url.rstrip("/")

        # websocket
        cls.websocket = websocket


@dataclass
class StaticFilesApacheRoute(ApacheRoute,
                             abstract=True,
                             type="static_files"):
    document_root: Path = field(init=False,
                                metadata={"frozen": True})
    directory_index: str = field(init=False,
                                 metadata={"frozen": True})

    def __init_subclass__(cls,
                          *,
                          type: str = "static_files",
                          document_root: Path | None = None,
                          directory_index: str = "index.html",
                          **kwargs):
        super().__init_subclass__(type=type,
                                  **kwargs)

        # abstract
        if is_abstract(cls):
            return

        # document_root
        if document_root is None:
            raise AttributeError(f"Attribute 'document_root' of '{cls.__name__}' is required.")
        cls.document_root = document_root

        # directory_index
        cls.directory_index = directory_index


@dataclass
class PhpFilesApacheRoute(StaticFilesApacheRoute,
                          type="php_files",
                          abstract=True):
    php_handler: str = field(init=False,
                             metadata={"frozen": True})

    def __init_subclass__(cls,
                          *,
                          type: str = "php_files",
                          php_handler: str = "proxy:unix:/run/php/php-fpm.sock|fcgi://localhost/",
                          **kwargs):
        super().__init_subclass__(type=type,
                                  **kwargs)

        # abstract
        if is_abstract(cls):
            return

        # php_handler
        cls.php_handler = php_handler
