"""State snapshot ingestion and memory isolation adapter.

Traces: FR-12.1, NFR-12, core-api-spec.md Section 7
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SimulatedVehicle:
    vehicle_id: str
    hub_id: Optional[str]
    vehicle_type: str
    state: str
    battery_pct: float
    soc: float  # Fraction 0.0 - 1.0 derived from battery_pct


@dataclass
class SimulatedHub:
    hub_id: str
    name: str
    parking_capacity: int
    occupied: int
    vehicles: List[SimulatedVehicle] = field(default_factory=list)


@dataclass
class IsolatedSandboxState:
    snapshot_id: str
    taken_at: Any
    hubs: Dict[str, SimulatedHub] = field(default_factory=dict)
    vehicles: Dict[str, SimulatedVehicle] = field(default_factory=dict)


class SnapshotAdapter:
    """Isolates operational snapshot from M1 Core into a clean simulation state."""

    @staticmethod
    def from_core_snapshot(snapshot: Any) -> IsolatedSandboxState:
        data = snapshot.to_dict() if hasattr(snapshot, "to_dict") else deepcopy(snapshot)

        sandbox = IsolatedSandboxState(
            snapshot_id=str(data.get("snapshot_id", "SNAP_M6_ISOLATED")),
            taken_at=data.get("taken_at")
        )

        # Map Hubs
        for h in data.get("hubs", []):
            hid = h.get("id") or h.get("hub_id")
            cap = h.get("parking_capacity", 0)
            occ = h.get("occupied", 0)
            name = h.get("name", hid)
            sandbox.hubs[hid] = SimulatedHub(
                hub_id=hid,
                name=name,
                parking_capacity=cap,
                occupied=occ,
                vehicles=[]
            )

        # Map flat vehicle list to Hubs
        for v in data.get("vehicles", []):
            vid = v.get("vehicle_id") or v.get("id")
            hid = v.get("hub_id")
            bat = float(v.get("battery_pct", 100.0))
            v_type = v.get("vehicle_type", "E_BIKE")
            state = v.get("state", "AVAILABLE")

            sim_veh = SimulatedVehicle(
                vehicle_id=vid,
                hub_id=hid,
                vehicle_type=v_type,
                state=state,
                battery_pct=bat,
                soc=bat / 100.0
            )
            sandbox.vehicles[vid] = sim_veh
            if hid and hid in sandbox.hubs:
                sandbox.hubs[hid].vehicles.append(sim_veh)

        return sandbox