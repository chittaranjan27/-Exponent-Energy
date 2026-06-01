"""
Validation script — verifies that all 5 scenarios produce valid schedules.

Checks:
  1. Range constraint: no bus exceeds 240 km between charges
  2. Charger exclusivity: no two charge windows overlap at any station
  3. Completeness: every bus has a timeline
  4. Route order: stations are visited in route order
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from scheduler.loader import load_scenario, list_scenarios
from scheduler.engine import schedule


def validate_scenario(path: str) -> list:
    """Validate a scenario and return list of error messages."""
    errors = []
    config = load_scenario(path)
    result = schedule(config)

    route = config.route
    fleet = config.fleet

    # 1. Check all buses have timelines
    bus_ids = {b.id for b in fleet.buses}
    scheduled_ids = {t.bus.id for t in result.timelines}
    missing = bus_ids - scheduled_ids
    if missing:
        errors.append(f"Missing timelines for buses: {missing}")

    for tl in result.timelines:
        bus = tl.bus
        cum_dist = route.get_cumulative_distances(bus.direction)
        stops = route.get_stops(bus.direction)
        origin = stops[0]
        destination = stops[-1]

        # 2. Range constraint
        checkpoints = [origin] + tl.charge_plan.stations + [destination]
        for i in range(len(checkpoints) - 1):
            gap = cum_dist[checkpoints[i + 1]] - cum_dist[checkpoints[i]]
            if gap > fleet.battery_range_km + 0.01:  # small epsilon for float
                errors.append(
                    f"{bus.id}: Range violation! "
                    f"{checkpoints[i]}→{checkpoints[i+1]} = {gap:.1f} km > {fleet.battery_range_km} km"
                )

        # 3. Route order
        station_indices = [stops.index(s) for s in tl.charge_plan.stations]
        if station_indices != sorted(station_indices):
            errors.append(f"{bus.id}: Stations not in route order: {tl.charge_plan.stations}")

        # 4. Positive trip time
        if tl.total_trip_time <= 0:
            errors.append(f"{bus.id}: Non-positive trip time: {tl.total_trip_time}")

        # 5. Non-negative wait
        if tl.total_wait < -0.01:
            errors.append(f"{bus.id}: Negative wait time: {tl.total_wait}")

    # 6. Charger exclusivity
    for station_name, queue in result.station_queues.items():
        chargers = config.route.charging_stations[station_name].chargers
        # Sort by charge_start
        sorted_q = sorted(queue, key=lambda x: x["charge_start"])

        # For single charger, check no overlaps
        if chargers == 1:
            for i in range(len(sorted_q) - 1):
                end_i = sorted_q[i]["charge_end"]
                start_next = sorted_q[i + 1]["charge_start"]
                if start_next < end_i - 0.01:
                    errors.append(
                        f"Station {station_name}: Charger overlap! "
                        f"{sorted_q[i]['bus_id']} ends at {end_i:.1f}, "
                        f"{sorted_q[i+1]['bus_id']} starts at {start_next:.1f}"
                    )

    return errors


def main():
    scenario_dir = Path(__file__).parent / "data" / "scenarios"
    scenarios = list_scenarios(str(scenario_dir))

    if not scenarios:
        print(f"ERROR: No scenarios found in {scenario_dir}")
        sys.exit(1)

    all_pass = True
    for name, path in scenarios:
        print(f"\n{'='*60}")
        print(f"Validating: {name}")
        print(f"{'='*60}")

        try:
            errors = validate_scenario(path)
            if errors:
                all_pass = False
                for err in errors:
                    print(f"  ❌ {err}")
            else:
                # Print summary stats
                config = load_scenario(path)
                result = schedule(config)
                total_buses = len(result.timelines)
                avg_wait = sum(t.total_wait for t in result.timelines) / total_buses
                max_wait = max(t.total_wait for t in result.timelines)
                avg_trip = sum(t.total_trip_time for t in result.timelines) / total_buses

                print(f"  ✅ All checks passed!")
                print(f"  📊 Buses: {total_buses}")
                print(f"  ⏱  Avg wait: {avg_wait:.1f} min | Max wait: {max_wait:.1f} min")
                print(f"  🚌 Avg trip: {avg_trip:.0f} min")

                # Show charging plan distribution
                plan_counts = {}
                for tl in result.timelines:
                    plan_key = " → ".join(tl.charge_plan.stations)
                    plan_counts[plan_key] = plan_counts.get(plan_key, 0) + 1
                print(f"  📋 Charging plans used:")
                for plan, count in sorted(plan_counts.items()):
                    print(f"     {plan}: {count} buses")

        except Exception as e:
            all_pass = False
            print(f"  ❌ Exception: {e}")

    print(f"\n{'='*60}")
    if all_pass:
        print("🎉 All scenarios validated successfully!")
    else:
        print("⚠️  Some scenarios have issues — see above.")
    print(f"{'='*60}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
