"""Passwords, tokens and login (A-06, NFR-16, NFR-17)."""

from datetime import timedelta

import pytest

from core.auth import AuthConfig, AuthService, hash_password, verify_password
from core.clock import FixedClock
from core.domain.entities import UserAccount
from core.domain.enums import Role
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.result import Err, Ok

KEY = "test-secret-key-0123456789"  # test data, not a real secret


# ------------------------------------------------------------------------------ passwords


def test_a_hash_is_salted_and_never_contains_the_password():
    first = hash_password("correct horse", iterations=1000)
    second = hash_password("correct horse", iterations=1000)

    assert first != second  # a new salt every time
    assert "correct horse" not in first
    assert first.startswith("pbkdf2_sha256$1000$")
    assert verify_password("correct horse", first) and verify_password("correct horse", second)


@pytest.mark.parametrize("wrong", ["", "Correct horse", "correct horse ", "x" * 500])
def test_a_wrong_password_does_not_verify(wrong):
    assert not verify_password(wrong, hash_password("correct horse", iterations=1000))


@pytest.mark.parametrize(
    "damaged",
    [
        "",
        "plain",
        "a$b$c$d",
        "pbkdf2_sha256$x$00$00",
        "pbkdf2_sha256$1000$zz$00",
        "md5$1$00$00",
        "a$b$c",
    ],
)
def test_a_damaged_stored_hash_is_false_not_an_error(damaged):
    assert verify_password("anything", damaged) is False


def test_the_cost_must_be_positive():
    with pytest.raises(ValueError):
        hash_password("x", iterations=0)


def test_non_ascii_passwords_work():
    stored = hash_password("mật khẩu 密码", iterations=1000)

    assert verify_password("mật khẩu 密码", stored)
    assert not verify_password("mat khau", stored)


# --------------------------------------------------------------------------------- config


def test_there_is_no_default_secret():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        AuthConfig.from_env({})
    with pytest.raises(ValueError, match="SECRET_KEY"):
        AuthConfig.from_env({"SECRET_KEY": "   "})


def test_the_secret_must_be_long_enough_and_numbers_positive():
    with pytest.raises(ValueError):
        AuthConfig(secret_key="short")
    with pytest.raises(ValueError):
        AuthConfig(secret_key=KEY, token_minutes=0)
    with pytest.raises(ValueError):
        AuthConfig(secret_key=KEY, hash_iterations=0)


def test_config_comes_from_the_environment():
    config = AuthConfig.from_env(
        {"SECRET_KEY": KEY, "ACCESS_TOKEN_TTL_MINUTES": "15", "PASSWORD_HASH_ITERATIONS": "2000"}
    )

    assert (config.token_minutes, config.hash_iterations) == (15, 2000)
    defaults = AuthConfig.from_env({"SECRET_KEY": KEY})
    assert defaults.token_minutes == 60


# ----------------------------------------------------------------------------- the service


@pytest.fixture
def service(t0):
    repo = InMemoryRepository()
    clock = FixedClock(t0)
    core = CoreFacade(repo, clock)
    config = AuthConfig(secret_key=KEY, token_minutes=30, hash_iterations=1000)
    repo.add(
        UserAccount("U1", "2452001", Role.STUDENT, password_hash=hash_password("pw-student", 1000))
    )
    repo.add(UserAccount("OP1", "OP-1", Role.OPERATOR, password_hash=hash_password("pw-op", 1000)))
    repo.add(
        UserAccount(
            "U2", "2452002", Role.STUDENT, password_hash=hash_password("pw2", 1000), is_active=False
        )
    )
    repo.add(UserAccount("U3", "2452003", Role.STUDENT))  # no password: cannot log in
    return core.authentication(config), clock, repo


def test_login_gives_a_token_that_names_the_user(service, t0):
    auth, _clock, _repo = service

    result = auth.login("2452001", "pw-student")

    assert isinstance(result, Ok)
    assert (result.value.user_id, result.value.role) == ("U1", Role.STUDENT)
    assert result.value.expires_at == t0 + timedelta(minutes=30)
    who = auth.authenticate(result.value.access_token)
    assert isinstance(who, Ok)
    assert (who.value.user_id, who.value.role, who.value.module) == ("U1", Role.STUDENT, "ui")


@pytest.mark.parametrize(
    ("code", "password"),
    [
        ("2452001", "wrong"),
        ("2452001", ""),
        ("NOBODY", "pw-student"),
        ("2452002", "pw2"),  # inactive account
        ("2452003", ""),  # no password set
        ("2452003", "anything"),
        ("", ""),
    ],
)
def test_every_kind_of_failed_login_gives_the_same_answer(service, code, password):
    auth, _clock, _repo = service

    result = auth.login(code, password)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.UNAUTHENTICATED
    assert result.message == "wrong account or password"  # nothing says which part was wrong


def test_a_token_expires_exactly_at_its_expiry_time(service):
    auth, clock, _repo = service
    token = auth.login("2452001", "pw-student").value.access_token  # type: ignore[union-attr]

    clock.advance(timedelta(minutes=30) - timedelta(seconds=1))
    assert isinstance(auth.authenticate(token), Ok)
    clock.advance(timedelta(seconds=1))
    assert isinstance(auth.authenticate(token), Err)


def test_a_changed_token_is_refused(service):
    auth, _clock, _repo = service
    token = auth.login("2452001", "pw-student").value.access_token  # type: ignore[union-attr]
    version, body, signature = token.split(".")
    other = auth.login("OP-1", "pw-op").value.access_token  # type: ignore[union-attr]
    other_body = other.split(".")[1]

    forged = [
        f"{version}.{body}.{signature[:-2]}AA",  # damaged signature
        f"{version}.{other_body}.{signature}",  # another user's payload, old signature
        f"v2.{body}.{signature}",
        f"{version}.{body}",
        "",
        "not a token",
        "a.b.c",
        token + ".extra",
    ]
    for candidate in forged:
        result = auth.authenticate(candidate)
        assert isinstance(result, Err), candidate
        assert result.code is ErrorCode.UNAUTHENTICATED


def test_a_token_signed_with_another_key_is_refused(service, t0):
    auth, _clock, repo = service
    other = CoreFacade(repo, FixedClock(t0)).authentication(
        AuthConfig(secret_key="another-secret-key-987654321", hash_iterations=1000)
    )
    foreign = other.login("2452001", "pw-student").value.access_token  # type: ignore[union-attr]

    assert isinstance(auth.authenticate(foreign), Err)


def test_the_account_is_checked_again_on_every_request(service):
    auth, _clock, repo = service
    token = auth.login("2452001", "pw-student").value.access_token  # type: ignore[union-attr]

    user = repo.get(UserAccount, "U1")
    user.is_active = False
    repo.update(user)
    assert isinstance(auth.authenticate(token), Err)  # a deactivated user is out at once

    user.is_active = True
    user.role = Role.OPERATOR  # a changed role takes effect without a new login
    repo.update(user)
    who = auth.authenticate(token)
    assert isinstance(who, Ok) and who.value.role is Role.OPERATOR


def test_a_token_of_a_deleted_user_is_refused(service):
    auth, _clock, repo = service
    token = auth.login("2452001", "pw-student").value.access_token  # type: ignore[union-attr]
    repo.update(UserAccount("U1", "2452001", Role.STUDENT, is_active=False))

    assert isinstance(auth.authenticate(token), Err)


def test_a_service_token_is_an_operator_of_the_named_module_and_expires(service):
    auth, clock, _repo = service

    token = auth.issue_service_token("iot_sim", "SIM", minutes=5)
    who = auth.authenticate(token)

    assert isinstance(who, Ok)
    assert (who.value.user_id, who.value.role, who.value.module) == (
        "SIM",
        Role.OPERATOR,
        "iot_sim",
    )
    assert who.value.actor().module == "iot_sim"
    clock.advance(timedelta(minutes=5))
    assert isinstance(auth.authenticate(token), Err)


def test_the_token_does_not_contain_the_password_or_its_hash(service):
    auth, _clock, _repo = service

    token = auth.login("2452001", "pw-student").value.access_token  # type: ignore[union-attr]

    assert "pw-student" not in token and "pbkdf2" not in token


def test_the_service_type_is_a_class(service):
    assert isinstance(service[0], AuthService)
