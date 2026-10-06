"""Strict data contract and finite binary reference-completion arithmetic.

Only Python's standard library is required. References identify outcomes, not
necessarily subjects: distinct observations of the same subject need distinct
reference IDs. A no-follow-up slot has no actual shared observation identity.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

STATES = frozenset({"positive", "negative", "ambiguous", "no_followup"})
RESOLVED = frozenset({"positive", "negative"})
DECISION_FIELDS = ("decision_id", "policy", "reference_id", "weight", "budget")
REFERENCE_FIELDS = ("reference_id", "state", "value", "resolvable", "cost")
OPTIONAL_REFERENCE_FIELDS = ("recovery_probability",)


class ValidationError(ValueError):
    """The input does not satisfy the frozen-policy evidence contract."""


@dataclass(frozen=True, slots=True)
class Reference:
    reference_id: str
    state: str
    value: int | None
    resolvable: bool
    cost: float
    recovery_probability: float | None = None


@dataclass(frozen=True, slots=True)
class DecisionWeight:
    decision_id: str
    policy: str
    reference_id: str
    weight: float
    budget: float


@dataclass(frozen=True, slots=True)
class Dataset:
    decisions: tuple[DecisionWeight, ...]
    references: tuple[Reference, ...]


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationError(f"{field} must be a nonempty string without outer whitespace")
    return value


def _number(value, field: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a finite number, not a boolean")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValidationError(f"{field} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValidationError(f"{field} must be finite")
    return result


def _boolean(value, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false", "0", "1"}:
        return value.lower() in {"true", "1"}
    raise ValidationError(f"{field} must be true/false (CSV also accepts 1/0)")


def _check_fields(row: Mapping, required: tuple, optional: tuple = ()) -> None:
    if not isinstance(row, Mapping):
        raise ValidationError("each record must be an object")
    missing = set(required) - row.keys()
    extra = row.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValidationError(f"invalid fields: missing={sorted(missing)}, extra={sorted(str(x) for x in extra)}")


def _from_records(decisions, references) -> Dataset:
    if not isinstance(decisions, list) or not isinstance(references, list):
        raise ValidationError("decisions and references must be arrays of records")
    ds, refs = [], []
    for row in decisions:
        _check_fields(row, DECISION_FIELDS)
        ds.append(DecisionWeight(*(_text(row[k], k) for k in DECISION_FIELDS[:3]),
                                 _number(row["weight"], "weight"),
                                 _number(row["budget"], "budget")))
    for row in references:
        _check_fields(row, REFERENCE_FIELDS, OPTIONAL_REFERENCE_FIELDS)
        value = None if row["value"] in (None, "") else _number(row["value"], "value")
        prob = row.get("recovery_probability")
        prob = None if prob in (None, "") else _number(prob, "recovery_probability")
        refs.append(Reference(_text(row["reference_id"], "reference_id"),
                              _text(row["state"], "state"), value,
                              _boolean(row["resolvable"], "resolvable"),
                              _number(row["cost"], "cost"), prob))
    return validate(Dataset(tuple(ds), tuple(refs)))


def _csv_records(path: str | Path, required: tuple, optional: tuple = ()) -> list[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames
        if not headers or len(headers) != len(set(headers)):
            raise ValidationError(f"missing or duplicated CSV headers: {path}")
        _check_fields(dict.fromkeys(headers), required, optional)
        records = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in records):
            raise ValidationError(f"CSV record has too many or too few fields: {path}")
        return records


def load_csv(decisions_path: str | Path, references_path: str | Path) -> Dataset:
    """Read and validate two CSVs without modifying either input."""
    return _from_records(_csv_records(decisions_path, DECISION_FIELDS),
                         _csv_records(references_path, REFERENCE_FIELDS, OPTIONAL_REFERENCE_FIELDS))


def load_json(path: str | Path) -> Dataset:
    """Read an object with exactly decisions and references record arrays."""
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValidationError(f"duplicated JSON object key: {key}")
            obj[key] = value
        return obj
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            obj = json.load(handle, object_pairs_hook=unique_object)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc
    _check_fields(obj, ("decisions", "references"))
    if not isinstance(obj["decisions"], list) or not isinstance(obj["references"], list):
        raise ValidationError("decisions and references must be arrays of records")
    for row in obj["decisions"]:
        _check_fields(row, DECISION_FIELDS)
        for key in ("weight", "budget"):
            if isinstance(row[key], bool) or not isinstance(row[key], (int, float)):
                raise ValidationError(f"JSON {key} must be a number")
    for row in obj["references"]:
        _check_fields(row, REFERENCE_FIELDS, OPTIONAL_REFERENCE_FIELDS)
        if not isinstance(row["resolvable"], bool):
            raise ValidationError("JSON resolvable must be a boolean")
        for key in ("value", "cost", "recovery_probability"):
            value = row.get(key)
            if value is None and key != "cost":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"JSON {key} must be numeric or an allowed null")
    return _from_records(obj["decisions"], obj["references"])


def validate(data: Dataset) -> Dataset:
    """Validate identities, evidence states, equal inventories and budgets.

    Requires a complete policy-by-decision panel. Explicit zero-weight rows keep
    common candidate inventories auditable; missing rows are not filled in.
    """
    if not isinstance(data, Dataset) or not data.decisions or not data.references:
        raise ValidationError("nonempty Dataset decisions and references are required")
    if not isinstance(data.decisions, tuple) or not isinstance(data.references, tuple):
        raise ValidationError("Dataset rows must be immutable tuples")
    refs = {}
    for ref in data.references:
        if not isinstance(ref, Reference):
            raise ValidationError("references must contain Reference objects")
        _text(ref.reference_id, "reference_id")
        if ref.reference_id in refs:
            raise ValidationError(f"duplicate reference_id: {ref.reference_id}")
        refs[ref.reference_id] = ref
        if ref.state not in STATES:
            raise ValidationError(f"invalid state for {ref.reference_id}: {ref.state}")
        if not isinstance(ref.resolvable, bool):
            raise ValidationError("resolvable must be a boolean")
        if _number(ref.cost, "cost") <= 0:
            raise ValidationError("cost must be strictly positive")
        if ref.recovery_probability is not None and not 0 <= _number(ref.recovery_probability, "recovery_probability") <= 1:
            raise ValidationError("recovery_probability must be in [0,1]")
        if ref.state in RESOLVED:
            expected = 1 if ref.state == "positive" else 0
            if isinstance(ref.value, bool) or not isinstance(ref.value, (int, float)) or ref.value != expected:
                raise ValidationError(f"{ref.state} requires value={expected}: {ref.reference_id}")
        elif ref.value is not None:
            raise ValidationError(f"unknown reference must have null/blank value: {ref.reference_id}")
        if ref.state == "no_followup" and ref.resolvable:
            raise ValidationError("no_followup cannot be resolvable; new observations define a new task")
    groups = defaultdict(list)
    keys, policies, dates, ref_dates = set(), set(), set(), defaultdict(set)
    for row in data.decisions:
        if not isinstance(row, DecisionWeight):
            raise ValidationError("decisions must contain DecisionWeight objects")
        for field in DECISION_FIELDS[:3]:
            _text(getattr(row, field), field)
        key = (row.decision_id, row.policy, row.reference_id)
        if key in keys:
            raise ValidationError(f"duplicate decision-policy-reference row: {key}")
        keys.add(key)
        if row.reference_id not in refs:
            raise ValidationError(f"missing reference: {row.reference_id}")
        if not isinstance(row.weight, (int, float)) or not isinstance(row.budget, (int, float)):
            raise ValidationError("direct API weight and budget must be numeric, not numeric strings")
        if not 0 <= _number(row.weight, "weight") <= 1:
            raise ValidationError("selection weight must be in [0,1]")
        if _number(row.budget, "budget") <= 0:
            raise ValidationError("budget must be strictly positive")
        groups[row.decision_id, row.policy].append(row)
        policies.add(row.policy)
        dates.add(row.decision_id)
        ref_dates[row.reference_id].add(row.decision_id)
    for ref_id, used_dates in ref_dates.items():
        if refs[ref_id].state == "no_followup" and len(used_dates) > 1:
            raise ValidationError("no_followup reference IDs must be decision-specific")
    for date in sorted(dates):
        inventory, budget = None, None
        for policy in sorted(policies):
            rows = groups.get((date, policy))
            if not rows:
                raise ValidationError(f"missing policy {policy} on decision {date}")
            b = rows[0].budget
            if any(not math.isclose(row.budget, b, rel_tol=1e-10, abs_tol=1e-10) for row in rows):
                raise ValidationError(f"inconsistent budget within {date}/{policy}")
            if not math.isclose(math.fsum(row.weight for row in rows), b, rel_tol=1e-10, abs_tol=1e-10):
                raise ValidationError(f"selection weights must sum to budget: {date}/{policy}")
            inv = {row.reference_id for row in rows}
            if inventory is not None and inv != inventory:
                raise ValidationError(f"policies must share the complete reference inventory on {date}")
            if budget is not None and not math.isclose(b, budget, rel_tol=1e-10, abs_tol=1e-10):
                raise ValidationError(f"paired policies require the same budget on {date}")
            inventory, budget = inv, b
    return data


def prioritize(coefficients: Mapping[str, float], references: Iterable[Reference]) -> list[dict]:
    """Label-free unique-reference order for potential width reduction.

    Reads only metadata and coefficients, never Reference.value. This is an
    equal-cost potential-reduction order, not a cost-aware optimizer.
    """
    refs = {}
    for ref in references:
        if ref.reference_id in refs:
            raise ValidationError(f"duplicate priority reference: {ref.reference_id}")
        if ref.state not in STATES or not isinstance(ref.resolvable, bool):
            raise ValidationError("invalid priority reference metadata")
        if _number(ref.cost, "cost") <= 0:
            raise ValidationError("cost must be positive")
        if ref.recovery_probability is not None and not 0 <= _number(ref.recovery_probability, "recovery_probability") <= 1:
            raise ValidationError("recovery_probability must be in [0,1]")
        refs[ref.reference_id] = ref
    rows = []
    for ref_id, coefficient in coefficients.items():
        if ref_id not in refs:
            raise ValidationError(f"unknown priority reference: {ref_id}")
        coefficient = _number(coefficient, "coefficient")
        ref = refs[ref_id]
        if ref.state in RESOLVED:
            raise ValidationError("prioritization coefficients must contain unresolved references only")
        if ref.state == "no_followup" and ref.resolvable:
            raise ValidationError("no_followup cannot be resolvable")
        probability = 1.0 if ref.recovery_probability is None else ref.recovery_probability
        eligible = ref.state == "ambiguous" and ref.resolvable and probability > 0
        reason = "" if eligible else ("no_actual_followup" if ref.state == "no_followup" else
                                      "not_resolvable" if not ref.resolvable else "zero_recovery_probability")
        rows.append({"reference_id": ref_id, "coefficient": coefficient,
                     "potential_width_reduction": abs(coefficient), "state": ref.state,
                     "eligible": eligible, "blocked_reason": reason, "cost": ref.cost,
                     "recovery_probability": probability})
    return sorted(rows, key=lambda row: (not row["eligible"], -row["potential_width_reduction"], row["reference_id"]))


def _completion(coefficients, refs) -> dict:
    known = math.fsum(c * refs[r].value for r, c in coefficients.items() if refs[r].state in RESOLVED)
    unknown = {r: c for r, c in coefficients.items() if refs[r].state not in RESOLVED}
    lower = known + math.fsum(min(0.0, c) for c in unknown.values())
    upper = known + math.fsum(max(0.0, c) for c in unknown.values())
    state_width = {state: math.fsum(abs(c) for r, c in unknown.items() if refs[r].state == state)
                   for state in ("ambiguous", "no_followup")}
    return {"known_contribution": known, "lower": lower, "upper": upper,
            "width": math.fsum(abs(c) for c in unknown.values()),
            "ambiguous_width": state_width["ambiguous"],
            "irreducible_no_followup_width": state_width["no_followup"]}


def evaluate(data: Dataset, *, tolerance: float = 0.02,
             comparisons: Iterable[tuple[str, str]] | None = None,
             cost_budget: float | None = None, strategy: str = "width_per_cost") -> dict:
    """Evaluate frozen weights and joint shared-outcome completion intervals.

    Conditional scores normalize each policy by its own verified selected mass.
    Macro conditional differences use common-defined dates; completion uses all
    dates with equal weight and one binary variable per shared reference ID.
    """
    from .planning import classify_interval, plan_references
    validate(data)
    tolerance = _number(tolerance, "tolerance")
    if tolerance < 0:
        raise ValidationError("tolerance must be nonnegative")
    if cost_budget is not None and _number(cost_budget, "cost_budget") < 0:
        raise ValidationError("cost_budget must be nonnegative")
    if strategy not in {"width_per_cost", "expected_width_per_cost"}:
        raise ValidationError("unknown planning strategy")
    refs = {ref.reference_id: ref for ref in data.references}
    policies = sorted({row.policy for row in data.decisions})
    dates = sorted({row.decision_id for row in data.decisions})
    pairs = list(itertools.combinations(policies, 2)) if comparisons is None else list(comparisons)
    if len(set(pairs)) != len(pairs):
        raise ValidationError("duplicate comparison")
    for a, b in pairs:
        if a == b or a not in policies or b not in policies:
            raise ValidationError("comparison must name two different observed policies")
    groups = defaultdict(dict)
    budgets = {}
    for row in data.decisions:
        groups[row.decision_id, row.policy][row.reference_id] = row.weight
        budgets[row.decision_id] = row.budget
    daily_policy, lookup = [], {}
    for date in dates:
        m = budgets[date]
        for policy in policies:
            weights = groups[date, policy]
            known_mass = math.fsum(w for r, w in weights.items() if refs[r].state in RESOLVED)
            positive_mass = math.fsum(w * refs[r].value for r, w in weights.items() if refs[r].state in RESOLVED)
            unknown_mass = math.fsum(w for r, w in weights.items() if refs[r].state not in RESOLVED)
            row = {"decision_id": date, "policy": policy, "candidate_count": len(weights),
                   "budget": m, "verified_selected_mass": known_mass,
                   "known_positive_selected_mass": positive_mass, "unknown_selected_mass": unknown_mass,
                   "conditional_score": positive_mass / known_mass if known_mass > 0 else None,
                   "conditional_defined": known_mass > 0,
                   "completion_lower": positive_mass / m,
                   "completion_upper": (positive_mass + unknown_mass) / m}
            daily_policy.append(row)
            lookup[date, policy] = row
    daily_comparison, macro_comparison, priority, plans = [], [], [], []
    for a, b in pairs:
        global_terms = defaultdict(list)
        conditional, outer_lower, outer_upper = [], [], []
        for date in dates:
            wa, wb, m = groups[date, a], groups[date, b], budgets[date]
            coefficients = {r: (wa[r] - wb[r]) / m for r in wa}
            interval = _completion(coefficients, refs)
            for r, c in coefficients.items():
                global_terms[r].append(c / len(dates))
            sa, sb = lookup[date, a]["conditional_score"], lookup[date, b]["conditional_score"]
            difference = sa - sb if sa is not None and sb is not None else None
            if difference is not None:
                conditional.append(difference)
            daily_comparison.append({"decision_id": date, "policy_a": a, "policy_b": b,
                                     "conditional_difference": difference, **interval,
                                     "interval_classification": classify_interval(interval["lower"], interval["upper"], tolerance)})
            outer_lower.append(interval["lower"])
            outer_upper.append(interval["upper"])
        coefficients = {r: math.fsum(terms) for r, terms in global_terms.items()}
        interval = _completion(coefficients, refs)
        macro = {"policy_a": a, "policy_b": b, "decision_count": len(dates),
                 "conditional_defined_dates": len(conditional),
                 "conditional_difference": math.fsum(conditional) / len(conditional) if conditional else None,
                 **interval, "interval_classification": classify_interval(interval["lower"], interval["upper"], tolerance),
                 "tolerance": tolerance,
                 "daily_outer_lower": math.fsum(outer_lower) / len(dates),
                 "daily_outer_upper": math.fsum(outer_upper) / len(dates)}
        macro_comparison.append(macro)
        unknown = {r: c for r, c in coefficients.items() if refs[r].state not in RESOLVED}
        priority.extend({"policy_a": a, "policy_b": b, **row} for row in prioritize(unknown, data.references))
        if cost_budget is not None:
            plans.append({"policy_a": a, "policy_b": b,
                          **plan_references(unknown, data.references, cost_budget=cost_budget, strategy=strategy)})
    macro_policy = []
    for policy in policies:
        rows = [lookup[date, policy] for date in dates]
        defined = [row["conditional_score"] for row in rows if row["conditional_score"] is not None]
        macro_policy.append({"policy": policy, "decision_count": len(dates),
                             "conditional_defined_dates": len(defined),
                             "conditional_score": math.fsum(defined) / len(defined) if defined else None,
                             "completion_lower": math.fsum(row["completion_lower"] for row in rows) / len(rows),
                             "completion_upper": math.fsum(row["completion_upper"] for row in rows) / len(rows)})
    used = {row.reference_id for row in data.decisions}
    return {"software": "verifyrank", "version": "0.2.0", "status": "prepared_public_release",
            "metadata": {"decision_count": len(dates), "policy_count": len(policies),
                         "weight_rows": len(data.decisions), "reference_count": len(refs),
                         "used_reference_count": len(used), "unused_reference_count": len(refs) - len(used),
                         "tolerance": tolerance, "source_selection": "precomputed frozen weights; never reranked",
                         "conditional_estimand": "verified selected-mass ratio, per policy",
                         "macro_estimand": "equal-decision contrast with shared reference outcomes",
                         "interval_kind": "binary reference-completion range, not a confidence interval",
                         "limitations": ["Input history validity, reference qualification and weight provenance require adapter audits.",
                                         "Known labels are taken as supplied; no measurement-error model is fitted.",
                                         "No-follow-up slots are hypothetical and cannot be resolved as archived observations.",
                                         "Software correctness does not establish field deployment benefit or causal effects.",
                                         "This version is prepared for public release; no DOI has been assigned."]},
            "daily_policy": daily_policy, "macro_policy": macro_policy,
            "daily_comparison": daily_comparison, "macro_comparison": macro_comparison,
            "priority": priority, "plans": plans}
