"""
Charging plan enumerator.

Generates all feasible charging plans for a bus given its direction,
the route, and battery range. A plan is feasible if the bus never
exceeds its battery range between any two consecutive charges
(or between start/end and the nearest charge).

Works for any number of stations — not hardcoded to 4.
"""

from itertools import combinations
from typing import List

from .models import Route, ChargePlan


def enumerate_feasible_plans(
    direction: str,
    route: Route,
    battery_range_km: float,
) -> List[ChargePlan]:
    """
    Enumerate all feasible charging plans for a bus.

    A charging plan is a subset of the route's charging stations (in route
    order) such that:
      - distance(origin → first_station) ≤ battery_range_km
      - distance(station_i → station_{i+1}) ≤ battery_range_km  (for consecutive stations)
      - distance(last_station → destination) ≤ battery_range_km

    Args:
        direction: "BK" or "KB"
        route: The route definition
        battery_range_km: Maximum range on a full charge

    Returns:
        List of feasible ChargePlans, ordered by number of stops (fewer first).
    """
    stations = route.get_charging_stations(direction)
    cum_dist = route.get_cumulative_distances(direction)
    stops = route.get_stops(direction)
    origin = stops[0]
    destination = stops[-1]

    feasible_plans: List[ChargePlan] = []

    # Try all subsets of stations, from smallest to largest
    for size in range(1, len(stations) + 1):
        for combo in combinations(stations, size):
            plan_stations = list(combo)

            # Build checkpoint sequence: origin → stations → destination
            checkpoints = [origin] + plan_stations + [destination]

            # Check every gap
            feasible = True
            for i in range(len(checkpoints) - 1):
                gap = cum_dist[checkpoints[i + 1]] - cum_dist[checkpoints[i]]
                if gap > battery_range_km:
                    feasible = False
                    break

            if feasible:
                feasible_plans.append(ChargePlan(stations=plan_stations))

    return feasible_plans
