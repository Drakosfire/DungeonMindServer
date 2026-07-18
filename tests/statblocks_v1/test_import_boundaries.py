"""Guardrails for statblocks_v1 package dependency direction.

Declared graph:

- domain → standard library and Pydantic only
- application → domain
- infrastructure → domain / application (plus external SDKs later)
- api → domain / application and FastAPI

Narrow exception: ``api`` may import ``routers.internal_auth`` for shared
internal-key constant names only (not legacy generator packages). The
foundation prefers local mirrors of those constants so focused tests avoid
``routers`` package side effects.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "statblocks_v1"

STDLIB_AND_TYPING_ROOTS = {
    "__future__",
    "annotations",
    "typing",
    "dataclasses",
    "datetime",
    "enum",
    "abc",
    "collections",
    "functools",
    "itertools",
    "re",
    "math",
    "decimal",
    "uuid",
    "json",
    "os",
    "sys",
    "secrets",
    "hashlib",
    "unicodedata",
    "pathlib",
    "copy",
}

FORBIDDEN_LEGACY = (
    "statblockgenerator",
    "StatBlockDetails",
)


def _import_names(path: Path) -> set[str]:
    """Return fully-qualified import module names referenced by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _python_files(relative: str) -> list[Path]:
    return sorted((PACKAGE_ROOT / relative).rglob("*.py"))


def _assert_no_legacy(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for token in FORBIDDEN_LEGACY:
        assert token not in text, f"{path} contains forbidden token {token!r}"


def _layer_of(module: str) -> str | None:
    if not module.startswith("statblocks_v1"):
        return None
    parts = module.split(".")
    if len(parts) == 1:
        return "package_root"
    if parts[1] in {"domain", "application", "infrastructure", "api"}:
        return parts[1]
    return "package_root"


def test_domain_imports_only_stdlib_and_pydantic() -> None:
    allowed_roots = STDLIB_AND_TYPING_ROOTS | {"pydantic", "statblocks_v1"}
    for path in _python_files("domain"):
        _assert_no_legacy(path)
        for name in _import_names(path):
            root = name.split(".")[0]
            assert root in allowed_roots, f"{path} imports unexpected root {root!r} ({name})"
            layer = _layer_of(name)
            if layer is not None:
                assert layer in {"domain", "package_root"}, (
                    f"{path} must not import layer {layer!r} ({name})"
                )


def test_application_depends_only_on_domain() -> None:
    allowed_roots = STDLIB_AND_TYPING_ROOTS | {"pydantic", "statblocks_v1"}
    for path in _python_files("application"):
        _assert_no_legacy(path)
        for name in _import_names(path):
            root = name.split(".")[0]
            assert root in allowed_roots, f"{path} imports unexpected root {root!r} ({name})"
            layer = _layer_of(name)
            if layer is not None:
                assert layer in {"domain", "application", "package_root"}, (
                    f"application must not import layer {layer!r} ({path} → {name})"
                )


def test_infrastructure_depends_only_on_domain_and_application() -> None:
    # SDKs are allowed later; forbid upward imports into api and legacy packages.
    forbidden_roots = {"fastapi", "statblockgenerator"}
    for path in _python_files("infrastructure"):
        _assert_no_legacy(path)
        for name in _import_names(path):
            root = name.split(".")[0]
            assert root not in forbidden_roots, f"{path} imports forbidden root {root!r}"
            layer = _layer_of(name)
            if layer is not None:
                assert layer in {"domain", "application", "infrastructure", "package_root"}, (
                    f"infrastructure must not import layer {layer!r} ({path} → {name})"
                )
            assert not name.startswith("statblocks_v1.api"), (
                f"infrastructure must not import api ({path} → {name})"
            )


def test_api_depends_on_domain_application_fastapi_and_auth_constants() -> None:
    allowed_roots = STDLIB_AND_TYPING_ROOTS | {
        "pydantic",
        "fastapi",
        "statblocks_v1",
        "routers",
    }
    for path in _python_files("api"):
        _assert_no_legacy(path)
        for name in _import_names(path):
            root = name.split(".")[0]
            assert root in allowed_roots, f"{path} imports unexpected root {root!r} ({name})"
            layer = _layer_of(name)
            if layer is not None:
                assert layer in {"domain", "application", "api", "package_root"}, (
                    f"api must not import layer {layer!r} ({path} → {name})"
                )
            if root == "routers":
                assert name == "routers.internal_auth", (
                    f"api may only import routers.internal_auth for shared key constants "
                    f"({path} → {name})"
                )


def test_api_does_not_import_legacy_statblockgenerator() -> None:
    for path in _python_files("api"):
        _assert_no_legacy(path)


def test_internal_auth_constants_match_shared_module() -> None:
    """Wire-contract drift guard without importing the routers package at runtime."""
    from pathlib import Path as _Path

    import ast as _ast

    from statblocks_v1.api.dependencies import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER

    shared = _Path(__file__).resolve().parents[2] / "routers" / "internal_auth.py"
    tree = _ast.parse(shared.read_text(encoding="utf-8"))
    values: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, _ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, _ast.Name) and isinstance(node.value, _ast.Constant):
                if isinstance(node.value.value, str):
                    values[target.id] = node.value.value
    assert values.get("INTERNAL_KEY_HEADER") == INTERNAL_KEY_HEADER
    assert values.get("INTERNAL_KEY_ENV") == INTERNAL_KEY_ENV
