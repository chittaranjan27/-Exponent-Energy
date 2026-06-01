"""
Per-bus timetable view — shows the full timeline for each bus:
departure → [arrive station → wait → charge → depart] × N → arrival.
"""

import streamlit as st
import pandas as pd


from scheduler.models import ScenarioConfig, ScheduleResult, BusTimeline


OPERATOR_COLORS = {
    "kpn": "🔵",
    "freshbus": "🟢",
    "flixbus": "🟠",
}

DIRECTION_LABELS = {
    "BK": "Bengaluru → Kochi",
    "KB": "Kochi → Bengaluru",
}


def _format_time(minutes: float) -> str:
    """Convert minutes from midnight to HH:MM format."""
    total_min = int(round(minutes))
    h = total_min // 60
    m = total_min % 60
    if h >= 24:
        return f"{h - 24:02d}:{m:02d} (+1d)"
    return f"{h:02d}:{m:02d}"


def _format_duration(minutes: float) -> str:
    """Format a duration in minutes as Xh Ym."""
    total_min = int(round(minutes))
    if total_min < 60:
        return f"{total_min}m"
    h = total_min // 60
    m = total_min % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


def render_bus_timelines(result: ScheduleResult, config: ScenarioConfig):
    """Render per-bus timetables with filtering."""

    # ── Filters ──
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        operators = sorted(set(tl.bus.operator for tl in result.timelines))
        selected_operator = st.selectbox(
            "Filter by Operator",
            ["All"] + [op.upper() for op in operators],
            key="bus_operator_filter",
        )
    with col_f2:
        selected_direction = st.selectbox(
            "Filter by Direction",
            ["All", "Bengaluru → Kochi", "Kochi → Bengaluru"],
            key="bus_direction_filter",
        )
    with col_f3:
        sort_by = st.selectbox(
            "Sort by",
            ["Departure Time", "Total Wait (desc)", "Trip Time (desc)"],
            key="bus_sort",
        )

    # ── Filter timelines ──
    filtered = result.timelines
    if selected_operator != "All":
        filtered = [t for t in filtered if t.bus.operator.upper() == selected_operator]
    if selected_direction == "Bengaluru → Kochi":
        filtered = [t for t in filtered if t.bus.direction == "BK"]
    elif selected_direction == "Kochi → Bengaluru":
        filtered = [t for t in filtered if t.bus.direction == "KB"]

    # Sort
    if sort_by == "Total Wait (desc)":
        filtered = sorted(filtered, key=lambda t: t.total_wait, reverse=True)
    elif sort_by == "Trip Time (desc)":
        filtered = sorted(filtered, key=lambda t: t.total_trip_time, reverse=True)
    else:
        filtered = sorted(filtered, key=lambda t: t.departure_time)

    # ── Summary table ──
    st.markdown("### 📊 Summary")
    summary_data = []
    for tl in filtered:
        icon = OPERATOR_COLORS.get(tl.bus.operator, "⚪")
        summary_data.append({
            "Bus ID": tl.bus.id,
            "Operator": f"{icon} {tl.bus.operator.upper()}",
            "Direction": DIRECTION_LABELS.get(tl.bus.direction, tl.bus.direction),
            "Departure": _format_time(tl.departure_time),
            "Arrival": _format_time(tl.arrival_time),
            "Stations": " → ".join(tl.charge_plan.stations),
            "Charges": len(tl.charge_events),
            "Wait": _format_duration(tl.total_wait),
            "Trip Time": _format_duration(tl.total_trip_time),
        })
    df_summary = pd.DataFrame(summary_data)
    st.dataframe(df_summary, width="stretch", hide_index=True)

    # ── Detailed per-bus timelines ──
    st.markdown("### 📋 Detailed Timelines")

    for tl in filtered:
        icon = OPERATOR_COLORS.get(tl.bus.operator, "⚪")
        dir_label = DIRECTION_LABELS.get(tl.bus.direction, tl.bus.direction)
        wait_str = _format_duration(tl.total_wait)
        trip_str = _format_duration(tl.total_trip_time)

        header = (
            f"{icon} **{tl.bus.id}** — {tl.bus.operator.upper()} — {dir_label}"
        )
        subheader = (
            f"Depart {_format_time(tl.departure_time)} → "
            f"Arrive {_format_time(tl.arrival_time)} | "
            f"Trip: {trip_str} | Wait: {wait_str}"
        )

        with st.expander(f"{header}  \n{subheader}", expanded=False):
            # Build step-by-step timeline
            steps = []
            stops = config.route.get_stops(tl.bus.direction)
            origin = stops[0]
            destination = stops[-1]
            cum_dist = config.route.get_cumulative_distances(tl.bus.direction)

            steps.append({
                "Step": "🚌 Depart",
                "Location": origin,
                "Time": _format_time(tl.departure_time),
                "Details": f"Range: {config.fleet.battery_range_km:.0f} km",
            })

            current_time = tl.departure_time
            current_pos = origin
            current_range = config.fleet.battery_range_km

            for ev in tl.charge_events:
                # Travel step
                travel_dist = cum_dist[ev.station] - cum_dist[current_pos]
                travel_time = ev.arrival_time - current_time
                steps.append({
                    "Step": "🚗 Travel",
                    "Location": f"{current_pos} → {ev.station}",
                    "Time": f"{_format_time(current_time)} → {_format_time(ev.arrival_time)}",
                    "Details": f"{travel_dist:.0f} km, {_format_duration(travel_time)}",
                })

                # Arrive at station
                steps.append({
                    "Step": "📍 Arrive",
                    "Location": f"Station {ev.station}",
                    "Time": _format_time(ev.arrival_time),
                    "Details": f"Range: {ev.range_on_arrival_km:.0f} km",
                })

                # Wait (if any)
                if ev.wait_time > 0:
                    steps.append({
                        "Step": "⏳ Wait",
                        "Location": f"Station {ev.station}",
                        "Time": f"{_format_time(ev.arrival_time)} → {_format_time(ev.charge_start)}",
                        "Details": f"Wait: {_format_duration(ev.wait_time)}",
                    })

                # Charge
                steps.append({
                    "Step": "🔌 Charge",
                    "Location": f"Station {ev.station}",
                    "Time": f"{_format_time(ev.charge_start)} → {_format_time(ev.charge_end)}",
                    "Details": f"{config.fleet.charging_time_min:.0f} min → Full ({config.fleet.battery_range_km:.0f} km)",
                })

                current_time = ev.charge_end
                current_pos = ev.station
                current_range = config.fleet.battery_range_km

            # Final travel leg
            final_dist = cum_dist[destination] - cum_dist[current_pos]
            steps.append({
                "Step": "🚗 Travel",
                "Location": f"{current_pos} → {destination}",
                "Time": f"{_format_time(current_time)} → {_format_time(tl.arrival_time)}",
                "Details": f"{final_dist:.0f} km, {_format_duration(tl.arrival_time - current_time)}",
            })

            # Arrive at destination
            final_range = current_range - final_dist
            steps.append({
                "Step": "🏁 Arrive",
                "Location": destination,
                "Time": _format_time(tl.arrival_time),
                "Details": f"Range: {final_range:.0f} km",
            })

            df_steps = pd.DataFrame(steps)
            st.dataframe(df_steps, width="stretch", hide_index=True)
