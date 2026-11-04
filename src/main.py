"""Composition root: the one place that builds the whole application (architecture-diagram.md, 11).

It reads the settings, builds ``core`` on the database, then lets each module install itself, in a
fixed order. Modules never import this file; this file may import every module.

Run it:

    python -m uvicorn --app-dir src main:create_app --factory --port 8000
    python src/main.py

A module takes part by exposing, in its package ``__init__``:

    def install(core: CoreFacade, app: FastAPI) -> None:
        # register providers:  core.register_provider(ProviderPort.DEMAND_SOURCE, impl)
        # register its tables: core.register_entity(TableSpec(...))  (joins core's transactions)
        # subscribe to events: core.events.subscribe(EventType.HUB_STATUS_CHANGED, handler)
        # mount its routers:   app.include_router(router)

A module folder with no ``install`` (or no code yet) is skipped. Demo data: with
``SEED_ON_START=true`` and an empty database, ``iot_sim.build_network_spec(seed)`` (M8) is loaded.
"""

import importlib
import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.actor import Actor
from core.api import create_app as create_core_app
from core.auth import AuthConfig
from core.clock import Clock
from core.config import CoreConfig
from core.domain.enums import Role
from core.facade import CoreFacade
from core.repository.base import Repository
from core.repository.sql import SqlRepository
from core.result import Err

logger = logging.getLogger("main")

ENVIRONMENTS = ("development", "test", "production-demo")
# Order of installation: a module that reacts to another's events comes after it.
MODULES = ("reservation", "charging", "allocation", "monitoring", "simulation", "ui")
SEEDER = Actor("SIM", Role.OPERATOR, "iot_sim")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SettingsError(ValueError):
    """A setting is missing or wrong. The message names the variable."""


class StartupError(RuntimeError):
    """The application could not start; the message says which part and why."""


# ---------------------------------------------------------------------------------- settings


def read_env_file(path: Path) -> dict[str, str]:
    """Read ``KEY=value`` lines. Comments and empty values are ignored (an empty value means
    "use the default"), quotes around a value are removed."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, raw = text.partition("=")
        raw = raw.strip()
        if raw[:1] in {'"', "'"} and raw.count(raw[0]) >= 2:
            value = raw[1 : raw.index(raw[0], 1)]
        else:
            value = raw.split(" #", 1)[0].split("\t#", 1)[0].strip()
            if value.startswith("#"):
                value = ""
        if value:
            values[key.strip()] = value
    return values


def load_env_file(path: Path, environ: dict[str, str] | None = None) -> None:
    """Put the values of a ``.env`` file into the environment; real variables win."""
    target = os.environ if environ is None else environ
    for key, value in read_env_file(path).items():
        target.setdefault(key, value)


@dataclass(frozen=True, slots=True)
class Settings:
    core: CoreConfig
    auth: AuthConfig
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str = "sqlite://"
    frontend_origin: str | None = None
    seed_on_start: bool = False
    iot_sim_seed: int = 0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ

        def text(name: str, default: str) -> str:
            return (env.get(name) or "").strip() or default

        def number(name: str, default: int, low: int, high: int) -> int:
            raw = text(name, str(default))
            try:
                value = int(raw)
            except ValueError:
                raise SettingsError(f"{name} must be a whole number, got {raw!r}") from None
            if not low <= value <= high:
                raise SettingsError(f"{name} must be between {low} and {high}, got {value}")
            return value

        app_env = text("APP_ENV", "development")
        if app_env not in ENVIRONMENTS:
            raise SettingsError(f"APP_ENV must be one of {ENVIRONMENTS}, got {app_env!r}")
        log_level = text("LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise SettingsError(
                f"LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR, got {log_level!r}"
            )
        database_url = text("DATABASE_URL", "sqlite://")
        if not database_url.startswith("sqlite"):
            raise SettingsError(
                f"DATABASE_URL must be a SQLite URL (sqlite:///data/hub.db), got {database_url!r}"
            )
        seed_text = text("SEED_ON_START", "false").lower()
        if seed_text not in {"true", "false"}:
            raise SettingsError(f"SEED_ON_START must be true or false, got {seed_text!r}")
        try:
            core_config = CoreConfig.from_env(env)
        except ValueError as exc:
            raise SettingsError(str(exc)) from exc
        try:
            auth_config = AuthConfig.from_env(env)
        except ValueError as exc:
            raise SettingsError(str(exc)) from exc
        return cls(
            core=core_config,
            auth=auth_config,
            app_env=app_env,
            host=text("APP_HOST", "127.0.0.1"),
            port=number("APP_PORT", 8000, 1, 65535),
            log_level=log_level,
            database_url=database_url,
            frontend_origin=text("FRONTEND_ORIGIN", "") or None,
            seed_on_start=seed_text == "true",
            iot_sim_seed=number("IOT_SIM_SEED", 0, 0, 2**31 - 1),
        )


# ------------------------------------------------------------------------------ the application


def install_modules(core: CoreFacade, app: FastAPI, names: tuple[str, ...] = MODULES) -> list[str]:
    """Call ``install(core, app)`` of every module that has one. Returns the names installed."""
    installed: list[str] = []
    for name in names:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name == name:
                continue  # the module has no code yet
            raise StartupError(f"module {name!r} could not be imported: {exc}") from exc
        install = getattr(module, "install", None)
        if install is None:
            continue
        try:
            install(core, app)
        except Exception as exc:
            raise StartupError(f"module {name!r} failed to install: {exc}") from exc
        installed.append(name)
        logger.info("module %s installed", name)
    return installed


def seed_network(core: CoreFacade, seed: int) -> None:
    """Load the demo network from the simulator into an empty core."""
    try:
        simulator = importlib.import_module("iot_sim")
    except ModuleNotFoundError as exc:
        raise StartupError("SEED_ON_START needs the iot_sim module (M8)") from exc
    build = getattr(simulator, "build_network_spec", None)
    if build is None:
        raise StartupError("SEED_ON_START needs iot_sim.build_network_spec(seed) -> NetworkSpec")
    result = core.commands.load_network(build(seed), SEEDER)
    if isinstance(result, Err):
        raise StartupError(f"the demo network could not be loaded: {result.message}")
    logger.info("demo network loaded: %s", result.value)


def build_app(
    settings: Settings,
    repository: Repository | None = None,
    clock: Clock | None = None,
    module_names: tuple[str, ...] = MODULES,
) -> FastAPI:
    """Build core on the database, install the modules, return the application."""
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    owns_repository = repository is None
    repo: Repository = (
        repository if repository is not None else SqlRepository.open(settings.database_url)
    )
    try:
        core = CoreFacade(repo, clock, settings.core)
        auth = core.authentication(settings.auth)

        @asynccontextmanager
        async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
            yield
            if owns_repository and isinstance(repo, SqlRepository):
                repo.close()

        app = create_core_app(
            core, auth, expose_docs=settings.app_env != "production-demo", lifespan=lifespan
        )
        if settings.frontend_origin:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=[settings.frontend_origin],
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "Content-Type"],
            )
        if settings.seed_on_start and not core.queries.list_hubs():
            seed_network(core, settings.iot_sim_seed)
        install_modules(core, app, module_names)
    except BaseException:
        if owns_repository and isinstance(repo, SqlRepository):
            repo.close()
        raise
    app.state.core = core
    app.state.auth = auth
    app.state.settings = settings
    return app


def create_app() -> FastAPI:
    """Factory for uvicorn: reads ``.env`` (real environment variables win) and builds the app."""
    load_env_file(PROJECT_ROOT / ".env")
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    try:
        return build_app(settings)
    except StartupError as exc:
        raise SystemExit(f"Startup error: {exc}") from exc


def run() -> None:
    import uvicorn

    load_env_file(PROJECT_ROOT / ".env")
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    uvicorn.run("main:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
