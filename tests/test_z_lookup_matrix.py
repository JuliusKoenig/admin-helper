from __future__ import annotations

import pytest

from admin_helper.exceptions import ObjectTreeLoopError
from admin_helper.objects import BaseObject
from admin_helper.objects.field import object_dataclass
from admin_helper.objects.registry import _ObjectRegistry


def _build_lookup_registry() -> tuple[
    _ObjectRegistry,
    type[BaseObject],
    type[BaseObject],
    type[BaseObject],
    type[BaseObject],
]:
    registry = _ObjectRegistry()

    @object_dataclass
    class Root(BaseObject):
        pass

    @object_dataclass
    class Branch(BaseObject):
        pass

    @object_dataclass
    class SpecializedBranch(Branch):
        pass

    @object_dataclass
    class Leaf(BaseObject):
        pass

    registry._register(name="lookup_root_a", cls=Root, abstract=False)
    registry._register(name="lookup_root_b", cls=SpecializedBranch, abstract=False)
    registry._register(name="branch", cls=Branch, abstract=False, parent=Root)
    registry._register(name="nested_leaf", cls=Leaf, abstract=False, parent=Branch)

    @object_dataclass
    class RootLeaf(Leaf):
        pass

    registry._register(
        name="root_leaf", cls=RootLeaf, abstract=False, parent=SpecializedBranch
    )
    registry.instantiate_all()
    return registry, Root, Branch, SpecializedBranch, Leaf


def test_registry_name_lookup_supports_full_and_every_unique_suffix_path() -> None:
    registry, Root, Branch, SpecializedBranch, Leaf = _build_lookup_registry()
    (root,) = registry.get_by_type(Root)
    branch = next(item for item in registry.get_by_type(Branch) if type(item) is Branch)
    specialized = registry.get_by_type(SpecializedBranch)[0]
    leaves = registry.get_by_type(Leaf)
    nested_leaf = next(item for item in leaves if item.parent is branch)
    root_leaf = next(item for item in leaves if item.parent is specialized)

    assert registry.get_by_name("lookup_root_a") is root
    assert registry.get_by_name("lookup_root_a.branch") is branch
    assert registry.get_by_name("lookup_root_a.branch.nested_leaf") is nested_leaf
    assert registry.get_by_name("branch.nested_leaf") is nested_leaf
    assert registry.get_by_name("lookup_root_b.root_leaf") is root_leaf

    assert registry.get_by_name("nested_leaf", Leaf) is nested_leaf
    assert registry.get_by_name("root_leaf", Leaf) is root_leaf
    with pytest.raises(TypeError):
        registry.get_by_name("lookup_root_a.branch", Leaf)
    with pytest.raises(KeyError):
        registry.get_by_name("missing")


def test_registry_wildcard_lookup_covers_segment_and_recursive_variants() -> None:
    registry, Root, Branch, SpecializedBranch, Leaf = _build_lookup_registry()
    root = registry.get_by_type(Root)[0]
    branch = registry.get_by_type(Branch)[0]
    specialized = registry.get_by_type(SpecializedBranch)[0]
    leaves = registry.get_by_type(Leaf)
    nested_leaf = next(item for item in leaves if item.parent is branch)
    root_leaf = next(item for item in leaves if item.parent is specialized)

    assert registry.find_by_name("lookup_root_a.*") == (branch,)
    assert registry.find_by_name("lookup_root_a.*.*") == (nested_leaf,)
    assert registry.find_by_name("lookup_root_a.**") == (root, branch, nested_leaf)
    assert registry.find_by_name("**.*_leaf") == (nested_leaf, root_leaf)
    assert registry.find_by_name("*.*_leaf") == (nested_leaf, root_leaf)
    assert registry.find_by_name("lookup_root_?.**") == (
        root,
        branch,
        nested_leaf,
        specialized,
        root_leaf,
    )
    assert registry.find_by_name("**", Leaf) == (nested_leaf, root_leaf)
    assert registry.find_by_name("missing.**") == ()


def test_object_child_navigation_supports_relative_and_absolute_paths() -> None:
    registry, Root, Branch, SpecializedBranch, Leaf = _build_lookup_registry()
    root = registry.get_by_type(Root)[0]
    branch = registry.get_by_type(Branch)[0]
    nested_leaf = next(
        item for item in registry.get_by_type(Leaf) if item.parent is branch
    )

    assert root.get_child_by_name("branch") is branch
    assert root.get_child_by_name("branch.nested_leaf") is nested_leaf
    assert root.get_child_by_name("lookup_root_a.branch") is branch
    assert (
        root.get_child_by_name("lookup_root_a.branch.nested_leaf", Leaf) is nested_leaf
    )
    assert branch.get_child_by_name("nested_leaf") is nested_leaf
    assert branch.get_child_by_name("lookup_root_a.branch.nested_leaf") is nested_leaf
    assert root.get_child_by_name("nested_leaf") is None
    assert root.get_child_by_name("missing") is None

    with pytest.raises(TypeError):
        root.get_child_by_name("branch", Leaf)
    with pytest.raises(ValueError, match="empty"):
        root.get_child_by_name("   ")


def test_type_lookup_includes_subclasses_and_child_type_lookup_is_direct_only() -> None:
    registry, Root, Branch, SpecializedBranch, Leaf = _build_lookup_registry()
    root = registry.get_by_type(Root)[0]
    branch = registry.get_by_type(Branch)[0]
    specialized = registry.get_by_type(SpecializedBranch)[0]
    nested_leaf = next(
        item for item in registry.get_by_type(Leaf) if item.parent is branch
    )

    assert registry.get_by_type(Branch) == (branch, specialized)
    assert root.get_child_by_type(Branch) == (branch,)
    assert root.get_child_by_type(Leaf) == ()
    assert branch.get_child_by_type(Leaf) == (nested_leaf,)


def test_parent_and_descendant_navigation_detects_corrupted_cycles() -> None:
    registry, Root, Branch, SpecializedBranch, Leaf = _build_lookup_registry()
    root = registry.get_by_type(Root)[0]
    branch = registry.get_by_type(Branch)[0]

    assert branch.root_parent is root
    assert root.children_flat[0] is branch

    object.__setattr__(root, "parent", branch)
    try:
        with pytest.raises(ObjectTreeLoopError, match="Parent loop"):
            root.root_parent
    finally:
        object.__setattr__(root, "parent", None)

    branch._children.append(root)
    try:
        with pytest.raises(ObjectTreeLoopError, match="Child loop"):
            root.children_flat
    finally:
        branch._children.remove(root)
