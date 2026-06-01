"""
Per-station queue view — for each charging station (A, B, C, D),
shows the ordered list of buses that charged there with times.
"""

import streamlit as st
import pandas as pd

from scheduler.models import ScenarioConfig, ScheduleResult


OPERATOR_ICONS = {
    "kpn": "🔵",
    "freshbus": "🟢",
    "flixbus": "🟠",
}

DIRECTION_ARROWS = {
    "BK": "→",
    "KB": "←",
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
    """Format a duration in minutes."""
    total_min = int(round(minutes))
    if total_min < 60:
        return f"{total_min}m"
    h = total_min // 60
    m = total_min % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


def render_station_view(result: ScheduleResult, config: ScenarioConfig):
    """Render per-station charging queues."""

    # Get station order from the route (forward direction)
    station_names = config.route.get_charging_stations("BK")

    # ── Station summary ──
    st.markdown("### 📊 Station Utilization Summary")
    summary_cols = st.columns(len(station_names))
    for i, name in enumerate(station_names):
        queue = result.station_queues.get(name, [])
        total_charges = len(queue)
        total_wait = sum(e["wait"] for e in queue)
        avg_wait = total_wait / total_charges if total_charges > 0 else 0
        max_wait = max((e["wait"] for e in queue), default=0)

        with summary_cols[i]:
            st.markdown(f"#### 🔌 Station {name}")
            st.metric("Total Charges", total_charges)
            st.metric("Avg Wait", _format_duration(avg_wait))
            st.metric("Max Wait", _format_duration(max_wait))

    st.markdown("---")

    # ── Detailed station queues ──
    st.markdown("### 📋 Charging Queues")

    for name in station_names:
        queue = result.station_queues.get(name, [])
        chargers = config.route.charging_stations[name].chargers

        st.markdown(f"#### 🔌 Station {name} ({chargers} charger{'s' if chargers > 1 else ''})")

        if not queue:
            st.info("No buses charged at this station.")
            continue

        queue_data = []
        for idx, event in enumerate(queue, 1):
            icon = OPERATOR_ICONS.get(event["operator"], "⚪")
            arrow = DIRECTION_ARROWS.get(event["direction"], "?")
            wait_str = _format_duration(event["wait"]) if event["wait"] > 0 else "—"

            queue_data.append({
                "#": idx,
                "Bus ID": event["bus_id"],
                "Operator": f"{icon} {event['operator'].upper()}",
                "Dir": arrow,
                "Arrival": _format_time(event["arrival"]),
                "Wait": wait_str,
                "Charge Start": _format_time(event["charge_start"]),
                "Charge End": _format_time(event["charge_end"]),
            })

        df_queue = pd.DataFrame(queue_data)

        # Highlight rows with wait > 0
        def highlight_wait(row):
            if row["Wait"] != "—":
                return ["background-color: rgba(239, 68, 68, 0.1)"] * len(row)
            return [""] * len(row)

        styled = df_queue.style.apply(highlight_wait, axis=1)
        st.dataframe(df_queue, width="stretch", hide_index=True)

        st.markdown("")  # spacer
