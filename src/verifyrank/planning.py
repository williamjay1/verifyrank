"""Label-free, indivisible reference-audit planning and declared error bounds.

The planner reads reference metadata only; it never reads a reference's value.
Costs are supplied relative units, not estimated flight or monetary costs.
Recovery probabilities describe success in returning a usable historical result,
not label accuracy. Expected widths are sensitivities, never realised guarantees.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _field(reference, name, default=None):
    return reference.get(name, default) if isinstance(reference, Mapping) else getattr(reference, name, default)


def classify_interval(lower: float, upper: float, tolerance: float = .02) -> str:
    """Classify an entire interval; touching the tolerance boundary is not a direction."""
    lower, upper = _number(lower, "lower"), _number(upper, "upper")
    tolerance = _number(tolerance, "tolerance")
    if lower > upper or tolerance < 0:
        raise ValueError("bounds must be ordered and tolerance nonnegative")
    if lower > tolerance:
        return "positive"
    if upper < -tolerance:
        return "negative"
    if lower >= -tolerance and upper <= tolerance:
        return "practical_equivalence"
    return "undetermined"


def plan_references(coefficients: Mapping[str, float], references: Iterable,
                    cost_budget: float, strategy: str = "width_per_cost") -> dict:
    """Greedily schedule indivisible unknown references without reading labels.

    ``coefficients`` contains unique unknown-reference macro coefficients only.
    Sort by |C|/cost, or |C|*p/cost, and scan once, accepting an item only if its
    full cost fits the remaining budget. This is a heuristic, not a knapsack
    optimum. Separate budgets can therefore produce non-nested selected sets.
    ``None`` recovery probability means ideal success (p=1), explicitly returned.
    Known references must be omitted; no_followup can never be resolvable.
    """
    if strategy not in {"width_per_cost", "expected_width_per_cost"}:
        raise ValueError("unknown planning strategy")
    budget = _number(cost_budget, "cost_budget")
    if budget < 0:
        raise ValueError("cost_budget must be nonnegative")
    refs = {}
    for reference in references:
        key = _field(reference, "reference_id")
        if not isinstance(key, str) or not key or key in refs:
            raise ValueError("unique nonempty reference IDs required")
        refs[key] = reference
    initial, floor, structural_floor, candidates, defaulted = 0., 0., 0., [], []
    for key, raw_coefficient in coefficients.items():
        coefficient = _number(raw_coefficient, "coefficient")
        if key not in refs:
            raise ValueError(f"metadata missing for {key}")
        ref = refs[key]
        state, resolvable = _field(ref, "state"), _field(ref, "resolvable")
        if state not in {"ambiguous", "no_followup"}:
            raise ValueError("planning coefficients must contain unknown references only")
        if not isinstance(resolvable, bool):
            raise ValueError("resolvable must be boolean")
        if state == "no_followup" and resolvable:
            raise ValueError("no_followup has no historical result to recover")
        benefit = abs(coefficient)
        initial += benefit
        if not resolvable:
            floor += benefit
            structural_floor += benefit
            continue
        cost = _number(_field(ref, "cost"), "cost")
        if cost <= 0:
            raise ValueError("resolvable reference cost must be positive")
        probability = _field(ref, "recovery_probability")
        if probability is None:
            probability = 1.
            defaulted.append(key)
        probability = _number(probability, "recovery_probability")
        if not 0 <= probability <= 1:
            raise ValueError("recovery_probability must be between zero and one")
        if probability == 0:
            floor += benefit
            continue
        priority = benefit / cost
        if strategy == "expected_width_per_cost":
            priority *= probability
        if benefit > 0:
            candidates.append({"reference_id": key, "cost": cost,
                "coefficient_abs": benefit, "recovery_probability": probability,
                "priority": priority, "potential_width_reduction": benefit,
                "expected_width_reduction": benefit * probability})
    candidates.sort(key=lambda item: (-item["priority"], item["reference_id"]))
    selected, used = [], 0.
    for candidate in candidates:
        if candidate["priority"] > 0 and used + candidate["cost"] <= budget + 1e-12:
            selected.append(candidate)
            used += candidate["cost"]
    potential = math.fsum(item["potential_width_reduction"] for item in selected)
    expected = math.fsum(item["expected_width_reduction"] for item in selected)
    return {"strategy": strategy, "cost_budget": budget, "cost_used": used,
        "cost_remaining": max(0., budget - used), "selected": selected,
        "selected_count": len(selected), "eligible_nonzero_references": len(candidates),
        "initial_width": initial, "irreducible_width": floor,
        "structural_irreducible_width": structural_floor,
        "zero_recovery_probability_width": floor - structural_floor,
        "recoverable_width": max(0., initial - floor),
        "residual_width_if_all_selected_resolved": max(floor, initial - potential),
        "hypothetical_expected_residual_width": max(floor, initial - expected),
        "default_ideal_success_reference_count": len(defaulted),
        "optimality": "indivisible cost-feasible greedy heuristic; not knapsack optimal",
        "probability_interpretation": "supplied hypothetical recovery probabilities; None assumes ideal success; not label accuracy",
        "update_rule": "only a returned qualified binary result resolves a reference; failures remain unknown; recompute bounds before classifying"}


def robust_completion_interval(coefficients: Mapping[str, float],
                               observed_labels: Mapping[str, int], max_wrong: int = 0,
                               fixed_known_contribution: float = 0.) -> dict:
    """Exact bounds allowing at most r returned unique-reference labels to flip.

    This sensitivity concerns ``observed_labels`` only. A caller wishing to allow
    errors in original known labels must include their coefficients and labels
    here, rather than hide them in the fixed contribution. Absent results remain
    unknown. Coefficients have already been aggregated by true reference ID.
    The assumed error-count budget is not inferred from metadata or from truth.
    """
    if isinstance(max_wrong, bool) or not isinstance(max_wrong, int) or max_wrong < 0:
        raise ValueError("max_wrong must be a nonnegative integer")
    fixed = _number(fixed_known_contribution, "fixed_known_contribution")
    c = {key: _number(value, "coefficient") for key, value in coefficients.items()}
    if not set(observed_labels).issubset(c):
        raise ValueError("returned label has no coefficient")
    for value in observed_labels.values():
        if isinstance(value, bool) or value not in (0, 1):
            raise ValueError("returned labels must be binary numbers")
    known = fixed + math.fsum(c[key] * value for key, value in observed_labels.items())
    unknown = [value for key, value in c.items() if key not in observed_labels]
    nominal_lower = known + math.fsum(min(0., value) for value in unknown)
    nominal_upper = known + math.fsum(max(0., value) for value in unknown)
    changes = [c[key] * (1 - 2 * value) for key, value in observed_labels.items()]
    low_changes = sorted(value for value in changes if value < 0)[:max_wrong]
    high_changes = sorted((value for value in changes if value > 0), reverse=True)[:max_wrong]
    lower = nominal_lower + math.fsum(low_changes)
    upper = nominal_upper + math.fsum(high_changes)
    return {"lower": lower, "upper": upper, "interval_width": max(0., upper - lower),
        "nominal_lower": nominal_lower, "nominal_upper": nominal_upper,
        "max_wrong_returned_references": max_wrong,
        "returned_references": len(observed_labels), "unknown_references": len(unknown),
        "interpretation": "finite binary completion with at most the specified number of wrong supplied unique-reference labels; not measurement validation"}
