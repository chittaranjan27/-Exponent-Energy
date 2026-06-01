"""
Scenario loader: YAML file → typed ScenarioConfig objects.

Handles parsing, validation, and listing available scenarios.
"""

import yaml
from pathlib import Path
from typing import List, Tuple

from .models import (
    Segment, StationConfig, Route, Bus, Fleet, Weights, ScenarioConfig,
)


def load_scenario(path: str) -> ScenarioConfig:
    """
    Load a scenario from a YAML file and return a fully typed ScenarioConfig.

    Validates:
      - All segment distances are positive
      - All departure times are parseable
      - Charging station names match stops defined in the route
      - At least one bus exists
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # --- Route ---
    segments = [
        Segment(
            from_stop=s["from"],
            to_stop=s["to"],
            distance_km=float(s["distance_km"]),
        )
        for s in data["route"]["segments"]
    ]

    # Validate segment distances
    for seg in segments:
        if seg.distance_km <= 0:
            raise ValueError(
                f"Segment {seg.from_stop}→{seg.to_stop} has invalid distance: {seg.distance_km}"
            )

    # Build set of valid stop names from segments
    valid_stops = {segments[0].from_stop}
    for seg in segments:
        valid_stops.add(seg.to_stop)

    stations = {}
    for name, cfg in data["route"]["charging_stations"].items():
        if name not in valid_stops:
            raise ValueError(
                f"Charging station '{name}' is not a stop on the route. "
                f"Valid stops: {valid_stops}"
            )
        stations[name] = StationConfig(
            name=name,
            chargers=int(cfg.get("chargers", 1)),
        )

    route = Route(segments=segments, charging_stations=stations)

    # --- Fleet ---
    buses = []
    for b in data["fleet"]["buses"]:
        bus = Bus(
            id=b["id"],
            operator=b["operator"],
            direction=b["direction"],
            departure=b["departure"],
        )
        # Validate departure time format
        try:
            _ = bus.departure_minutes
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Bus {bus.id} has invalid departure time '{bus.departure}': {e}")

        # Validate direction
        if bus.direction not in ("BK", "KB"):
            raise ValueError(
                f"Bus {bus.id} has invalid direction '{bus.direction}'. Must be 'BK' or 'KB'."
            )

        buses.append(bus)

    if not buses:
        raise ValueError("Fleet must contain at least one bus.")

    fleet = Fleet(
        battery_range_km=float(data["fleet"]["battery_range_km"]),
        charging_time_min=float(data["fleet"]["charging_time_min"]),
        speed_kmh=float(data["fleet"]["speed_kmh"]),
        buses=buses,
    )

    # --- Weights ---
    weights_data = data.get("weights", {})
    weights = Weights(values={k: float(v) for k, v in weights_data.items()})

    # --- Metadata ---
    metadata = data.get("metadata", {})

    return ScenarioConfig(
        name=metadata.get("name", Path(path).stem),
        description=metadata.get("description", ""),
        route=route,
        fleet=fleet,
        weights=weights,
    )


def list_scenarios(directory: str) -> List[Tuple[str, str]]:
    """
    List all available scenario files in a directory.

    Returns:
        List of (scenario_name, file_path) tuples, sorted by filename.
    """
    scenario_dir = Path(directory)
    if not scenario_dir.exists():
        return []

    scenarios = []
    for f in sorted(scenario_dir.glob("*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                name = data.get("metadata", {}).get("name", f.stem)
                scenarios.append((name, str(f)))
        except Exception:
            # Skip malformed files
            scenarios.append((f.stem, str(f)))

    return scenarios
