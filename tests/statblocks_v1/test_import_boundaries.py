"""Guardrails for statblocks_v1 package dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "statblocks_v1"


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
            if node.module.startswith("statblocks_v1"):
                imports.add(node.module)
    return imports


def _python_files(relative: str) -> list[Path]:
    return sorted((PACKAGE_ROOT / relative).rglob("*.py"))


def test_domain_imports_only_stdlib_and_pydantic() -> None:
    allowed_roots = {
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
        "pydantic",
        "statblocks_v1",
    }
    forbidden_substrings = (
        "fastapi",
        "openai",
        "firebase",
        "firestore",
        "statblockgenerator",
        "cloudflare",
        "routers",
    )

    for path in _python_files("domain"):
        imports = _module_imports(path)
        for name in imports:
            assert not any(bad in name for bad in forbidden_substrings), (
                f"{path} imports forbidden module {name!r}"
            )
            root = name.split(".")[0]
            assert root in allowed_roots or name.startswith("statblocks_v1.domain"), (
                f"{path} imports unexpected root {root!r}"
            )


def test_api_does_not_import_legacy_statblockgenerator() -> None:
    for path in _python_files("api"):
        text = path.read_text()
        assert "statblockgenerator" not in text
        assert "StatBlockDetails" not in text
