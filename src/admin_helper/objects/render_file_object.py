import getpass
import sys
from dataclasses import dataclass, field
import os
import platform

from pathlib import Path
from typing import Any, Union, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from admin_helper import __name__ as __module_name__
from admin_helper.settings import settings
from admin_helper.objects.base_object import BaseObject


@dataclass
class RenderFileObject(BaseObject,
                       abstract=True):
    src: Path = field(init=False,
                      metadata={"frozen": True})
    dest: Path = field(init=False,
                       metadata={"frozen": True})
    overwrite: bool = field(init=False,
                            repr=False,
                            metadata={"frozen": True})
    environment_options: dict[str, Any] = field(init=False,
                                                repr=False,
                                                metadata={"frozen": True})

    def __init_subclass__(cls,
                          *,
                          abstract: bool = False,
                          name: str | None = None,
                          parent: Union["BaseObject", Any, None] = None,
                          src: str | Path,
                          dest: str | Path,
                          overwrite: bool = False,
                          environment_options: dict[str, Any] | None = None,
                          **kwargs):
        super().__init_subclass__(abstract=abstract,
                                  name=name,
                                  parent=parent,
                                  **kwargs)

        # src
        if not isinstance(src, Path):
            src = Path(src)
        if not src.is_file():
            module = sys.modules[cls.__module__]
            if module.__file__ is None:
                raise AttributeError("__file__ not defined")
            module_file = Path(module.__file__).resolve()
            module_dir = module_file.parent
            src = module_dir / src
        if not src.is_file():
            raise FileNotFoundError(f"{src} not found.")
        cls.src = src

        # dest
        if not isinstance(dest, Path):
            dest = Path(dest)
        cls.dest = dest

        # overwrite
        cls.overwrite = overwrite

        # environment_options
        if environment_options is None:
            environment_options = {
                "undefined": StrictUndefined,
            }
        cls.environment_options = environment_options

    def _get_environment(self,
                         dry_run: bool = False) -> Environment:
        self.logger.debug(f"Environment options: {self.environment_options}")
        environment_options = self.environment_options.copy()
        environment_options["loader"] = FileSystemLoader(self.src.parent)
        environment = Environment(**environment_options)

        # set filter
        def unix_path(path: str | Path) -> str:
            if isinstance(path, Path):
                path = str(path)
            return path.replace("\\", "/") if platform.system() == "Windows" else path

        environment.filters["unix_path"] = unix_path

        def ensure_path(path: str | Path) -> Path:
            if isinstance(path, str):
                path = Path(path)
            if not path.is_dir():
                if dry_run:
                    self.logger.debug(f"[DRY-RUN] Creating directory '{path}' ...")
                else:
                    self.logger.debug(f"Creating directory '{path}' ...")
                    path.mkdir(parents=True, exist_ok=True)
            return path

        environment.filters["ensure_path"] = ensure_path
        return environment

    @property
    def parent_file(self) -> Optional["RenderFileObject"]:
        if isinstance(self.parent, RenderFileObject):
            return self.parent
        return None

    @property
    def data(self) -> dict[str, Any]:
        data = {}

        def add(k: str, v: Any) -> None:
            if k in data.keys():
                raise KeyError(f"Data key '{k}' already exists. Please use a different key name.")
            data[k] = v

        def add_subfile(_subfile):
            add(_subfile.name, _subfile)
            for __subfile in _subfile.subfiles.values():
                add_subfile(__subfile)

        add("__module_name__", __module_name__)
        add("__object_name__", self.name)
        add("__object__", self)
        add(self.name, self)
        add("system", platform.system())
        add("settings", settings)
        add("environment", os.environ)
        add("user", getpass.getuser())
        add("group", os.getgid())
        add("pwd", Path.cwd())

        for subfile in self.subfiles.values():
            add_subfile(subfile)

        parent_file = self.parent_file
        if parent_file is not None:
            add(parent_file.name, self.parent)
            for subfile in parent_file.subfiles.values():
                if subfile is self:
                    continue
                add_subfile(subfile)

        return data

    @property
    def subfiles(self) -> dict[str, "RenderFileObject"]:
        subfiles = {}
        for child_name, child in self.children.items():
            if not isinstance(child, RenderFileObject):
                continue
            subfiles[child_name] = child
        return subfiles

    def test(self) -> dict[str, tuple[bool, str]]:
        result = {}
        for broadcast_result in self.broadcast_call("test"):
            result.update(broadcast_result)
        try:
            self.logger.debug(f"Testing file {self} ...")

            # check if input file exist
            if not self.src.is_file():
                raise FileNotFoundError(f"{self.src} not found.")

            # get environment
            environment = self._get_environment(dry_run=True)

            # get template
            template = environment.get_template(self.src.name)

            # render template
            self.logger.debug(f"Data: {self.data}")
            output = template.render(self.data)

            self.logger.debug(f"Output: {output}")

            self.logger.debug(f"File {self} has been tested successfully.")
            result[self.name] = (True, "[green]Test passed.[/green]")
        except Exception as e:
            result[self.name] = (False, f"[red]Test failed[/red]: {e}")
            self.logger.error(f"Testing file {self} failed: {e}")
            if settings.debug:
                raise e

        return result

    def render(self) -> dict[str, tuple[bool, str]]:
        result = {}
        for broadcast_result in self.broadcast_call("render"):
            result.update(broadcast_result)
        try:
            self.logger.debug(f"Rendering file {self} ...")

            # check if input file exist
            if not self.src.is_file():
                raise FileNotFoundError(f"{self.src} not found.")

            # check if output file already exist
            if self.dest.is_file():
                if not self.overwrite:
                    raise FileExistsError(f"{self.dest} already exists. Set overwrite=True to overwrite.")
                self.dest.unlink()
            self.dest.parent.mkdir(parents=True, exist_ok=True)

            # get environment
            environment = self._get_environment()

            # get template
            template = environment.get_template(self.src.name)

            # render template
            self.logger.debug(f"Data: {self.data}")
            output = template.render(self.data)

            self.logger.debug(f"Output: {output}")

            # write output to file
            with self.dest.open(mode="w") as output_file:
                output_file.write(output)

            self.logger.debug(f"File {self} has been rendered.")
            result[self.name] = (True, "[green]Render passed.[/green]")
        except Exception as e:
            result[self.name] = (False, f"[red]Render failed[/red]: {e}")
            self.logger.error(f"Rendering file {self} failed: {e}")
            if settings.debug:
                raise e

        return result