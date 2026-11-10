"""Enumerations of the core domain (docs/design/structural/class-diagram-core.md, section 2)."""

from enum import StrEnum


class VehicleState(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    IN_USE = "IN_USE"
    RETURNED = "RETURNED"
    CHARGING = "CHARGING"
    MAINTENANCE = "MAINTENANCE"


class VehicleEvent(StrEnum):
    """Events of the Vehicle state machine (docs/design/behavioral/vehicle-state-machine.md)."""

    RESERVE = "reserve"
    RELEASE_RESERVATION = "release_reservation"
    PICKUP = "pickup"
    RETURN = "return"
    RETURN_FAULTY = "return_faulty"
    MARK_READY = "mark_ready"
    START_CHARGING = "start_charging"
    FINISH_CHARGING = "finish_charging"
    INTERRUPT_CHARGING = "interrupt_charging"
    REPORT_FAULT = "report_fault"
    REPAIR = "repair"
    ARRIVE = "arrive"
    DEPART = "depart"


class HubStatus(StrEnum):
    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    MAINTENANCE = "MAINTENANCE"


class SpaceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"


class ChargingPointStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    CHARGING = "CHARGING"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    MAINTENANCE = "MAINTENANCE"


class Ownership(StrEnum):
    FLEET = "FLEET"
    PRIVATE = "PRIVATE"


class VehicleType(StrEnum):
    E_BIKE = "E_BIKE"
    E_SCOOTER = "E_SCOOTER"
    E_MOTORCYCLE = "E_MOTORCYCLE"


class ResourceType(StrEnum):
    VEHICLE = "VEHICLE"
    SPACE = "SPACE"
    CHARGING_POINT = "CHARGING_POINT"


class HolderKind(StrEnum):
    """The three claims named in BR-M1-01."""

    RESERVATION = "RESERVATION"
    CHARGING_SESSION = "CHARGING_SESSION"
    DISPATCH_TASK = "DISPATCH_TASK"


class ClaimStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class Role(StrEnum):
    STUDENT = "STUDENT"
    OPERATOR = "OPERATOR"
