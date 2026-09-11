"""Guardrails for statblocks_v1 package dependency direction.

Declared graph:

- domain → standard library and Pydantic only
- application → domain (and bare ``statblocks_v1`` package root)
- infrastructure → domain / application plus external SDKs
- api → domain / application and FastAPI

Repository-owned packages (``app``, ``routers``, ``firestore``, …) are rejected
by default. Infrastructure may reuse them only through explicit
adapter-specific exceptions.

``statblocks_v1/__init__.py`` must stay domain-safe: domain and application may
import the bare package root for contract metadata.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "statblocks_v1"

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
    "time",
}

FORBIDDEN_LEGACY = (
    "statblockgenerator",
    "StatBlockDetails",
)

# Package-root support modules shared across layers (not domain/application layers).
PACKAGE_SUPPORT_MODULES = frozenset(
    {
        "statblocks_v1.config",
        "statblocks_v1.observability",
    }
)

# Relative path under infrastructure/ → allowed repo-owned import roots.
# Empty in PR12; later adapters opt in explicitly (e.g. firestore client wrap).
INFRASTRUCTURE_ADAPTER_EXCEPTIONS: dict[str, frozenset[str]] = {
    # Self-contained httpx upload; no repository cloudflare package import.
    "runtime.py": frozenset({"shared"}),
}

def _repo_owned_package_roots() -> frozenset[str]:
    """Top-level Python packages/modules owned by this repository (not third-party)."""
    roots: set[str] = set()
    skip_dirs = {
        "statblocks_v1",
        "tests",
        "scripts",
        "Docs",
        "static",
        "build",
        "dungeonmind.egg-info",
        "__pycache__",
    }
    for path in REPO_ROOT.iterdir():
        if path.name.startswith("."):
            continue
        if path.is_dir():
            if path.name in skip_dirs:
                continue
            if (path / "__init__.py").exists() or any(path.glob("*.py")):
                roots.add(path.name)
        elif path.is_file() and path.suffix == ".py" and path.name != "__init__.py":
            roots.add(path.stem)
    return frozenset(roots)


REPO_OWNED_PACKAGE_ROOTS = _repo_owned_package_roots()


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
    # Sibling modules under the package (e.g. testing) are not the domain-safe root.
    return "package_other"


def _assert_domain_safe_imports(path: Path) -> None:
    allowed_roots = STDLIB_AND_TYPING_ROOTS | {"pydantic", "statblocks_v1"}
    for name in _import_names(path):
        root = name.split(".")[0]
        assert root in allowed_roots, f"{path} imports unexpected root {root!r} ({name})"
        assert root not in REPO_OWNED_PACKAGE_ROOTS, (
            f"{path} must not import repository package {root!r}"
        )
        if not name.startswith("statblocks_v1"):
            continue
        if name == "statblocks_v1":
            continue
        layer = _layer_of(name)
        assert layer == "domain", (
            f"{path} may only import bare statblocks_v1 or statblocks_v1.domain.* "
            f"(got {name!r})"
        )


def test_repo_owned_roots_include_known_legacy_surfaces() -> None:
    for expected in (
        "app",
        "routers",
        "firestore",
        "cloudflare",
        "ruleslawyer",
        "cardgenerator",
        "statblockgenerator",
    ):
        assert expected in REPO_OWNED_PACKAGE_ROOTS, (
            f"expected repository-owned root {expected!r} in {sorted(REPO_OWNED_PACKAGE_ROOTS)}"
        )
    assert "statblocks_v1" not in REPO_OWNED_PACKAGE_ROOTS


def test_package_root_init_is_domain_safe() -> None:
    path = PACKAGE_ROOT / "__init__.py"
    _assert_no_legacy(path)
    _assert_domain_safe_imports(path)


def test_domain_imports_only_stdlib_and_pydantic() -> None:
    for path in _python_files("domain"):
        _assert_no_legacy(path)
        _assert_domain_safe_imports(path)


def _assert_application_import(name: str, *, path: Path | str = "<synthetic>") -> None:
    """Enforce application → domain (stdlib/Pydantic allowed; outer layers rejected)."""
    allowed_roots = STDLIB_AND_TYPING_ROOTS | {"pydantic", "statblocks_v1"}
    root = name.split(".")[0]
    assert root in allowed_roots, f"{path} imports unexpected root {root!r} ({name})"
    assert root not in REPO_OWNED_PACKAGE_ROOTS, (
        f"application must not import repository package {root!r} ({path})"
    )
    if name == "statblocks_v1":
        return
    layer = _layer_of(name)
    if layer is not None:
        assert layer in {"domain", "application"}, (
            f"application must not import {name!r} ({path})"
        )


def test_application_depends_only_on_domain() -> None:
    for path in _python_files("application"):
        _assert_no_legacy(path)
        for name in _import_names(path):
            _assert_application_import(name, path=path)


def test_application_import_policy_allows_stdlib_pydantic_rejects_outer_layers() -> None:
    """Stdlib/Pydantic must pass; application → infrastructure/api must fail."""
    for allowed in (
        "typing",
        "datetime",
        "pydantic",
        "statblocks_v1",
        "statblocks_v1.domain",
        "statblocks_v1.domain.errors",
        "statblocks_v1.application",
    ):
        _assert_application_import(allowed)

    for forbidden in (
        "statblocks_v1.infrastructure",
        "statblocks_v1.infrastructure.runtime",
        "statblocks_v1.api",
        "statblocks_v1.api.router",
        "statblocks_v1.testing",
    ):
        with pytest.raises(AssertionError):
            _assert_application_import(forbidden)


def test_infrastructure_depends_only_on_domain_and_application() -> None:
    allowed_layer = {"domain", "application", "infrastructure"}
    for path in _python_files("infrastructure"):
        _assert_no_legacy(path)
        relative = str(path.relative_to(PACKAGE_ROOT / "infrastructure"))
        allowed_repo = INFRASTRUCTURE_ADAPTER_EXCEPTIONS.get(relative, frozenset())
        for name in _import_names(path):
            root = name.split(".")[0]
            if root in REPO_OWNED_PACKAGE_ROOTS:
                assert root in allowed_repo, (
                    f"infrastructure must not import repository package {root!r} "
                    f"unless listed in INFRASTRUCTURE_ADAPTER_EXCEPTIONS "
                    f"({path} → {name}; allowed for this file: {sorted(allowed_repo)})"
                )
                continue
            if name == "statblocks_v1":
                continue
            if name in PACKAGE_SUPPORT_MODULES:
                continue
            layer = _layer_of(name)
            if layer is not None:
                assert layer in allowed_layer, (
                    f"infrastructure must not import layer {layer!r} ({path} → {name})"
                )
            assert not name.startswith("statblocks_v1.api"), (
                f"infrastructure must not import api ({path} → {name})"
            )
            # FastAPI belongs to the api layer, not infrastructure adapters.
            assert root != "fastapi", f"{path} must not import fastapi"


def test_api_depends_on_domain_application_fastapi_and_auth_constants() -> None:
    allowed_roots = STDLIB_AND_TYPING_ROOTS | {
        "asyncio",
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
            if root in REPO_OWNED_PACKAGE_ROOTS:
                assert name == "routers.internal_auth", (
                    f"api may only import routers.internal_auth for shared key constants "
                    f"({path} → {name})"
                )
                continue
            if name == "statblocks_v1":
                continue
            if name in PACKAGE_SUPPORT_MODULES:
                continue
            layer = _layer_of(name)
            if layer is not None:
                assert layer in {"domain", "application", "api"}, (
                    f"api must not import layer {layer!r} ({path} → {name})"
                )


def test_api_does_not_import_legacy_statblockgenerator() -> None:
    for path in _python_files("api"):
        _assert_no_legacy(path)


def test_internal_auth_constants_match_shared_module() -> None:
    """Wire-contract drift guard without importing the routers package at runtime."""
    from statblocks_v1.api.dependencies import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER

    shared = REPO_ROOT / "routers" / "internal_auth.py"
    tree = ast.parse(shared.read_text(encoding="utf-8"))
    values: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    values[target.id] = node.value.value
    assert values.get("INTERNAL_KEY_HEADER") == INTERNAL_KEY_HEADER
    assert values.get("INTERNAL_KEY_ENV") == INTERNAL_KEY_ENV
