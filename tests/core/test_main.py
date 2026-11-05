"""The composition root (src/main.py): settings, start-up, module installation, demo data."""

import socket
import subprocess
import sys
import time
import types
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

import main
from core.auth import hash_password
from core.config import CoreConfig
from core.domain.enums import Role, VehicleType
from core.events import EventType
from core.providers import ProviderPort
from core.repository.sql import SqlRepository
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec

KEY = "test-secret-key-0123456789"  # test data, not a real secret
ROOT = Path(__file__).resolve().parents[2]


def settings(**changes):
    env = {"SECRET_KEY": KEY, "LOG_LEVEL": "WARNING"}
    env.update(changes)
    return main.Settings.from_env(env)


def demo_spec(seed=0):
    return NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Metro",
                "METRO",
                4,
                1,
                vehicles=(VehicleSpec("V1", "RENT-1", VehicleType.E_BIKE, 80.0),),
            ),
        ),
        users=(
            UserSpec("OP1", "OP-1", Role.OPERATOR, hash_password("pw-operator", 1000)),
            UserSpec("U1", "2452001", Role.STUDENT, hash_password("pw-student", 1000)),
        ),
    )


@pytest.fixture
def fake_simulator(monkeypatch):
    """A stand-in for M8's iot_sim that records how often the demo network was built."""
    module = types.ModuleType("iot_sim")
    module.calls = []

    def build_network_spec(seed):
        module.calls.append(seed)
        return demo_spec(seed)

    module.build_network_spec = build_network_spec
    monkeypatch.setitem(sys.modules, "iot_sim", module)
    return module


def login(client, code, password):
    response = client.post("/auth/login", json={"code": code, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ----------------------------------------------------------------------------------- .env


def test_env_file_values_comments_quotes_and_empty_values(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "PLAIN=value",
                "SPACED =  padded  ",
                "WITH_COMMENT=kept   # dropped",
                "EMPTY=",
                "ONLY_COMMENT=   # nothing",
                'QUOTED="has # hash and spaces"',
                "SINGLE='x y'",
                "no equals sign",
                "URL=sqlite:///data/hub.db",
            ]
        ),
        encoding="utf-8",
    )

    values = main.read_env_file(path)

    assert values == {
        "PLAIN": "value",
        "SPACED": "padded",
        "WITH_COMMENT": "kept",
        "QUOTED": "has # hash and spaces",
        "SINGLE": "x y",
        "URL": "sqlite:///data/hub.db",
    }


def test_a_missing_env_file_is_not_an_error(tmp_path):
    assert main.read_env_file(tmp_path / "nope.env") == {}


def test_real_environment_variables_win_over_the_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=from-file\nB=from-file\n", encoding="utf-8")
    environment = {"A": "from-environment"}

    main.load_env_file(path, environment)

    assert environment == {"A": "from-environment", "B": "from-file"}


def test_the_example_file_can_be_copied_as_it_is_with_only_a_secret_added():
    """.env.example lists names with empty values; every setting must then take its default."""
    assert main.read_env_file(ROOT / ".env.example") == {}
    parsed = main.Settings.from_env({"SECRET_KEY": KEY})
    assert (parsed.app_env, parsed.port, parsed.database_url) == ("development", 8000, "sqlite://")


# -------------------------------------------------------------------------------- settings


def test_defaults():
    parsed = settings()

    assert parsed.app_env == "development"
    assert (parsed.host, parsed.port, parsed.log_level) == ("127.0.0.1", 8000, "WARNING")
    assert parsed.database_url == "sqlite://"
    assert parsed.frontend_origin is None and parsed.seed_on_start is False
    assert parsed.core == CoreConfig()


def test_every_setting_can_be_given():
    parsed = settings(
        APP_ENV="production-demo",
        APP_HOST="0.0.0.0",
        APP_PORT="9000",
        LOG_LEVEL="debug",
        DATABASE_URL="sqlite:///data/hub.db",
        FRONTEND_ORIGIN="http://localhost:5173",
        SEED_ON_START="TRUE",
        IOT_SIM_SEED="42",
        LOW_BATTERY_THRESHOLD="20",
        NEAR_CAPACITY_THRESHOLD="85",
        ACCESS_TOKEN_TTL_MINUTES="15",
        PASSWORD_HASH_ITERATIONS="5000",
    )

    assert (parsed.app_env, parsed.host, parsed.port) == ("production-demo", "0.0.0.0", 9000)
    assert parsed.log_level == "DEBUG" and parsed.database_url == "sqlite:///data/hub.db"
    assert parsed.frontend_origin == "http://localhost:5173"
    assert parsed.seed_on_start is True and parsed.iot_sim_seed == 42
    assert (parsed.core.low_battery_threshold, parsed.core.near_capacity_threshold) == (20.0, 85.0)
    assert (parsed.auth.token_minutes, parsed.auth.hash_iterations) == (15, 5000)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("APP_ENV", "staging"),
        ("APP_PORT", "eighty"),
        ("APP_PORT", "0"),
        ("APP_PORT", "70000"),
        ("LOG_LEVEL", "LOUD"),
        ("DATABASE_URL", "postgresql://user@host/db"),
        ("SEED_ON_START", "maybe"),
        ("IOT_SIM_SEED", "-1"),
        ("IOT_SIM_SEED", "abc"),
        ("LOW_BATTERY_THRESHOLD", "500"),
        ("NEAR_CAPACITY_THRESHOLD", "lots"),
    ],
)
def test_a_wrong_setting_is_refused_with_a_message_that_names_it(name, value):
    with pytest.raises(main.SettingsError) as raised:
        settings(**{name: value})

    assert name in str(raised.value) or name.split("_")[0].lower() in str(raised.value).lower()


def test_the_secret_key_is_required_and_has_no_default():
    with pytest.raises(main.SettingsError, match="SECRET_KEY"):
        main.Settings.from_env({})
    with pytest.raises(main.SettingsError, match="SECRET_KEY"):
        main.Settings.from_env({"SECRET_KEY": "short"})


# -------------------------------------------------------------------------- building the app


def test_the_application_runs_end_to_end_on_a_seeded_database(fake_simulator):
    app = main.build_app(settings(SEED_ON_START="true", IOT_SIM_SEED="7"))

    with TestClient(app) as client:
        assert client.get("/hubs").status_code == 401
        headers = login(client, "2452001", "pw-student")
        hubs = client.get("/hubs", headers=headers).json()
        assert [h["hub_id"] for h in hubs] == ["H01"]
        assert hubs[0]["available_vehicles"] == 1
        assert client.get("/hubs/H01/spaces", headers=headers).status_code == 403
        operator = login(client, "OP-1", "pw-operator")
        assert len(client.get("/hubs/H01/spaces", headers=operator).json()) == 4
    assert fake_simulator.calls == [7]
    assert app.state.core is not None and app.state.settings.iot_sim_seed == 7


def test_demo_data_is_loaded_only_into_an_empty_database(fake_simulator, tmp_path):
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    first = main.build_app(settings(DATABASE_URL=url, SEED_ON_START="true"))
    with TestClient(first):
        pass

    second = main.build_app(settings(DATABASE_URL=url, SEED_ON_START="true"))
    with TestClient(second) as client:
        hubs = client.get("/hubs", headers=login(client, "OP-1", "pw-operator")).json()

    assert fake_simulator.calls == [0]  # the second start found the data and did not load again
    assert [h["hub_id"] for h in hubs] == ["H01"]


def test_a_database_file_keeps_its_data_between_starts(tmp_path):
    url = f"sqlite:///{tmp_path / 'data' / 'hub.db'}"

    first = main.build_app(settings(DATABASE_URL=url))
    assert (tmp_path / "data" / "hub.db").exists()
    first.state.core.commands.load_network(demo_spec(), main.SEEDER)
    with TestClient(first):
        pass

    second = main.build_app(settings(DATABASE_URL=url))
    with TestClient(second) as client:
        headers = login(client, "OP-1", "pw-operator")
        assert [h["hub_id"] for h in client.get("/hubs", headers=headers).json()] == ["H01"]


def test_seeding_needs_a_simulator_that_can_build_the_network(monkeypatch):
    monkeypatch.setitem(sys.modules, "iot_sim", types.ModuleType("iot_sim"))

    with pytest.raises(main.StartupError, match="build_network_spec"):
        main.build_app(settings(SEED_ON_START="true"))


def test_a_demo_network_that_core_refuses_stops_the_start(monkeypatch):
    broken = types.ModuleType("iot_sim")
    broken.build_network_spec = lambda seed: NetworkSpec(hubs=())
    monkeypatch.setitem(sys.modules, "iot_sim", broken)

    with pytest.raises(main.StartupError, match="demo network"):
        main.build_app(settings(SEED_ON_START="true"))


def test_a_given_repository_is_not_closed_by_the_application():
    repo = SqlRepository.open("sqlite://")
    try:
        app = main.build_app(settings(), repository=repo)
        with TestClient(app):
            pass
        assert repo.version() == 0  # still open and usable
    finally:
        repo.close()


def test_docs_are_hidden_in_the_production_demo_but_not_in_development():
    development = TestClient(main.build_app(settings(APP_ENV="development")))
    demo = TestClient(main.build_app(settings(APP_ENV="production-demo")))

    assert development.get("/openapi.json").status_code == 200
    assert demo.get("/openapi.json").status_code == 404


def test_cross_origin_requests_are_allowed_only_for_the_configured_origin():
    open_to = "http://localhost:5173"
    with_origin = TestClient(main.build_app(settings(FRONTEND_ORIGIN=open_to)))
    without = TestClient(main.build_app(settings()))
    preflight = {
        "Origin": open_to,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }
    other = dict(preflight, Origin="http://evil.example")

    allowed = with_origin.options("/hubs", headers=preflight)
    refused = with_origin.options("/hubs", headers=other)
    none = without.options("/hubs", headers=preflight)

    assert allowed.headers["access-control-allow-origin"] == open_to
    assert "access-control-allow-origin" not in refused.headers
    assert "access-control-allow-origin" not in none.headers


# ----------------------------------------------------------------------- installing modules


def fake_module(monkeypatch, name, install=None, **attributes):
    module = types.ModuleType(name)
    if install is not None:
        module.install = install
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_modules_install_in_the_fixed_order_and_can_use_the_whole_core(monkeypatch):
    order = []
    received = []

    def reservation_install(core, app):
        order.append("reservation")
        core.register_provider(ProviderPort.RESERVATION_DEMAND, "reservation-impl")
        router = APIRouter()

        @router.get("/reservations/ping")
        def ping():
            return {"pong": True}

        app.include_router(router)

    def charging_install(core, app):
        order.append("charging")
        core.events.subscribe(EventType.HUB_STATUS_CHANGED, received.append)

    def monitoring_install(core, app):
        order.append("monitoring")

    fake_module(monkeypatch, "monitoring", monitoring_install)  # registered first on purpose
    fake_module(monkeypatch, "charging", charging_install)
    fake_module(monkeypatch, "reservation", reservation_install)
    fake_module(monkeypatch, "allocation")  # no install: skipped
    for name in ("simulation", "ui"):
        monkeypatch.setitem(sys.modules, name, None)  # not importable: skipped

    app = main.build_app(settings())

    assert order == ["reservation", "charging", "monitoring"]
    with TestClient(app) as client:
        assert client.get("/reservations/ping").json() == {"pong": True}
    core = app.state.core
    assert core.providers.is_registered(ProviderPort.RESERVATION_DEMAND)
    assert received == []  # subscribed, nothing happened yet


def test_a_module_that_fails_to_install_stops_the_start_with_its_name(monkeypatch):
    def broken(core, app):
        raise RuntimeError("cannot register")

    fake_module(monkeypatch, "monitoring", broken)

    with pytest.raises(main.StartupError, match="monitoring.*cannot register"):
        main.build_app(settings(), module_names=("monitoring",))


def test_a_module_whose_own_import_fails_is_an_error_not_a_skip(monkeypatch, tmp_path):
    package = tmp_path / "charging_broken"
    package.mkdir()
    (package / "__init__.py").write_text(
        "import a_library_that_is_not_installed\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(main.StartupError, match="could not be imported"):
        main.install_modules(None, None, ("charging_broken",))


def test_modules_without_code_yet_are_skipped():
    assert main.install_modules(None, None, ("a_module_that_does_not_exist",)) == []


def test_a_failed_start_closes_the_database_it_opened(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    fake_module(monkeypatch, "reservation", lambda core, app: 1 / 0)
    closed = []
    original = SqlRepository.close
    monkeypatch.setattr(SqlRepository, "close", lambda self: (closed.append(self), original(self)))

    with pytest.raises(main.StartupError):
        main.build_app(settings(DATABASE_URL=url), module_names=("reservation",))

    assert len(closed) == 1


def test_a_failed_start_does_not_close_a_repository_it_was_given(monkeypatch):
    fake_module(monkeypatch, "reservation", lambda core, app: 1 / 0)
    repo = SqlRepository.open("sqlite://")
    closed = []
    original = SqlRepository.close
    monkeypatch.setattr(SqlRepository, "close", lambda self: (closed.append(self), original(self)))
    try:
        with pytest.raises(main.StartupError):
            main.build_app(settings(), repository=repo, module_names=("reservation",))
        assert closed == []
    finally:
        original(repo)


# ----------------------------------------------------------------- the factory and the server


def test_the_factory_reads_the_env_file_and_reports_errors_in_plain_words(
    tmp_path, monkeypatch, capsys
):
    for name in ("SECRET_KEY", "APP_ENV", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="SECRET_KEY"):
        main.create_app()

    (tmp_path / ".env").write_text(f"SECRET_KEY={KEY}\nLOG_LEVEL=WARNING\n", encoding="utf-8")
    app = main.create_app()
    assert app.state.settings.auth.secret_key == KEY

    monkeypatch.setenv("SEED_ON_START", "true")
    monkeypatch.setitem(sys.modules, "iot_sim", types.ModuleType("iot_sim"))
    with pytest.raises(SystemExit, match="Startup error"):
        main.create_app()


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_the_documented_command_starts_a_real_server():
    port = free_port()
    env = {"SECRET_KEY": KEY, "LOG_LEVEL": "WARNING", "PATH": "", "SYSTEMROOT": "C:\\Windows"}
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--app-dir",
            str(ROOT / "src"),
            "main:create_app",
            "--factory",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 30
        status = None
        while time.time() < deadline:
            try:
                status = httpx.get(f"http://127.0.0.1:{port}/hubs", timeout=2).status_code
                break
            except httpx.TransportError:
                time.sleep(0.3)
        assert status == 401  # up, and asking for a login
        assert httpx.get(f"http://127.0.0.1:{port}/openapi.json", timeout=2).status_code == 200
    finally:
        server.terminate()
        server.wait(timeout=10)
