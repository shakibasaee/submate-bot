"""Static dependency-boundary tests for clean architecture."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def imported_modules(folder: Path) -> set[str]:
    modules: set[str] = set()
    for path in folder.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    return modules


def test_domain_has_no_framework_or_infrastructure_dependencies() -> None:
    imports = imported_modules(ROOT / "app" / "domain")
    forbidden = ("aiogram", "aiohttp", "redis", "psycopg", "app.infrastructure")
    assert not any(module.startswith(forbidden) for module in imports)


def test_application_has_no_transport_or_concrete_infrastructure_dependencies() -> None:
    imports = imported_modules(ROOT / "app" / "application")
    forbidden = ("aiogram", "aiohttp", "redis", "psycopg", "app.infrastructure")
    assert not any(module.startswith(forbidden) for module in imports)


def test_handlers_do_not_import_concrete_providers_or_databases() -> None:
    imports = imported_modules(ROOT / "app" / "bot" / "handlers")
    forbidden = ("app.infrastructure", "app.services", "redis", "psycopg", "aiohttp")
    assert not any(module.startswith(forbidden) for module in imports)


def test_client_session_is_constructed_only_in_composition_root() -> None:
    offenders: list[Path] = []
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "aiohttp.ClientSession(" in text and path.name != "bootstrap.py":
            offenders.append(path)
    assert offenders == []
