"""
Greedy scheduler engine.

Processes buses in departure-time order. For each bus, evaluates all
feasible charging plans against current station availability, scores
each plan using the weighted rules, and commits the best one.

Station availability is tracked per-charger, supporting N chargers
per station (default 1). The engine is deterministic: same input →
same output, always.
"""

from typing import List, Dict, Tuple, Optional

from .models import (
    Bus, Fleet, Route, Weights, ScenarioConfig,
    ChargePlan, ChargeEvent, BusTimeline, ScheduleResult,
)
from .planner import enumerate_feasible_plans
from .rules import Rule, CandidateEval, SchedulerState, DEFAULT_RULES


# ──────────────────────────────────────────────
#  Station availability tracker
# ──────────────────────────────────────────────

class StationTracker:
    """
    Tracks charger availability at a single station.

    Supports multiple chargers. For each charger, records when it
    becomes free. When a bus requests a charge, the tracker assigns
    the earliest-available charger.
    """

    def __init__(self, chargers: int = 1):
        self.chargers = chargers
        # Each charger's "free at" time (minutes from midnight)
        self.charger_free_at: List[float] = [0.0] * chargers

    def next_available(self, arrival_time: float) -> Tuple[float, int]:
        """
        When is the earliest a bus arriving at `arrival_time` can start charging?

        Returns:
            (charge_start_time, charger_index)
        """
        # Find the charger that becomes free earliest
        best_idx = min(range(self.chargers), key=lambda i: self.charger_free_at[i])
        available = max(arrival_time, self.charger_free_at[best_idx])
        return available, best_idx

    def book(self, charger_index: int, charge_end: float):
        """Mark a charger as occupied until charge_end."""
        self.charger_free_at[charger_index] = charge_end


# ──────────────────────────────────────────────
#  Plan simulation
# ──────────────────────────────────────────────

def simulate_plan(
    bus: Bus,
    plan: ChargePlan,
    route: Route,
    fleet: Fleet,
    station_trackers: Dict[str, StationTracker],
    commit: bool = False,
) -> Tuple[List[ChargeEvent], float, float, float]:
    """
    Simulate a bus following a specific charging plan.

    Computes the full timeline: travel times, arrival at stations,
    wait for charger, charging, and final arrival at destination.

    Args:
        bus: The bus to simulate
        plan: Which stations to charge at
        route: Route definition
        fleet: Fleet configuration (speed, charge time, range)
        station_trackers: Current station availability state
        commit: If True, updates station trackers (books the chargers)

    Returns:
        (charge_events, arrival_time, total_wait, total_trip_time)
    """
    direction = bus.direction
    cum_dist = route.get_cumulative_distances(direction)
    stops = route.get_stops(direction)
    origin = stops[0]
    destination = stops[-1]

    speed = fleet.speed_kmh
    charge_time = fleet.charging_time_min
    battery_range = fleet.battery_range_km

    current_time = bus.departure_minutes
    current_pos = origin
    current_range = battery_range

    events: List[ChargeEvent] = []
    total_wait = 0.0
    bookings: List[Tuple[str, int, float]] = []  # (station, charger_idx, charge_end)

    for station in plan.stations:
        # Travel from current position to this station
        travel_dist = cum_dist[station] - cum_dist[current_pos]
        travel_time = (travel_dist / speed) * 60  # convert hours to minutes
        arrival_time = current_time + travel_time
        range_on_arrival = current_range - travel_dist

        # Find when the charger is available
        tracker = station_trackers[station]
        charge_start, charger_idx = tracker.next_available(arrival_time)
        wait_time = charge_start - arrival_time
        charge_end = charge_start + charge_time

        events.append(ChargeEvent(
            station=station,
            arrival_time=round(arrival_time, 2),
            wait_time=round(wait_time, 2),
            charge_start=round(charge_start, 2),
            charge_end=round(charge_end, 2),
            range_on_arrival_km=round(range_on_arrival, 2),
        ))

        bookings.append((station, charger_idx, charge_end))
        total_wait += wait_time

        # After charging: depart from station with full range
        current_time = charge_end
        current_pos = station
        current_range = battery_range

    # Final leg: last charge (or origin) → destination
    final_dist = cum_dist[destination] - cum_dist[current_pos]
    final_time = (final_dist / speed) * 60
    arrival_at_dest = current_time + final_time
    total_trip = arrival_at_dest - bus.departure_minutes

    # Commit bookings if this is the chosen plan
    if commit:
        for station, charger_idx, charge_end in bookings:
            station_trackers[station].book(charger_idx, charge_end)

    return events, round(arrival_at_dest, 2), round(total_wait, 2), round(total_trip, 2)


# ──────────────────────────────────────────────
#  Main scheduler
# ──────────────────────────────────────────────

def schedule(
    config: ScenarioConfig,
    rules: Optional[List[Rule]] = None,
) -> ScheduleResult:
    """
    Run the greedy scheduler on a scenario.

    Algorithm:
      1. Sort buses by departure time (ties broken by bus ID)
      2. For each bus, enumerate all feasible charging plans
      3. Simulate each plan against current station availability
      4. Score each plan: cost = Σ(weight × rule(candidate, state))
      5. Commit the lowest-cost plan
      6. Repeat until all buses are scheduled

    Args:
        config: Full scenario configuration
        rules: List of scoring rules (defaults to DEFAULT_RULES)

    Returns:
        ScheduleResult with per-bus timelines and per-station queues
    """
    if rules is None:
        rules = DEFAULT_RULES

    route = config.route
    fleet = config.fleet
    weights = config.weights

    # Initialize station trackers
    station_trackers: Dict[str, StationTracker] = {}
    for name, station_cfg in route.charging_stations.items():
        station_trackers[name] = StationTracker(chargers=station_cfg.chargers)

    # Sort buses: earliest departure first, then by ID for determinism
    sorted_buses = sorted(fleet.buses, key=lambda b: (b.departure_minutes, b.id))

    # Scheduler state (grows as we commit plans)
    state = SchedulerState(committed=[])
    timelines: List[BusTimeline] = []

    for bus in sorted_buses:
        # 1. Get all feasible plans for this bus
        plans = enumerate_feasible_plans(bus.direction, route, fleet.battery_range_km)

        if not plans:
            raise ValueError(
                f"No feasible charging plan for bus {bus.id}. "
                f"Check route distances vs battery range ({fleet.battery_range_km} km)."
            )

        # 2. Evaluate each plan
        best_plan: Optional[ChargePlan] = None
        best_cost = float("inf")
        best_result = None

        for plan in plans:
            # Simulate without committing
            events, arrival, total_wait, total_trip = simulate_plan(
                bus, plan, route, fleet, station_trackers, commit=False,
            )

            # Build candidate evaluation
            candidate = CandidateEval(
                bus=bus,
                total_wait=total_wait,
                total_trip_time=total_trip,
                charge_count=len(plan.stations),
            )

            # Compute weighted cost
            cost = 0.0
            for rule in rules:
                w = weights.get(rule.name)
                if w > 0:
                    cost += w * rule.fn(candidate, state)

            if cost < best_cost or (cost == best_cost and best_plan is not None
                                     and len(plan.stations) < len(best_plan.stations)):
                best_cost = cost
                best_plan = plan
                best_result = (events, arrival, total_wait, total_trip)

        # 3. Commit the best plan
        events, arrival, total_wait, total_trip = best_result
        simulate_plan(bus, best_plan, route, fleet, station_trackers, commit=True)

        timeline = BusTimeline(
            bus=bus,
            charge_plan=best_plan,
            charge_events=events,
            departure_time=bus.departure_minutes,
            arrival_time=arrival,
            total_wait=total_wait,
            total_trip_time=total_trip,
        )

        timelines.append(timeline)
        state.committed.append(timeline)

    # 4. Build per-station queues
    station_queues: Dict[str, List[Dict]] = {}
    for name in route.charging_stations:
        station_queues[name] = []

    for tl in timelines:
        for ev in tl.charge_events:
            station_queues[ev.station].append({
                "bus_id": tl.bus.id,
                "operator": tl.bus.operator,
                "direction": tl.bus.direction,
                "arrival": ev.arrival_time,
                "wait": ev.wait_time,
                "charge_start": ev.charge_start,
                "charge_end": ev.charge_end,
            })

    # Sort each station's queue by charge start time
    for name in station_queues:
        station_queues[name].sort(key=lambda x: x["charge_start"])

    return ScheduleResult(timelines=timelines, station_queues=station_queues)
