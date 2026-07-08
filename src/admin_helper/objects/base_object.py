import logging
import re
from abc import ABC
from dataclasses import dataclass, field, fields
from typing import TypeVar, Union, Any

from admin_helper import __name__ as __module_name__
from admin_helper.exceptions import BroadcastException
from admin_helper.logger import logger
from admin_helper.settings import settings

T = TypeVar("T", bound="BaseObject")

BROADCAST_METHODS: list[str] = []


@dataclass
class BaseObject(ABC):
    # public attrs
    name: str = field(init=False,
                      metadata={"frozen": True})
    logger: logging.Logger = field(init=False,
                                   repr=False,
                                   metadata={"frozen": True})
    parent: Union["BaseObject", Any, None] = field(default=None,
                                                   init=False,
                                                   repr=False,
                                                   metadata={"frozen": True})

    # private attrs
    _init: bool = field(default=False,
                        init=False,
                        repr=False)
    _children: list[Union["BaseObject", Any]] = field(default_factory=list,
                                                      init=False,
                                                      repr=False)

    def __init_subclass__(cls,
                          *,
                          abstract: bool = False,
                          name: str | None = None,
                          parent: Union["BaseObject", Any, None] = None,
                          **kwargs):
        # abstract
        if abstract:
            for key, value in {"name": name,
                               "parent": parent,
                               **kwargs}.items():
                if value is None:
                    continue
                raise RuntimeError(f"{cls.__name__} is abstract and cannot have '{key}' defined.")
            cls.__abstract__ = True
            return

        # name
        if name is None:
            name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        cls.name = name

        # parent
        cls.parent = parent

    def __post_init__(self):
        # parent
        if self.parent:
            self.parent.add_child(self)

        # logger
        self.logger = logging.Logger(f"{__module_name__}.{self.name}")
        self.logger.parent = logger

        # finalize
        self._init = True
        self.logger.debug(f"Initialized {self}")

    def __setattr__(self,
                    key,
                    value):
        if self._init:
            _field = None
            for f in fields(self):
                if f.name == key:
                    _field = f
                    break
            if _field is not None:
                is_frozen = _field.metadata.get("frozen", False)
                if is_frozen:
                    raise AttributeError(f"Field '{_field.name}' is frozen and cannot be modified.")
        super().__setattr__(key, value)

    def broadcast_call(self,
                       _method_name: str,
                       _wrap_errors: bool = not settings.debug,
                       _stop_on_error: bool = True,
                       **method_kwargs) -> Any:
        self.logger.debug(f"Broadcasting {self} -> {_method_name}")
        result = []
        for child in self.children.values():
            method = getattr(child, _method_name, None)
            if callable(method):
                try:
                    result.append(method(**method_kwargs))
                except Exception as e:
                    self.logger.error(f"Error occurred while broadcasting {self} -> {_method_name}: {e}")
                    if not _wrap_errors:
                        raise e
                    result.append(BroadcastException(self, _method_name, e))
                    if _stop_on_error:
                        result[-1].finalize()
                        raise result[-1]
            else:
                result.append(child.broadcast_call(_method_name=_method_name,
                                                   _wrap_errors=_wrap_errors,
                                                   _stop_on_error=_stop_on_error,
                                                   **method_kwargs))
        if not _wrap_errors and not _stop_on_error:
            final_exception = None
            for broadcast_result in result:
                if isinstance(broadcast_result, BroadcastException):
                    if final_exception is None:
                        final_exception = BroadcastException()
                    final_exception.errors.append(broadcast_result)
            if final_exception is not None:
                final_exception.finalize()
                raise final_exception

        return result

    @property
    def root_parent(self) -> Union["BaseObject", Any]:
        if self.parent is not None:
            return self.parent.root_parent
        else:
            return self

    @property
    def children(self) -> dict[str, Union["BaseObject", Any]]:
        children = {}
        for child in self._children:
            children[child.name] = child
        return children

    def add_child(self,
                  obj: T | type[T],
                  **kwargs) -> T:
        if type(obj) is type:
            return obj(parent=self,
                       **kwargs)
        else:
            if not isinstance(obj, BaseObject):
                raise ValueError(f"{obj} is not an instance of NiceguiAdminType")
            if obj in self._children:
                raise ValueError(f"{obj} is already a child of {self}")
            b_init = getattr(obj, "_init")
            setattr(obj, "_init", False)
            obj.parent = self
            setattr(obj, "_init", b_init)
            self._children.append(obj)
            return obj

    def get_child_by_name(self,
                          name: str) -> T | None:
        if name not in self.children:
            return None
        return self.children[name]

    def get_child_by_type(self,
                          t: type[T]) -> list[T]:
        result = []
        for name, child in self.children.items():
            child_type = type(child)
            if issubclass(child_type, t):
                result.append(child)
        return result
