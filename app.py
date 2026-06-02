"""
Bus Charging Scheduler — Streamlit Application

A single-page app that:
  1. Lets you pick a scenario from a dropdown
  2. Shows the scenario input data
  3. Runs the scheduler and displays per-bus timetables
  4. Shows per-station charging queues

Built for the Exponent Energy take-home assignment.
"""

import streamlit as st
from pathlib import Path

from scheduler.loader import load_scenario, list_scenarios
from scheduler.engine import schedule
from scheduler.rules import DEFAULT_RULES
from ui.scenario_view import render_scenario_view
from ui.bus_timeline import render_bus_timelines
from ui.station_view import render_station_view


# ──────────────────────────────────────────────
#  Page config
# ──────────────────────────────────────────────

st.set_page_config(
    page_title="Bus Charging Scheduler",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────
#  Custom styling
# ──────────────────────────────────────────────

st.markdown("""
<style>
    /* Header styling */
    .main-header-container {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 0.2rem;
    }
    .main-header-emoji {
        font-size: 2.2rem;
    }
    .main-header-text {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #3B82F6, #8B5CF6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        line-height: 1.3;
        display: inline-block;
    }
    .sub-header {
        font-size: 1rem;
        color: #9CA3AF;
        margin-bottom: 1.5rem;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background-color: rgba(59, 130, 246, 0.05);
        border: 1px solid rgba(59, 130, 246, 0.15);
        border-radius: 0.5rem;
        padding: 0.75rem;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 20px;
        border-radius: 8px;
    }

    /* Expander */
    .streamlit-expanderHeader {
        font-size: 0.95rem;
    }

    /* Adjust top padding to prevent clipping under Streamlit's header */
    .block-container {
        padding-top: 4.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
#  Header
# ──────────────────────────────────────────────

st.markdown(
    '<div class="main-header-container">'
    '<span class="main-header-emoji">🚌</span>'
    '<span class="main-header-text">Bus Charging Scheduler</span>'
    '</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="sub-header">'
    'Electric bus charging optimization for the Bengaluru–Kochi corridor'
    '</p>',
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────
#  Scenario selection
# ──────────────────────────────────────────────

SCENARIO_DIR = Path(__file__).parent / "data" / "scenarios"
scenarios = list_scenarios(str(SCENARIO_DIR))

if not scenarios:
    st.error(f"No scenario files found in `{SCENARIO_DIR}`. Add `.yaml` files and restart.")
    st.stop()

scenario_names = [name for name, _ in scenarios]
selected_idx = st.selectbox(
    "📂 Select Scenario",
    range(len(scenarios)),
    format_func=lambda i: scenario_names[i],
    key="scenario_selector",
)


# ──────────────────────────────────────────────
#  Load & schedule
# ──────────────────────────────────────────────

@st.cache_data
def run_scheduler(path: str):
    """Load scenario and run scheduler (cached for performance)."""
    config = load_scenario(path)
    result = schedule(config)
    return config, result


try:
    config, result = run_scheduler(scenarios[selected_idx][1])
except Exception as e:
    st.error(f"Error loading or scheduling: {e}")
    st.stop()


# ──────────────────────────────────────────────
#  Quick stats bar
# ──────────────────────────────────────────────

st.markdown("---")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Total Buses", len(result.timelines))
with col2:
    avg_wait = sum(t.total_wait for t in result.timelines) / len(result.timelines)
    st.metric("Avg Wait", f"{avg_wait:.1f} min")
with col3:
    max_wait = max(t.total_wait for t in result.timelines)
    st.metric("Max Wait", f"{max_wait:.1f} min")
with col4:
    avg_trip = sum(t.total_trip_time for t in result.timelines) / len(result.timelines)
    st.metric("Avg Trip", f"{avg_trip:.0f} min")
with col5:
    total_charges = sum(len(t.charge_events) for t in result.timelines)
    st.metric("Total Charges", total_charges)

st.markdown("---")


# ──────────────────────────────────────────────
#  Tabbed views
# ──────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "📋 Scenario Input",
    "🚌 Bus Timetables",
    "🔌 Station Queues",
])

with tab1:
    render_scenario_view(config)

with tab2:
    render_bus_timelines(result, config)

with tab3:
    render_station_view(result, config)


# ──────────────────────────────────────────────
#  Footer
# ──────────────────────────────────────────────

st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #6B7280; font-size: 0.85rem;'>"
    "Built for Exponent Energy • "
    "Greedy priority-queue scheduler with pluggable cost functions"
    "</div>",
    unsafe_allow_html=True,
)
