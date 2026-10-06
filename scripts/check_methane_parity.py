"""Local adapter parity check; ships code only, no methane records.

Uses existing frozen selection weights, never reconstructs or fits policy scores.
Only aggregate parity output is written. Provider-restricted inputs stay external.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import time

from verifyrank import Dataset, DecisionWeight, Reference, evaluate

SCENARIO = "qaccepted_r250_h3_l24"
MODE = "external_2023_to_2024"
PAIRS = [("beta_rate", "uniform_random"), ("logistic", "beta_rate"),
         ("hist_gradient_boosting", "beta_rate")]


def selected(row):
    return row["scenario"] == SCENARIO and row["evaluation_mode"] == MODE and row["campaign"] == "2024"


def check(predictions, weights, expected, output):
    started = time.perf_counter()
    refs, observations = {}, {}
    with Path(predictions).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not selected(row):
                continue
            key = (row["decision_at"], row["source_id"])
            if key in observations:
                raise ValueError("duplicate source-decision prediction")
            scene, raw_label = row["outcome_scene"], row["outcome_label"]
            value = None if raw_label == "" else float(raw_label)
            if value is not None and value not in (0, 1):
                raise ValueError("nonbinary source label")
            if scene:
                ref_id = "reference:" + json.dumps([row["campaign"], row["source_id"], scene], separators=(",", ":"))
                state = "ambiguous" if value is None else "positive" if value == 1 else "negative"
            else:
                if value is not None:
                    raise ValueError("known value without actual source-scene reference")
                ref_id = "no_scene_slot:" + json.dumps([row["campaign"], row["source_id"], row["decision_at"]], separators=(",", ":"))
                state = "no_followup"
            ref = Reference(ref_id, state, value, state == "ambiguous", 1., None)
            if ref_id in refs and refs[ref_id] != ref:
                raise ValueError("shared reference evidence disagrees across decisions")
            refs[ref_id] = ref
            observations[key] = (ref_id, value)
    policies = {policy for pair in PAIRS for policy in pair}
    rows, keys, candidate_counts = [], set(), Counter(date for date, _ in observations)
    label_mismatches = candidate_mismatches = 0
    with Path(weights).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not selected(row) or row["budget_kind"] != "fraction" or float(row["budget_value"]) != .25 or row["model"] not in policies:
                continue
            key = (row["decision_at"], row["source_id"])
            if key not in observations:
                raise ValueError("weight row missing from primary inventory")
            triplet = (row["decision_at"], row["model"], row["source_id"])
            if triplet in keys:
                raise ValueError("duplicate source selection weight")
            keys.add(triplet)
            ref_id, label = observations[key]
            w_label = None if row["outcome_label"] == "" else float(row["outcome_label"])
            label_mismatches += int(w_label != label)
            candidate_mismatches += int(int(row["candidate_count"]) != candidate_counts[row["decision_at"]])
            rows.append(DecisionWeight(row["decision_at"], row["model"], ref_id,
                                       float(row["selection_probability"]), float(row["effective_budget"])))
    if label_mismatches or candidate_mismatches:
        raise ValueError("prediction/weight input evidence or inventory mismatch")
    if len(rows) != len(observations) * len(policies):
        raise ValueError("incomplete policy inventory")
    result = evaluate(Dataset(tuple(rows), tuple(refs.values())), comparisons=PAIRS)
    with Path(expected).open(encoding="utf-8", newline="") as handle:
        old = {row["pair"]: row for row in csv.DictReader(handle)
               if row["budget_kind"] == "fraction" and float(row["budget_value"]) == .25}
    checks = []
    for current in result["macro_comparison"]:
        pair = current["policy_a"] + "_vs_" + current["policy_b"]
        prior = old[pair]
        errors = [abs(current[field] - float(prior["joint_" + field])) for field in ("lower", "upper", "width")]
        floor_error = abs(current["irreducible_no_followup_width"] - float(prior["joint_width_no_future_scene"]))
        inventory_difference = len(observations) - int(prior["source_decision_rows"])
        date_difference = current["decision_count"] - int(prior["decision_days"])
        checks.append({"pair": pair, "source_decision_rows": len(observations),
                       "paired_weight_rows": 2 * len(observations), "decision_count": current["decision_count"],
                       "unique_reference_or_score_slots": len(refs),
                       "inventory_row_difference": inventory_difference, "decision_count_difference": date_difference,
                       "label_input_mismatches": label_mismatches, "candidate_count_input_mismatches": candidate_mismatches,
                       "new_lower": current["lower"], "old_lower": float(prior["joint_lower"]),
                       "new_upper": current["upper"], "old_upper": float(prior["joint_upper"]),
                       "new_width": current["width"], "old_width": float(prior["joint_width"]),
                       "max_interval_absolute_difference": max(errors), "no_followup_width_absolute_difference": floor_error,
                       "passed_1e_10": max(errors + [floor_error]) <= 1e-10 and not inventory_difference and not date_difference})
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "comparison_parity.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(checks[0])); writer.writeheader(); writer.writerows(checks)
    summary = {"all_passed": all(row["passed_1e_10"] for row in checks), "source_decision_rows": len(observations),
               "generic_weight_rows": len(rows), "policies": len(policies), "references": len(refs),
               "reference_states": dict(Counter(ref.state for ref in refs.values())),
               "comparisons": checks, "wall_seconds": time.perf_counter() - started,
               "inputs": [{"name": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                          for path in (predictions, weights, expected)],
               "scope": "Local aggregate adapter parity only; no methane input rows are exported into the software package.",
               "conditional_note": "No parity claim for conditional scores: verifyrank uses frozen verified selection mass; the earlier methane evaluator reranks known candidates."}
    (destination / "parity_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("all_passed", "source_decision_rows", "generic_weight_rows", "references", "wall_seconds")}))
    if not summary["all_passed"]:
        raise ValueError("generic adapter numerical parity failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("predictions", "weights", "expected", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    check(args.predictions, args.weights, args.expected, args.output)
