"""Snapshot adapter isolating simulation sandbox state from Core DB.

Traces: NFR-12, Core API Spec §7
"""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SimulatedVehicle:
    vehicle_id: str
    hub_id: str
    vehicle_type: str
    state: str
    battery_pct: float
    soc: float


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
    taken_at: Optional[datetime]
    hubs: Dict[str, SimulatedHub] = field(default_factory=dict)
    vehicles: Dict[str, SimulatedVehicle] = field(default_factory=dict)


class SnapshotAdapter:
    @staticmethod
    def from_core_snapshot(data: Dict[str, Any]) -> IsolatedSandboxState:
        snapshot_id = str(data.get("snapshot_id", "SNAP_UNKNOWN"))
        taken_at_val = data.get("taken_at")
        taken_at = (
            datetime.fromisoformat(str(taken_at_val))
            if isinstance(taken_at_val, str)
            else taken_at_val
        )

        sandbox = IsolatedSandboxState(
            snapshot_id=snapshot_id,
            taken_at=taken_at,
        )

        # M6-3: Hub occupied count based on parking_spaces with state OCCUPIED
        for h in data.get("hubs", []):
            if isinstance(h, dict):
                hid = str(h.get("id") or h.get("hub_id"))
                cap = int(h.get("parking_capacity", 0))

                parking_spaces = h.get("parking_spaces", [])
                occ_count = sum(
                    1
                    for sp in parking_spaces
                    if isinstance(sp, dict) and sp.get("state") == "OCCUPIED"
                )

                sandbox.hubs[hid] = SimulatedHub(
                    hub_id=hid,
                    name=str(h.get("name", hid)),
                    parking_capacity=cap,
                    occupied=occ_count,
                )

        for v in data.get("vehicles", []):
            if isinstance(v, dict):
                vid = str(v.get("id") or v.get("vehicle_id"))
                hid = str(v.get("hub_id", ""))
                vtype = str(v.get("type", "E_BIKE"))
                st = str(v.get("state", "AVAILABLE"))
                soc_val = float(v.get("battery_pct", 80.0)) / 100.0

                sim_v = SimulatedVehicle(
                    vehicle_id=vid,
                    hub_id=hid,
                    vehicle_type=vtype,
                    state=st,
                    battery_pct=float(v.get("battery_pct", 80.0)),
                    soc=soc_val,
                )
                sandbox.vehicles[vid] = sim_v
                if hid in sandbox.hubs:
                    sandbox.hubs[hid].vehicles.append(sim_v)

        return deepcopy(sandbox)