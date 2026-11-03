"""Claim rules: no two overlapping claims on one resource (BR-M1-01, NFR-06).

A claim covers the half-open interval [start_at, end_at): a claim that ends exactly when another
starts does not overlap it.
"""

from collections.abc import Iterable
from datetime import datetime

from core.domain.entities import ResourceClaim
from core.domain.enums import ClaimStatus, HolderKind, ResourceType
from core.errors import ErrorCode
from core.result import Err


class ClaimPolicy:
    @staticmethod
    def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
        return a_start < b_end and b_start < a_end

    @staticmethod
    def validate_interval(start_at: datetime, end_at: datetime) -> Err | None:
        for name, value in (("start_at", start_at), ("end_at", end_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                return Err(ErrorCode.INVALID_INPUT, f"{name} must be timezone-aware (UTC)")
        if start_at >= end_at:
            return Err(ErrorCode.INVALID_INPUT, "start_at must be before end_at")
        return None

    @classmethod
    def find_conflict(
        cls,
        existing: Iterable[ResourceClaim],
        resource_type: ResourceType,
        resource_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> ResourceClaim | None:
        """First ACTIVE claim on the same resource whose interval overlaps, in claim_id order."""
        for claim in sorted(existing, key=lambda c: c.claim_id):
            if (
                claim.status is ClaimStatus.ACTIVE
                and claim.resource_type is resource_type
                and claim.resource_id == resource_id
                and cls.overlaps(claim.start_at, claim.end_at, start_at, end_at)
            ):
                return claim
        return None

    @staticmethod
    def find_same_request(
        existing: Iterable[ResourceClaim],
        resource_type: ResourceType,
        resource_id: str,
        holder_kind: HolderKind,
        holder_ref: str,
        start_at: datetime,
        end_at: datetime,
    ) -> ResourceClaim | None:
        """An ACTIVE claim made by the same holder for the same resource and interval.

        A retried ``place_claim`` returns it instead of failing with CLAIM_CONFLICT.
        """
        for claim in sorted(existing, key=lambda c: c.claim_id):
            if (
                claim.status is ClaimStatus.ACTIVE
                and claim.resource_type is resource_type
                and claim.resource_id == resource_id
                and claim.holder_kind is holder_kind
                and claim.holder_ref == holder_ref
                and claim.start_at == start_at
                and claim.end_at == end_at
            ):
                return claim
        return None
