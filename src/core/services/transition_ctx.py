"""Inputs of ``transition_vehicle`` (kept apart so the sensor intake can use it without a cycle)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransitionCtx:
    """Inputs of ``transition_vehicle`` besides the event.

    - ``min_battery``: lowest battery the caller accepts for ``reserve`` (T1).
    - ``claim_id``: the claim that backs the transition. Required for ``reserve`` and ``pickup``
      (a claim on the vehicle), for ``start_charging`` (a claim on the charging point) and
      optional for ``return`` (the caller's hold on the destination space; it is consumed).
    - ``hub_id`` / ``parking_space_id``: destination of ``return`` and ``return_faulty``. A named
      space wins; with only a Hub, the lowest free space is chosen.
    - ``charging_point_id``: the bay for ``start_charging``.
    - ``battery_pct``: the battery level when known (for example at return).
    """

    min_battery: float = 0.0
    claim_id: str | None = None
    hub_id: str | None = None
    parking_space_id: str | None = None
    charging_point_id: str | None = None
    battery_pct: float | None = None
