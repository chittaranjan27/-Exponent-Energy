"""
Pluggable scoring rules for the scheduler.

Each rule is a function that takes a CandidateEval and SchedulerState,
and returns a float score (lower = better). The scheduler computes:

    total_cost = Σ (weight_i × rule_i(candidate, state))

Adding a new rule:
  1. Define a function: def my_rule(candidate, state) -> float
  2. Append Rule(name="my_rule", fn=my_rule) to DEFAULT_RULES
  3. Add weight "my_rule: 1.0" to the scenario YAML

That's it. No engine changes needed.
"""

from dataclasses import dataclass
from typing import Callable, List

from .models import Bus, BusTimeline


# ──────────────────────────────────────────────
#  Evaluation context
# ──────────────────────────────────────────────

@dataclass
class CandidateEval:
    """
    Everything the scoring rules need to know about a candidate plan.
    Populated by the engine before calling each rule.
    """
    bus: Bus
    total_wait: float        # Total wait time (min) for this bus under this plan
    total_trip_time: float   # Total trip time (min) from departure to arrival
    charge_count: int        # Number of charging stops in this plan


@dataclass
class SchedulerState:
    """
    Current state of the scheduler: all previously committed timelines.
    Rules can query this to make decisions based on global context.
    """
    committed: List[BusTimeline]

    def get_operator_waits(self, operator: str) -> List[float]:
        """Get wait times for all committed buses of a given operator."""
        return [t.total_wait for t in self.committed if t.bus.operator == operator]

    def get_operator_trip_times(self, operator: str) -> List[float]:
        """Get trip times for all committed buses of a given operator."""
        return [t.total_trip_time for t in self.committed if t.bus.operator == operator]

    def get_all_waits(self) -> List[float]:
        """Get wait times for all committed buses."""
        return [t.total_wait for t in self.committed]


# ──────────────────────────────────────────────
#  Built-in rule functions
# ──────────────────────────────────────────────

def individual_wait_rule(candidate: CandidateEval, state: SchedulerState) -> float:
    """
    Penalize individual bus wait time.

    Score = this bus's total wait time (minutes).
    Lower = better. A bus that doesn't wait scores 0.
    """
    return candidate.total_wait


def operator_fairness_rule(candidate: CandidateEval, state: SchedulerState) -> float:
    """
    Penalize unfair wait distribution within an operator's fleet.

    Score = max wait time among all of this operator's buses (committed + current).
    This protects against any single bus of an operator being stuck with
    excessive wait. Higher operator weight → stronger outlier protection.

    Why max and not average? Average dilutes outliers. Max ensures the
    scheduler actively avoids worst-case treatment for any operator's bus.
    """
    existing_waits = state.get_operator_waits(candidate.bus.operator)
    all_waits = existing_waits + [candidate.total_wait]
    return max(all_waits)


def overall_time_rule(candidate: CandidateEval, state: SchedulerState) -> float:
    """
    Penalize trip overhead (wait + extra charging time).

    Score = total wait + extra charging time beyond the minimum 2 stops.
    Base travel time is fixed (same route, same speed), so we only score
    the controllable overhead. This keeps overall_time comparable in
    magnitude to individual_wait, enabling meaningful weight tuning.

    A 2-stop plan with 0 wait scores 0.
    A 3-stop plan with 0 wait scores 25 (one extra 25-min charge).
    A 2-stop plan with 40 min wait scores 40.
    """
    # Minimum charging stops needed is 2 (for 540 km route with 240 km range)
    # Extra charging overhead = (charge_count - 2) * 25 min
    min_charges = 2
    extra_charge_time = max(0, (candidate.charge_count - min_charges)) * 25.0
    return candidate.total_wait + extra_charge_time


# ──────────────────────────────────────────────
#  Rule registry
# ──────────────────────────────────────────────

@dataclass
class Rule:
    """A named scoring rule with its weight key and function."""
    name: str  # Must match a key in Weights.values
    fn: Callable[[CandidateEval, SchedulerState], float]


# Default rules shipped with the scheduler.
# To add a new rule: append Rule(name="my_rule", fn=my_rule_fn) here.
DEFAULT_RULES: List[Rule] = [
    Rule(name="individual_wait", fn=individual_wait_rule),
    Rule(name="operator_fairness", fn=operator_fairness_rule),
    Rule(name="overall_time", fn=overall_time_rule),
]
