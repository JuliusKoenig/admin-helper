import logging
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Union, Optional

from admin_helper import __name__ as __module_name__
from admin_helper.logger import logger


@dataclass
class BaseObject(ABC):
    name: str = field(init=False)
    _logger: logging.Logger | None = field(default=None)
    _parent: Optional["BaseObject"] = field(default=None, init=False)

    __str_name__: str | None = "BaseObject"
    __str_attrs__ = ["name"]
    __children_attrs__ = []

    def __str__(self) -> str:
        return f"{self.__str_name__}(" + ", ".join(f"{attr}={getattr(self, attr)}" for attr in self.__str_attrs__) + ")"

    def __init_subclass__(cls,
                          *,
                          abstract: bool = False,
                          name: str | None = None,
                          **kwargs):
        super().__init_subclass__(**kwargs)

        # abstract
        if abstract:
            return

        # name
        if name is None:
            name = cls.__name__.lower()
        cls.name = name

    def __post_init__(self):
        if self._logger is None:
            self._logger = logging.Logger(f"{__module_name__}.{self.name}")
            self._logger.parent = logger
        logger.debug(f"Initialized {self}")

    @property
    def logger(self) -> logging.Logger:
        if self._logger is None:
            raise RuntimeError(f"{self.__class__.__name__} is not initialized.")
        return self._logger

    @property
    def parent(self) -> Optional["BaseObject"]:
        return self._parent

    @property
    def children(self) -> list["BaseObject"]:
        children = []
        for children_attr in self.__children_attrs__:
            additional_children = getattr(self, children_attr)
            for additional_child in additional_children:
                if additional_child in children:
                    continue
                children.append(additional_child)
        return children

    def create_children(self,
                         *children: Union["BaseObject", type["BaseObject"]]) -> Union[
        "BaseObject", Any, list[Union["BaseObject", Any]]]:
        result = []
        for child in children:
            if not isinstance(child, BaseObject):
                if issubclass(child, BaseObject):
                    child = child()
                else:
                    raise TypeError(f"{self.__class__.__name__} is not a subclass of {BaseObject.__name__}")

            child._parent = self
            if child in self.children:
                raise RuntimeError(f"'{child}' already added.")
            result.append(child)
        return result
