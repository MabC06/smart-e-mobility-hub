"""Claim rules (BR-M1-01): interval overlap, conflicts, retries."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from core.domain.claims import ClaimPolicy
from core.domain.entities import ResourceClaim
from core.domain.enums import ClaimStatus, HolderKind, ResourceType
from core.errors import ErrorCode


def at(minutes: int, base: datetime) -> datetime:
    return base + timedelta(minutes=minutes)


# Intervals are half-open [start, end): touching intervals do not overlap.
@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((0, 10), (10, 20), False),
        ((10, 20), (0, 10), False),
        ((0, 10), (9, 20), True),
        ((0, 10), (0, 10), True),
        ((0, 30), (10, 20), True),
        ((10, 20), (0, 30), True),
        ((0, 10), (11, 20), False),
    ],
)
def test_overlap_boundaries(
    t0: datetime, a: tuple[int, int], b: tuple[int, int], expected: bool
) -> None:
    assert ClaimPolicy.overlaps(at(a[0], t0), at(a[1], t0), at(b[0], t0), at(b[1], t0)) is expected


def test_conflict_is_found_on_the_same_resource(
    t0: datetime, make_claim: Callable[..., ResourceClaim]
) -> None:
    existing = [make_claim("C001", "V001", 0, 10)]

    found = ClaimPolicy.find_conflict(existing, ResourceType.VEHICLE, "V001", at(5, t0), at(15, t0))

    assert found is not None
    assert found.claim_id == "C001"


def test_no_conflict_for_touching_interval(
    t0: datetime, make_claim: Callable[..., ResourceClaim]
) -> None:
    existing = [make_claim("C001", "V001", 0, 10)]

    assert (
        ClaimPolicy.find_conflict(existing, ResourceType.VEHICLE, "V001", at(10, t0), at(20, t0))
        is None
    )


def test_released_and_expired_claims_do_not_conflict(
    t0: datetime, make_claim: Callable[..., ResourceClaim]
) -> None:
    existing = [
        make_claim("C001", "V001", 0, 10, status=ClaimStatus.RELEASED),
        make_claim("C002", "V001", 0, 10, status=ClaimStatus.EXPIRED),
    ]

    assert (
        ClaimPolicy.find_conflict(existing, ResourceType.VEHICLE, "V001", at(0, t0), at(10, t0))
        is None
    )


def test_other_resources_and_types_do_not_conflict(
    t0: datetime, make_claim: Callable[..., ResourceClaim]
) -> None:
    existing = [make_claim("C001", "V001", 0, 10)]

    assert (
        ClaimPolicy.find_conflict(existing, ResourceType.VEHICLE, "V002", at(0, t0), at(10, t0))
        is None
    )
    assert (
        ClaimPolicy.find_conflict(existing, ResourceType.SPACE, "V001", at(0, t0), at(10, t0))
        is None
    )


def test_first_conflict_is_chosen_by_claim_id(
    t0: datetime, make_claim: Callable[..., ResourceClaim]
) -> None:
    existing = [make_claim("C002", "V001", 0, 10), make_claim("C001", "V001", 5, 15)]

    found = ClaimPolicy.find_conflict(existing, ResourceType.VEHICLE, "V001", at(6, t0), at(8, t0))

    assert found is not None
    assert found.claim_id == "C001"


def test_same_request_is_recognised_for_a_retry(
    t0: datetime, make_claim: Callable[..., ResourceClaim]
) -> None:
    existing = [make_claim("C001", "V001", 0, 10, holder_ref="R001")]

    same = ClaimPolicy.find_same_request(
        existing,
        ResourceType.VEHICLE,
        "V001",
        HolderKind.RESERVATION,
        "R001",
        at(0, t0),
        at(10, t0),
    )
    other_holder = ClaimPolicy.find_same_request(
        existing,
        ResourceType.VEHICLE,
        "V001",
        HolderKind.RESERVATION,
        "R999",
        at(0, t0),
        at(10, t0),
    )
    other_interval = ClaimPolicy.find_same_request(
        existing,
        ResourceType.VEHICLE,
        "V001",
        HolderKind.RESERVATION,
        "R001",
        at(0, t0),
        at(11, t0),
    )

    assert same is not None
    assert other_holder is None
    assert other_interval is None


def test_interval_validation(t0: datetime) -> None:
    assert ClaimPolicy.validate_interval(at(0, t0), at(1, t0)) is None

    backwards = ClaimPolicy.validate_interval(at(1, t0), at(0, t0))
    empty = ClaimPolicy.validate_interval(at(0, t0), at(0, t0))
    naive = ClaimPolicy.validate_interval(datetime(2026, 11, 2, 8, 0), at(1, t0))

    for error in (backwards, empty, naive):
        assert error is not None
        assert error.code is ErrorCode.INVALID_INPUT


def test_claim_entity_rejects_bad_intervals(t0: datetime) -> None:
    with pytest.raises(ValueError):
        ResourceClaim(
            "C1", ResourceType.VEHICLE, "V1", HolderKind.RESERVATION, "R1", at(5, t0), at(5, t0)
        )
    with pytest.raises(ValueError):
        ResourceClaim(
            "C1",
            ResourceType.VEHICLE,
            "V1",
            HolderKind.RESERVATION,
            "R1",
            datetime(2026, 11, 2, 8, 0, tzinfo=UTC).replace(tzinfo=None),
            at(5, t0),
        )
