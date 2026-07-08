import getpass
import sys
from dataclasses import dataclass, field
import os
import platform

from pathlib import Path
from typing import Any, Union

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from admin_helper import __name__ as __module_name__
from admin_helper.types.base_object import BaseObject
from admin_helper.logger import logger
from admin_helper.settings import settings


@dataclass
class RenderFile(BaseObject, abstract=True):
    src: Path = field(init=False)
    dest: Path = field(init=False)
    overwrite: bool = field(init=False, default=False)
    environment_options: dict[str, Any] = field(init=False)
    _subfiles: list["RenderFile"] = field(init=False)

    __str_name__: str | None = "RenderFile"
    __str_attrs__ = ["name", "src", "dest"]

    def __init_subclass__(cls,
                          *,
                          abstract: bool = False,
                          name: str | None = None,
                          src: str | Path,
                          dest: str | Path,
                          overwrite: bool = False,
                          environment_options: dict[str, Any] | None = None,
                          subfiles: list["RenderFile"] | None = None,
                          **kwargs):
        super().__init_subclass__(abstract=abstract,
                                  name=name,
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

        # subfiles
        if subfiles is None:
            subfiles = []
        cls._subfiles = subfiles

    def __post_init__(self):
        # add subfiles over interface
        subfiles = self._subfiles
        self._subfiles = []
        self.add_subfile(*subfiles)

        super().__post_init__()

    def _get_environment(self,
                         dry_run: bool = False) -> Environment:
        logger.debug(f"Environment options: {self.environment_options}")
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
                    logger.debug(f"[DRY-RUN] Creating directory '{path}' ...")
                else:
                    logger.debug(f"Creating directory '{path}' ...")
                    path.mkdir(parents=True, exist_ok=True)
            return path
        environment.filters["ensure_path"] = ensure_path
        return environment

    @property
    def data(self) -> dict[str, Any]:
        data = {}

        def add(k: str, v: Any) -> None:
            if k in data.keys():
                raise KeyError(f"Data key '{k}' already exists. Please use a different key name.")
            data[k] = v

        def add_subfile(_subfile):
            add(_subfile.name, _subfile)
            for __subfile in _subfile.subfiles:
                add_subfile(__subfile)

        add("__module_name__", __module_name__)
        add("system", platform.system())
        add("settings", settings)
        add("environment", os.environ)
        add("user", getpass.getuser())
        add("group", os.getgid())
        add("pwd", Path.cwd())
        add(self.name, self)

        for subfile in self._subfiles:
            add_subfile(subfile)

        if self.parent is not None:
            add(self.parent.name, self.parent)
            for subfile in self.parent.subfiles:
                if subfile is self:
                    continue
                add_subfile(subfile)

        return data

    @property
    def subfiles(self) -> tuple["RenderFile", ...]:
        return tuple(self._subfiles)

    def add_subfile(self, *subfiles: Union["RenderFile", type["RenderFile"]]) -> None:
        children = self.create_children(*subfiles)
        self._subfiles.extend(children)
        _ = self.data  # validate data

    def test(self) -> dict[str, tuple[bool, str]]:
        result = {}
        try:
            logger.debug(f"Testing file {self} ...")

            # check if input file exist
            if not self.src.is_file():
                raise FileNotFoundError(f"{self.src} not found.")

            # get environment
            environment = self._get_environment(dry_run=True)

            # get template
            template = environment.get_template(self.src.name)

            # render template
            logger.debug(f"Data: {self.data}")
            output = template.render(self.data)

            logger.debug(f"Output: {output}")

            logger.debug(f"File {self} has been tested successfully.")
            result[self.name] = (True, "[green]Test passed.[/green]")
        except Exception as e:
            result[self.name] = (False, f"[red]Test failed[/red]: {e}")

        # test subfiles
        for subfile in self.subfiles:
            result.update(subfile.test())

        return result

    def render(self) -> dict[str, tuple[bool, str]]:
        result = {}
        try:
            logger.debug(f"Rendering file {self} ...")

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
            logger.debug(f"Data: {self.data}")
            output = template.render(self.data)

            logger.debug(f"Output: {output}")

            # write output to file
            with self.dest.open(mode="w") as output_file:
                output_file.write(output)

            logger.debug(f"File {self} has been rendered.")
            result[self.name] = (True, "[green]Render passed.[/green]")
        except Exception as e:
            result[self.name] = (False, f"[red]Render failed[/red]: {e}")

        # render subfiles
        for subfile in self.subfiles:
            result.update(subfile.render())

        return result
