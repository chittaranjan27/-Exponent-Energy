# Bus Charging Scheduler

Electric bus charging optimization for the Bengaluru–Kochi corridor. Built for the Exponent Energy take-home assignment.

## Quick Start

```bash
# Clone and install
git clone https://github.com/YOUR_USERNAME/ev-bus-scheduler.git
cd ev-bus-scheduler
pip install -r requirements.txt

# Run locally
streamlit run app.py
```

The app opens at `http://localhost:8501`. Select a scenario from the dropdown.

## Project Structure

```
├── app.py                    # Streamlit entry point
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── ARCHITECTURE.md           # Design rationale & extensibility
│
├── data/scenarios/           # Scenario YAML files
│   ├── scenario_1.yaml       # Even spacing
│   ├── scenario_2.yaml       # Bunched start
│   ├── scenario_3.yaml       # Asymmetric load
│   ├── scenario_4.yaml       # Operator-heavy (operator weight = 2.0)
│   └── scenario_5.yaml       # Worst case convergence
│
├── scheduler/                # Core scheduling engine
│   ├── models.py             # Domain dataclasses
│   ├── loader.py             # YAML → typed objects
│   ├── planner.py            # Feasible charging plan enumeration
│   ├── engine.py             # Greedy scheduler
│   └── rules.py              # Pluggable scoring rules
│
└── ui/                       # Streamlit view components
    ├── scenario_view.py      # Input data display
    ├── bus_timeline.py       # Per-bus timetable
    └── station_view.py       # Per-station queue
```

## How to Change a Weight

Weights live in each scenario's YAML file. Open any scenario file and edit the `weights` section:

```yaml
# data/scenarios/scenario_4.yaml
weights:
  individual_wait: 1.0
  operator_fairness: 2.0   # ← change this value
  overall_time: 1.0
```

That's it. Reload the app and the scheduler uses the new weight. No code changes needed.

## How to Add a New Rule

Adding a new rule takes 3 steps — no engine changes required:

### Step 1: Define the rule function in `scheduler/rules.py`

```python
def priority_bus_rule(candidate: CandidateEval, state: SchedulerState) -> float:
    """Give priority buses lower cost (they get scheduled first)."""
    # Example: buses with 'priority' in their ID get a bonus
    if "priority" in candidate.bus.id:
        return -50.0  # negative cost = bonus
    return 0.0
```

### Step 2: Register it in the DEFAULT_RULES list

```python
DEFAULT_RULES = [
    Rule(name="individual_wait", fn=individual_wait_rule),
    Rule(name="operator_fairness", fn=operator_fairness_rule),
    Rule(name="overall_time", fn=overall_time_rule),
    Rule(name="priority_bus", fn=priority_bus_rule),  # ← add this
]
```

### Step 3: Add the weight to your scenario YAML

```yaml
weights:
  individual_wait: 1.0
  operator_fairness: 1.0
  overall_time: 1.0
  priority_bus: 1.5    # ← add this
```

Done. The engine automatically picks up the new rule and weight.

## How to Add a New Scenario

1. Create a new YAML file in `data/scenarios/` (e.g., `scenario_6.yaml`)
2. Follow the format of existing scenarios — define metadata, route, fleet, and weights
3. The app automatically discovers all `.yaml` files in that directory

## How to Add a New Station

Add a segment and a charging station entry in the YAML:

```yaml
route:
  segments:
    - { from: "Bengaluru", to: "A", distance_km: 100 }
    - { from: "A", to: "E", distance_km: 60 }         # ← new segment
    - { from: "E", to: "B", distance_km: 60 }          # ← adjusted
    - { from: "B", to: "C", distance_km: 100 }
    - { from: "C", to: "D", distance_km: 120 }
    - { from: "D", to: "Kochi", distance_km: 100 }
  charging_stations:
    A: { chargers: 1 }
    E: { chargers: 2 }   # ← new station with 2 chargers
    B: { chargers: 1 }
    C: { chargers: 1 }
    D: { chargers: 1 }
```

No code changes. The planner and engine adapt automatically.

## Assumptions

1. **Bus speed**: 60 km/h constant (no traffic, no variation) — configurable in YAML
2. **Charging**: Always to full, always exactly 25 min — configurable in YAML
3. **No partial charging**: Buses either charge (full 25 min) or skip a station
4. **No endpoint scheduling**: Bengaluru and Kochi have slow chargers that handle pre-departure charging; they're not part of the scheduling problem
5. **Greedy ordering**: Buses are processed in departure-time order. Earlier-departing buses get first pick of station slots
6. **Deterministic tie-breaking**: When costs are equal, the plan with fewer charging stops wins; if still tied, bus ID determines order

## License

MIT
