from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from admin_helper.objects.object import BaseObject
    from admin_helper.objects.registry import _ObjectRegistry


@dataclass(frozen=True, slots=True)
class _ObjectConstructionContext:
    """Framework-owned values available during one registry construction."""

    registry: _ObjectRegistry
    object_name: str
    registration_name: str
    abstract: bool
    parent: BaseObject | None


_construction_context: ContextVar[_ObjectConstructionContext | None] = ContextVar(
    "base_object_construction_context",
    default=None,
)
