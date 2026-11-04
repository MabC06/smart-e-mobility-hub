"""Import boundaries between the packages in ``src/`` (NFR-22, D-003, CONTRIBUTING 9.2).

The rules, read from the source files without running them:

1. ``core`` imports none of the module packages (it never calls up into a module; it defines
   ports that modules implement).
2. A module package imports no other module package. Modules meet through ``core``.
3. A module imports from ``core`` only the public surface listed in ``PUBLIC_CORE``; the rest
   (``core.services``, ``core.repository.sql`` ...) is internal and may change without notice.
4. ``src/main.py`` is the composition root and may import everything.

Owner: M1 (NFR-22). The checker is tested on small made-up sources below, so a rule that stops
working is noticed even while the module packages are still empty.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
MODULES = frozenset(
    {"reservation", "charging", "allocation", "monitoring", "simulation", "ui", "iot_sim"}
)

# What a module may import from core (core-api-spec.md: facade, views, results, events, the data
# types in them, the ports, and the pieces a module needs to register its own tables).
PUBLIC_CORE = frozenset(
    {
        "core",
        "core.facade",
        "core.views",
        "core.result",
        "core.errors",
        "core.events",
        "core.actor",
        "core.config",
        "core.clock",
        "core.ids",
        "core.sensors",
        "core.seed",
        "core.providers",
        "core.domain.enums",
        "core.domain.entities",
        "core.domain.invariants",
        "core.services.transition_ctx",
        "core.services.snapshot",
        "core.repository.base",
        "core.repository.memory",
        "core.repository.schema",
    }
)


def _absolute(module: str | None, level: int, package: tuple[str, ...]) -> str | None:
    """The dotted name an import statement refers to, or None if it leaves ``src``."""
    if level == 0:
        return module
    if level - 1 > len(package) - 1:
        return None
    base = package[: len(package) - (level - 1)]
    return ".".join([*base, module] if module else base)


def _is_module(name: str) -> bool:
    path = SRC.joinpath(*name.split("."))
    return path.is_dir() or path.with_suffix(".py").is_file()


def _imports(tree: ast.AST, package: tuple[str, ...]) -> list[tuple[int, str]]:
    """(line, dotted name) of every import. ``from core import services`` also gives
    ``core.services``, because the imported name is a module there."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(node.module, node.level, package)
            if base is None:
                found.append((node.lineno, "<outside src>"))
                continue
            found.append((node.lineno, base))
            found += [
                (node.lineno, f"{base}.{alias.name}")
                for alias in node.names
                if _is_module(f"{base}.{alias.name}")
            ]
        elif isinstance(node, ast.Call):
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
            if name in {"__import__", "import_module"}:
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.append((node.lineno, first.value))
                else:
                    found.append((node.lineno, "<computed name>"))
    return found


def violations(owner: str, package: tuple[str, ...], source: str) -> list[str]:
    """What is wrong with the imports of one file of package ``owner``."""
    problems: list[str] = []
    for line, name in _imports(ast.parse(source), package):
        top = name.split(".")[0]
        if name in {"<outside src>", "<computed name>"}:
            problems.append(f"line {line}: {name} import cannot be checked")
        elif owner == "core":
            if top in MODULES:
                problems.append(f"line {line}: core must not import {name}")
        elif top in MODULES and top != owner:
            problems.append(f"line {line}: {owner} must not import {name} (use core)")
        elif top == "core" and name not in PUBLIC_CORE:
            problems.append(f"line {line}: {name} is not part of core's public surface")
    return problems


def _source_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for package in sorted(p for p in SRC.iterdir() if p.is_dir() and p.name != "__pycache__"):
        files += [(package.name, path) for path in sorted(package.rglob("*.py"))]
    return files


def _check_tree(owner: str, path: Path) -> list[str]:
    package = (owner, *path.relative_to(SRC / owner).parts[:-1])
    found = violations(owner, package, path.read_text(encoding="utf-8"))
    return [f"{path.relative_to(SRC)}: {problem}" for problem in found]


# ------------------------------------------------------------------ the real source tree


def test_src_holds_only_known_packages():
    names = {p.name for p in SRC.iterdir() if p.is_dir() and p.name != "__pycache__"}

    assert names <= {"core"} | MODULES, (
        f"unknown package(s) {sorted(names - {'core'} - MODULES)} in src/: "
        "add them to MODULES in this test and to the README layout"
    )


def test_no_package_breaks_the_import_rules():
    problems = [problem for owner, path in _source_files() for problem in _check_tree(owner, path)]

    assert problems == []


def test_the_check_really_reads_the_core_files():
    core_files = [path for owner, path in _source_files() if owner == "core"]

    assert len(core_files) > 30  # a check that scans nothing would pass for the wrong reason


def test_every_public_core_name_exists():
    """The list above must not drift from the code: a renamed file is noticed here."""
    for name in sorted(PUBLIC_CORE):
        relative = Path(*name.split("."))
        assert (SRC / relative).is_dir() or (SRC / relative.with_suffix(".py")).is_file(), name


# ------------------------------------------------------------------ the checker itself

OWN = ("reservation",)
INTERNAL = "is not part of core's public surface"

FORBIDDEN = [
    ("core", ("core",), "import reservation", ["line 1: core must not import reservation"]),
    (
        "core",
        ("core", "services"),
        "from charging.queue import Queue",
        ["line 1: core must not import charging.queue"],
    ),
    (
        "reservation",
        OWN,
        "import charging",
        ["line 1: reservation must not import charging (use core)"],
    ),
    (
        "ui",
        ("ui", "views"),
        "from monitoring.incidents import Incident",
        ["line 1: ui must not import monitoring.incidents (use core)"],
    ),
    (
        "reservation",
        OWN,
        "from core.services.commands import StateCommands",
        [f"line 1: core.services.commands {INTERNAL}"],
    ),
    ("reservation", OWN, "import core.repository.sql", [f"line 1: core.repository.sql {INTERNAL}"]),
    ("reservation", OWN, "from core import services", [f"line 1: core.services {INTERNAL}"]),
    (
        "reservation",
        OWN,
        "import importlib\nimportlib.import_module('charging')",
        ["line 2: reservation must not import charging (use core)"],
    ),
    (
        "reservation",
        OWN,
        "__import__(name)",
        ["line 1: <computed name> import cannot be checked"],
    ),
    (
        "reservation",
        OWN,
        "from .. import other",
        ["line 1: <outside src> import cannot be checked"],
    ),
]

ALLOWED = [
    ("reservation", OWN, "from core.facade import CoreFacade"),
    ("reservation", OWN, "from core.domain.enums import VehicleEvent, VehicleState"),
    ("reservation", OWN, "from core.repository.schema import TableSpec, metadata"),
    ("reservation", OWN, "import core"),
    ("reservation", OWN, "import sqlalchemy\nimport os\nfrom datetime import datetime"),
    ("reservation", ("reservation", "api"), "from reservation.service import X"),
    ("reservation", ("reservation", "api"), "from . import helpers\nfrom ..model import Y"),
    ("core", ("core", "services"), "from core.domain.entities import Hub"),
    ("core", ("core",), "import sqlalchemy"),
    ("core", ("core", "api"), "from . import schemas\nfrom core.api.app import create_app"),
    ("iot_sim", ("iot_sim",), "from core.sensors import SensorEvent\nfrom core.seed import X"),
]


@pytest.mark.parametrize(("owner", "package", "source", "expected"), FORBIDDEN)
def test_the_checker_flags_what_the_rules_forbid(owner, package, source, expected):
    assert violations(owner, package, source) == expected


@pytest.mark.parametrize(("owner", "package", "source"), ALLOWED)
def test_the_checker_accepts_what_the_rules_allow(owner, package, source):
    assert violations(owner, package, source) == []
