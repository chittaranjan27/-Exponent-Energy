"""
Scenario input view — displays the raw scenario data so reviewers
can see exactly what's being fed to the scheduler.
"""

import streamlit as st
import pandas as pd

from scheduler.models import ScenarioConfig


OPERATOR_COLORS = {
    "kpn": "#3B82F6",       # Blue
    "freshbus": "#10B981",  # Green
    "flixbus": "#F59E0B",   # Amber
}

DIRECTION_LABELS = {
    "BK": "Bengaluru → Kochi",
    "KB": "Kochi → Bengaluru",
}


def render_scenario_view(config: ScenarioConfig):
    """Render the scenario input data."""

    # ── Description ──
    st.markdown(f"*{config.description}*")

    col1, col2 = st.columns([1, 1])

    with col1:
        # ── Route Info ──
        st.markdown("### 🛣️ Route")
        route_data = []
        cumulative = 0
        for seg in config.route.segments:
            cumulative += seg.distance_km
            route_data.append({
                "Segment": f"{seg.from_stop} → {seg.to_stop}",
                "Distance": f"{seg.distance_km:.0f} km",
                "Cumulative": f"{cumulative:.0f} km",
            })

        df_route = pd.DataFrame(route_data)
        st.dataframe(df_route, use_container_width=True, hide_index=True)

        # ── Stations ──
        st.markdown("### 🔌 Charging Stations")
        station_data = []
        for name, cfg in config.route.charging_stations.items():
            station_data.append({
                "Station": name,
                "Chargers": cfg.chargers,
            })
        df_stations = pd.DataFrame(station_data)
        st.dataframe(df_stations, use_container_width=True, hide_index=True)

    with col2:
        # ── Fleet Constants ──
        st.markdown("### ⚡ Fleet Configuration")
        st.markdown(f"""
| Parameter | Value |
|-----------|-------|
| Battery Range | **{config.fleet.battery_range_km:.0f} km** |
| Charging Time | **{config.fleet.charging_time_min:.0f} min** (to full) |
| Speed | **{config.fleet.speed_kmh:.0f} km/h** |
| Total Buses | **{len(config.fleet.buses)}** |
        """)

        # ── Weights ──
        st.markdown("### ⚖️ Optimization Weights")
        weight_data = []
        for name, val in config.weights.values.items():
            label = name.replace("_", " ").title()
            weight_data.append({"Rule": label, "Weight": val})
        df_weights = pd.DataFrame(weight_data)
        st.dataframe(df_weights, use_container_width=True, hide_index=True)

    # ── Bus Schedule ──
    st.markdown("### 🚌 Departure Schedule")

    bus_data = []
    for bus in config.fleet.buses:
        color = OPERATOR_COLORS.get(bus.operator, "#888")
        bus_data.append({
            "Bus ID": bus.id,
            "Operator": bus.operator.upper(),
            "Direction": DIRECTION_LABELS.get(bus.direction, bus.direction),
            "Departure": bus.departure,
        })

    df_buses = pd.DataFrame(bus_data)

    # Split by direction
    bk_buses = df_buses[df_buses["Direction"] == "Bengaluru → Kochi"]
    kb_buses = df_buses[df_buses["Direction"] == "Kochi → Bengaluru"]

    col_bk, col_kb = st.columns(2)
    with col_bk:
        st.markdown(f"**Bengaluru → Kochi** ({len(bk_buses)} buses)")
        if not bk_buses.empty:
            st.dataframe(bk_buses, use_container_width=True, hide_index=True)
    with col_kb:
        st.markdown(f"**Kochi → Bengaluru** ({len(kb_buses)} buses)")
        if not kb_buses.empty:
            st.dataframe(kb_buses, use_container_width=True, hide_index=True)
