import getpass
import sys
import warnings
from copy import deepcopy
from dataclasses import dataclass, field
import os
import platform

from pathlib import Path
from typing import Any, Union, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from admin_helper.logger import logger
from admin_helper.settings import settings


@dataclass
class RenderFile:
    name: str = field(init=False)
    src: Path = field(init=False)
    dest: Path = field(init=False)
    overwrite: bool = field(init=False, default=False)
    environment_options: dict[str, Any] = field(init=False)
    _subfiles: list["RenderFile"] = field(init=False)
    _parent: Optional["RenderFile"] = field(default=None, init=False)

    def __init_subclass__(cls,
                          *,
                          name: str,
                          src: str | Path,
                          dest: str | Path,
                          overwrite: bool = False,
                          environment_options: dict[str, Any] | None = None,
                          subfiles: list["RenderFile"] | None = None,
                          **kwargs):
        super().__init_subclass__(**kwargs)

        # name
        cls.name = name

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

    @property
    def parent(self) -> Optional["RenderFile"]:
        return self._parent

    @property
    def _data(self) -> dict[str, Any]:
        data = {}

        def add(k: str, v: Any) -> None:
            if k in data.keys():
                raise KeyError(f"Data key '{k}' already exists. Please use a different key name.")
            data[k] = v

        def add_subfile(_subfile):
            add(_subfile.name, _subfile)
            for __subfile in _subfile.subfiles:
                add_subfile(__subfile)

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
        for subfile in subfiles:
            if not isinstance(subfile, RenderFile):
                if issubclass(subfile, RenderFile):
                    subfile = subfile()
                else:
                    raise TypeError(f"subfile must be an instance or subclass of RenderFile, got {type(subfile)}")

            subfile._parent = self
            if subfile in self.subfiles:
                raise RuntimeError(f"'{subfile}' already added.")
            self._subfiles.append(subfile)
            _ = self._data # validate data

    def render(self,
               **data) -> None:
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

        # create file system loader
        self.environment_options["loader"] = FileSystemLoader(self.src.parent)

        # create environment
        logger.debug(f"Environment options: {self.environment_options}")
        environment = Environment(**self.environment_options)

        # set filter
        environment.filters["unix_path"] = lambda path: str(path).replace("\\", "/") if platform.system() == "Windows" else str(path)

        # get template
        template = environment.get_template(self.src.name)

        for key, value in self._data.items():
            if key in data:
                warnings.warn(f"Conflicting data key '{key}' in render() arguments. Overwriting with provided value.")
            data[key] = value

        # render template
        logger.debug(f"Data: {data}")
        output = template.render(data)

        logger.debug(f"Rendered output: {output}")

        # write output to file
        with self.dest.open(mode="w") as output_file:
            output_file.write(output)

        logger.debug(f"File {self} has been rendered.")

        # render subfiles
        for subfile in self.subfiles:
            subfile.render(**data)
