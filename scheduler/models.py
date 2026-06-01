"""
Domain models for the Bus Charging Scheduler.

All core data structures: route, stations, buses, charging plans, timelines.
Designed as plain dataclasses — no framework coupling, easy to serialize.
"""

from dataclasses import dataclass, field
from typing import List, Dict


# ──────────────────────────────────────────────
#  Input / Configuration Models
# ──────────────────────────────────────────────

@dataclass
class Segment:
    """A single segment of the route between two consecutive stops."""
    from_stop: str
    to_stop: str
    distance_km: float


@dataclass
class StationConfig:
    """Configuration for a charging station."""
    name: str
    chargers: int = 1


@dataclass
class Route:
    """
    The full route definition: ordered segments + charging station configs.
    Supports bidirectional travel — forward (BK) and reverse (KB).
    """
    segments: List[Segment]
    charging_stations: Dict[str, StationConfig]

    @property
    def stops_forward(self) -> List[str]:
        """All stops in forward (Bengaluru → Kochi) order."""
        stops = [self.segments[0].from_stop]
        for seg in self.segments:
            stops.append(seg.to_stop)
        return stops

    @property
    def stops_reverse(self) -> List[str]:
        """All stops in reverse (Kochi → Bengaluru) order."""
        return list(reversed(self.stops_forward))

    def get_stops(self, direction: str) -> List[str]:
        """Get ordered stops for a given direction ('BK' or 'KB')."""
        return self.stops_forward if direction == "BK" else self.stops_reverse

    def get_charging_stations(self, direction: str) -> List[str]:
        """Get charging station names in route order for a direction."""
        stops = self.get_stops(direction)
        return [s for s in stops if s in self.charging_stations]

    def get_cumulative_distances(self, direction: str) -> Dict[str, float]:
        """Cumulative distance from the origin for each stop in the given direction."""
        if direction == "BK":
            ordered_segments = self.segments
        else:
            ordered_segments = [
                Segment(s.to_stop, s.from_stop, s.distance_km)
                for s in reversed(self.segments)
            ]

        stops = self.get_stops(direction)
        result = {stops[0]: 0.0}
        dist = 0.0
        for seg in ordered_segments:
            dist += seg.distance_km
            result[seg.to_stop] = dist
        return result

    @property
    def total_distance(self) -> float:
        return sum(s.distance_km for s in self.segments)


@dataclass
class Bus:
    """A single bus with its schedule."""
    id: str
    operator: str
    direction: str   # "BK" (Bengaluru→Kochi) or "KB" (Kochi→Bengaluru)
    departure: str   # "HH:MM" format

    @property
    def departure_minutes(self) -> float:
        """Convert HH:MM to minutes from midnight."""
        h, m = self.departure.split(":")
        return int(h) * 60 + int(m)


@dataclass
class Fleet:
    """Fleet configuration: shared physical constants + list of buses."""
    battery_range_km: float
    charging_time_min: float
    speed_kmh: float
    buses: List[Bus]


@dataclass
class Weights:
    """
    Tunable weights for the scheduler's cost function.
    Stored as a dict so new rules can be added without changing this class.
    """
    values: Dict[str, float] = field(default_factory=lambda: {
        "individual_wait": 1.0,
        "operator_fairness": 1.0,
        "overall_time": 1.0,
    })

    def get(self, name: str) -> float:
        """Get weight for a rule. Returns 0.0 if rule not configured."""
        return self.values.get(name, 0.0)


@dataclass
class ScenarioConfig:
    """Complete scenario: everything the scheduler needs as input."""
    name: str
    description: str
    route: Route
    fleet: Fleet
    weights: Weights


# ──────────────────────────────────────────────
#  Output Models
# ──────────────────────────────────────────────

@dataclass
class ChargePlan:
    """Which stations a bus will charge at, in route order."""
    stations: List[str]


@dataclass
class ChargeEvent:
    """One charging stop in a bus's journey."""
    station: str
    arrival_time: float         # minutes from midnight
    wait_time: float            # minutes waiting for charger
    charge_start: float         # minutes from midnight
    charge_end: float           # minutes from midnight
    range_on_arrival_km: float  # remaining range when bus arrives at station


@dataclass
class BusTimeline:
    """Complete journey timeline for a single bus."""
    bus: Bus
    charge_plan: ChargePlan
    charge_events: List[ChargeEvent]
    departure_time: float       # minutes from midnight
    arrival_time: float         # minutes from midnight — when bus reaches destination
    total_wait: float           # total minutes spent waiting for chargers
    total_trip_time: float      # departure to arrival, including travel + charging + waiting


@dataclass
class ScheduleResult:
    """Full output of the scheduler for a scenario."""
    timelines: List[BusTimeline]
    station_queues: Dict[str, List[Dict]]  # station_name → ordered list of charge events
