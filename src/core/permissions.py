"""Who may run which command (NFR-16). One table, easy to review and to change.

Modules act on behalf of students, so the check is on the calling module and the role:
- an OPERATOR may run every command;
- a claim is placed and released by the module that owns its holder kind;
- a fault report or repair needs an operator or a system module (monitoring, iot_sim);
- a vehicle is registered by the charging module (private EV profile) or the seed loader (iot_sim).
"""

from core.actor import Actor
from core.domain.enums import HolderKind, Role, VehicleEvent

SYSTEM_MODULES = frozenset({"monitoring", "iot_sim"})

HOLDER_MODULE: dict[HolderKind, str] = {
    HolderKind.RESERVATION: "reservation",
    HolderKind.CHARGING_SESSION: "charging",
    HolderKind.DISPATCH_TASK: "allocation",
}

_OPERATOR_OR_SYSTEM_EVENTS = frozenset({VehicleEvent.REPORT_FAULT, VehicleEvent.REPAIR})
_OCCUPANCY_EVENTS = frozenset({VehicleEvent.ARRIVE, VehicleEvent.DEPART})


def _is_operator(actor: Actor) -> bool:
    return actor.role is Role.OPERATOR


def _is_operator_or_system(actor: Actor) -> bool:
    return _is_operator(actor) or actor.module in SYSTEM_MODULES


def may_transition(actor: Actor, event: VehicleEvent) -> bool:
    if event in _OPERATOR_OR_SYSTEM_EVENTS:
        return _is_operator_or_system(actor)
    if event in _OCCUPANCY_EVENTS:
        return may_change_occupancy(actor)
    return True


def may_manage_claim(actor: Actor, holder_kind: HolderKind) -> bool:
    return _is_operator(actor) or actor.module == HOLDER_MODULE[holder_kind]


def may_set_hub_status(actor: Actor) -> bool:
    return _is_operator_or_system(actor)


def may_set_charging_point_status(actor: Actor) -> bool:
    return _is_operator_or_system(actor) or actor.module == "charging"


def may_register_vehicle(actor: Actor) -> bool:
    return _is_operator(actor) or actor.module in {"charging", "iot_sim"}


def may_send_sensor_event(actor: Actor) -> bool:
    return actor.module == "iot_sim"


def may_load_network(actor: Actor) -> bool:
    return _is_operator(actor) or actor.module == "iot_sim"


def may_change_occupancy(actor: Actor) -> bool:
    return _is_operator(actor) or actor.module in {"reservation", "iot_sim"}
