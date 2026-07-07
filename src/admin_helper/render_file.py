import getpass
import sys
from dataclasses import dataclass, field
import os
import platform

from pathlib import Path
from typing import Any

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

    def __init_subclass__(cls,
                          *,
                          name: str,
                          src: str | Path,
                          dest: str | Path,
                          overwrite: bool = False,
                          environment_options: dict[str, Any] | None = None,
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

        data["settings"] = settings
        data["environment"] = os.environ
        data["user"] = getpass.getuser()
        data["group"] = os.getgid()
        data["pwd"] = Path.cwd()

        if self.name in data.keys():
            raise KeyError(f"Data key '{self.name}' already exists. Please use a different key name.")
        data[self.name] = self

        # render template
        logger.debug(f"Data: {data}")
        output = template.render(data)

        logger.debug(f"Rendered output: {output}")

        # write output to file
        with self.dest.open(mode="w") as output_file:
            output_file.write(output)

        logger.debug(f"File {self} has been rendered.")
