# Architecture

## Scheduling Approach

### Choice: Greedy Priority-Queue Scheduler with Pluggable Cost Functions

The scheduler processes buses in departure-time order. For each bus, it:

1. **Enumerates all feasible charging plans** — every valid subset of stations where no gap exceeds the battery range (240 km). For the current route, this yields 8 feasible plans per bus.
2. **Simulates each plan** against current station availability — computes arrival times, wait times, charging windows.
3. **Scores each plan** using a weighted sum of pluggable rules: `total_cost = Σ(weight_i × rule_i(candidate, state))`
4. **Commits the lowest-cost plan** — books the charger time slots, records the timeline.

### Why This Approach

| Criterion | Greedy + Cost Functions | MIP (Gurobi/CPLEX) | CP-SAT (OR-Tools) | Pure Simulation |
|-----------|:---:|:---:|:---:|:---:|
| Correct for 20 buses | ✅ | ✅ | ✅ | ⚠️ |
| Explainable decisions | ✅ | ❌ (black box) | ❌ | ✅ |
| Easy to add rules | ✅ (one function) | ⚠️ (constraints) | ⚠️ (constraints) | ❌ |
| Easy to tune weights | ✅ (YAML values) | ⚠️ (objective terms) | ⚠️ | N/A |
| Runs in <1s | ✅ | ⚠️ | ⚠️ | ✅ |
| Scales to 100+ buses | ✅ | ✅ | ✅ | ✅ |
| No solver dependency | ✅ | ❌ | ❌ | ✅ |

**Key advantages:**
- **Explainability**: Every decision traces to a cost comparison. In the interview, I can say "bus X got plan Y because it scored 45.2 vs 78.1 for plan Z, driven by 30 min less wait."
- **Extensibility**: A new rule is a Python function that takes `(candidate, state) → float`. No solver constraints to reformulate.
- **No dependencies**: Runs on any Python install, deploys to Streamlit Cloud without solver binaries.
- **Speed**: For 20 buses × 8 plans = 160 evaluations per scenario. Runs in milliseconds.

**Acknowledged trade-offs:**
- Greedy doesn't guarantee global optimality. A bus processed early might take a slot that, globally, should go to a later bus. For 20 buses with 15-min spacing, this is rarely an issue. For larger fleets, the cost function can be wrapped in a metaheuristic (simulated annealing) without changing the rule interface.

### Upgrade Path to Global Optimization

If needed, the same cost function plugs directly into:
- **Simulated annealing**: Randomly swap bus ordering, re-run greedy, keep improvements
- **Genetic algorithm**: Chromosome = bus processing order, fitness = total cost
- **Beam search**: Keep top-K partial schedules, expand each

None of these require changing the rules, weights, or data model.

---

## Data Structure Design

### Scenario as a Single YAML File

Each scenario is one YAML file containing everything the scheduler needs:

```yaml
metadata:     # Human-readable name and description
route:        # Segments + charging station configs
fleet:        # Battery specs + bus list
weights:      # Tunable cost function weights
```

### Design Rationale

1. **Self-contained**: One file = one complete scenario. No cross-file dependencies.
2. **Human-readable**: YAML supports comments, is easy to edit by hand.
3. **Typed parsing**: The loader converts YAML → Python dataclasses with validation.
4. **No code coupling**: The data structure doesn't import or reference any code.

### Key Fields and Why They Exist

| Field | Why | Future-proof for |
|-------|-----|-----------------|
| `segments[].distance_km` | Defines route geometry | Adding/removing stations = adding/removing segments |
| `charging_stations[name].chargers` | Number of chargers per station | Multi-charger upgrades (just change `1` → `2`) |
| `fleet.battery_range_km` | Maximum range per charge | Mixed fleets with different ranges |
| `fleet.charging_time_min` | Time to charge | Fast vs slow chargers |
| `fleet.speed_kmh` | Travel speed | Speed variations, different bus types |
| `buses[].operator` | Operator identity | Adding operators = just use a new name |
| `buses[].direction` | Travel direction | Multi-route systems |
| `weights.*` | Cost function weights | Any new rule gets a weight here |

---

## Anticipated Future Changes

Below is the full set of changes I anticipated when designing the data structure, and how each is handled:

### 1. More chargers per station
**Change**: Station B gets upgraded from 1 to 3 chargers.
**How**: Change `B: { chargers: 1 }` to `B: { chargers: 3 }` in the YAML.
**Code impact**: Zero. `StationTracker` already supports N chargers — it tracks N independent `charger_free_at` slots and assigns buses to the earliest-available charger.

### 2. New station added to route
**Change**: Station E is built between A and B.
**How**: Split the A→B segment into A→E and E→B in the YAML. Add `E: { chargers: 1 }` to charging_stations.
**Code impact**: Zero. The planner enumerates all subsets of whatever stations exist. The engine simulates whatever the planner generates.

### 3. Station removed from route
**Change**: Station A is decommissioned.
**How**: Remove A from `charging_stations`. Merge segments into Bengaluru→B (220 km).
**Code impact**: Zero.

### 4. New operator
**Change**: "RedBus" enters the market.
**How**: Add buses with `operator: "redbus"` in the fleet section.
**Code impact**: Zero. Operators are just strings — no enum, no registration.

### 5. More buses (50, 100, 500)
**Change**: Fleet grows from 20 to 100+ buses.
**How**: Add more bus entries to the YAML.
**Code impact**: Zero. Performance scales linearly: N buses × M plans × K rules. At 100 buses × 8 plans × 3 rules = 2,400 evaluations — still sub-second.

### 6. Different bus speeds
**Change**: Express buses travel at 80 km/h, regular at 60 km/h.
**How**: Add `speed_kmh` as a per-bus field in the YAML. Modify `Fleet` to support per-bus override.
**Code impact**: Minor — `simulate_plan` reads speed from bus instead of fleet config. ~5 lines changed.

### 7. Variable charging times
**Change**: Station B has fast chargers (15 min), others remain 25 min.
**How**: Add `charging_time_min` per station in the YAML.
**Code impact**: Minor — `simulate_plan` reads charge time from station config instead of fleet config. ~3 lines changed.

### 8. Priority buses
**Change**: Some buses have contractual priority at stations.
**How**: Add a `priority: true` field to bus entries. Add a `priority_bus` rule:
```python
def priority_bus_rule(candidate, state):
    return -100.0 if getattr(candidate.bus, 'priority', False) else 0.0
```
Add `priority_bus: 2.0` to weights.
**Code impact**: One new rule function + one weight in YAML.

### 9. Time-of-day electricity costs
**Change**: Charging between 22:00–06:00 is cheaper.
**How**: Add a `electricity_cost` rule that scores based on charge_start time:
```python
def electricity_cost_rule(candidate, state):
    # Penalize daytime charging
    peak_penalty = sum(
        10.0 for ev in candidate.charge_events
        if 360 <= ev.charge_start <= 1320  # 6AM-10PM
    )
    return peak_penalty
```
**Code impact**: One new rule function + one weight.

### 10. Driver shift constraints
**Change**: Drivers must rest for 30 min after 4 hours of driving.
**How**: Add a hard constraint in the planner or a high-penalty soft rule. The planner can filter out plans where any continuous driving segment exceeds 4 hours.
**Code impact**: One new validation in `planner.py` or one new rule.

### 11. Multiple routes sharing stations
**Change**: A second route (Chennai–Kochi) also uses stations B and C.
**How**: Station trackers are already keyed by station name. Run schedulers for both routes sharing the same station tracker state — or merge into one scenario with buses from both routes.
**Code impact**: Moderate — would need a multi-route scenario format. But the core engine and station tracking already support this (stations are shared resources, not route-specific).

### 12. Partial charging
**Change**: Buses can charge for less than 25 min (partial charge).
**How**: `ChargePlan` would include charge duration per station. The planner would generate plans with varying charge amounts. `ChargeEvent.charge_time` would vary.
**Code impact**: Moderate — planner generates more plan variants, simulation uses per-stop charge duration. Engine and rules unchanged.

### 13. Asymmetric route distances
**Change**: Route is not symmetric — northbound has a detour.
**How**: Already supported. `Route.get_cumulative_distances()` computes distances per direction from the segment list. If segments are asymmetric, distances are correctly asymmetric.
**Code impact**: Zero (already handled).

### 14. Weight changes for A/B testing
**Change**: Operations team wants to run the same scenario with 10 different weight configurations.
**How**: Duplicate the YAML with different weights, or (better) add a weight override in the UI:
```python
w = st.slider("Individual Wait Weight", 0.0, 5.0, config.weights.get("individual_wait"))
```
**Code impact**: ~3 lines in the UI to add sliders. Engine already takes weights as input.

---

## How to Change a Weight

Open the scenario YAML file and change one number:

```yaml
# Before
weights:
  individual_wait: 1.0
  operator_fairness: 1.0
  overall_time: 1.0

# After — emphasize operator fairness
weights:
  individual_wait: 1.0
  operator_fairness: 3.0    # ← changed from 1.0 to 3.0
  overall_time: 1.0
```

Reload the app. The scheduler re-runs with the new weight.

---

## How to Add a New Rule

### Example: Penalize plans with 3+ charging stops

```python
# In scheduler/rules.py

def charge_count_rule(candidate: CandidateEval, state: SchedulerState) -> float:
    """Penalize plans with many charging stops (more overhead)."""
    return candidate.charge_count * 10.0  # 10 penalty points per stop

# Add to registry:
DEFAULT_RULES.append(Rule(name="charge_count", fn=charge_count_rule))
```

```yaml
# In the scenario YAML:
weights:
  individual_wait: 1.0
  operator_fairness: 1.0
  overall_time: 1.0
  charge_count: 0.5          # ← new rule, low weight
```

The engine automatically finds the weight for `"charge_count"` and applies it. No other changes needed.

---

## Assumptions

1. **Constant speed**: All buses travel at the same speed (60 km/h). Configurable in YAML.
2. **Full charge only**: Buses always charge to 100%. No partial charging.
3. **No endpoint scheduling**: Bengaluru and Kochi handle pre-departure charging outside this system.
4. **Greedy is sufficient**: For 20 buses and 4 stations, greedy produces near-optimal results. Global optimality is not required for defensible schedules.
5. **No queue at station**: Buses wait "at the station" — there's no physical queue limit. If 5 buses are waiting, all 5 wait (they don't block the road).
6. **Deterministic**: Same input always produces the same output. No randomness.
7. **Time granularity**: Minutes. Sub-minute precision is not meaningful for bus scheduling.

---

## Code Quality Notes

- **No global state**: All state flows through function arguments and return values.
- **Type-safe**: Dataclasses with type hints throughout. No raw dicts in the core logic.
- **Tested via scenarios**: All 5 scenarios exercise different edge cases (even load, bunched, asymmetric, operator-heavy, worst-case convergence).
- **Separation of concerns**: `loader` (I/O) → `planner` (combinatorics) → `engine` (scheduling) → `rules` (scoring). Each can be tested independently.
