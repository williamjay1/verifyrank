# Worked tutorial: two frozen policies and incomplete observations

The supplied tables are synthetic computational examples. They do not describe methane sources, acquired scenes or human participants.

## 1. Prepare the evidence separately from policy selection

`examples/synthetic/decisions.csv` has 24 weights: three decision occasions, two policies and four candidate reference slots per occasion. Each policy's weights sum to two. A positive and a negative observation are shared, as is an ambiguous observation. The three missing-follow-up slots have distinct IDs because no actual observation establishes cross-decision identity.

The ambiguous reference has audit cost 2 and hypothetical usable-recovery probability 0.5. These illustrative assumptions are supplied by the example, not estimated by VerifyRank. No hidden truth appears in either input table.

```python
from verifyrank import load_csv, evaluate

data = load_csv("examples/synthetic/decisions.csv",
                "examples/synthetic/references.csv")
result = evaluate(data, comparisons=[("policy_a", "policy_b")],
                  tolerance=0.02, cost_budget=2,
                  strategy="expected_width_per_cost")
comparison = result["macro_comparison"][0]
print(comparison["lower"], comparison["upper"], comparison["width"])
```

The macro interval is `[-1/24, 5/24]`, width `1/4`. It is undetermined at tolerance 0.02, even though it includes zero. The no-follow-up width is `1/6`; auditing the sole ambiguous reference cannot eliminate this component. The reported known-reference conditional contrast is `1/6`, which does not replace the full-inventory completion interval.

## 2. Inspect a label-free plan

```python
plan = result["plans"][0]
print(plan["selected"])
print(plan["residual_width_if_all_selected_resolved"])
print(plan["hypothetical_expected_residual_width"])
```

The selected reference is `shared_ambiguous`, charged once at cost 2. If its label is successfully returned, width becomes `1/6`. Under the supplied 0.5 recovery probability, hypothetical expected width is `5/24`. The eventual location of the interval depends on the returned label; the planner does not inspect it in advance. A failed audit leaves the input state unknown.

Costs can differ across references. `width_per_cost` orders by absolute coefficient/cost; `expected_width_per_cost` additionally multiplies by supplied recovery probability. Both are indivisible, budget-feasible greedy heuristics, not optimal knapsack solutions. Cost units need to be defined by the application. They are not automatically money, elapsed time or aircraft hours.

## 3. Apply the stopping rule to an actual interval

```python
from verifyrank.planning import classify_interval

assert classify_interval(-0.01, 0.015, tolerance=0.02) == "practical_equivalence"
assert classify_interval(-0.20, 0.01, tolerance=0.02) == "undetermined"
assert classify_interval(0.021, 0.12, tolerance=0.02) == "positive"
```

Practical equivalence requires the entire interval inside the tolerance band. A bound touching +0.02 does not certify a positive difference beyond +0.02. The tolerance is an operator-defined comparison margin; it is not learned from masked outcomes.

## 4. Allow a declared number of returned labels to be wrong

```python
from verifyrank.planning import robust_completion_interval

audit = robust_completion_interval(
    {"reference_a": 0.2, "reference_b": -0.1},
    observed_labels={"reference_a": 1},
    max_wrong=1,
)
print(audit["lower"], audit["upper"])
```

This separate sensitivity utility permits at most the specified number of returned unique-reference labels to flip. An absent result remains unknown. The assumption is supplied, not calibrated from metadata. Original known-label errors are covered only if their coefficients and observed values are explicitly included. This function reads returned labels to update evaluation; it does not choose audit order or have access to hidden truth.

## 5. Run the CLI and inspect its output

```sh
verifyrank run --decisions examples/synthetic/decisions.csv --references examples/synthetic/references.csv --output demo_output --tolerance 0.02 --cost-budget 2 --strategy expected_width_per_cost
```

Open `demo_output/report.html` for a static summary. Exact values and all daily records are in `report.json` and CSV tables. `report.json` also identifies input SHA256 values. To rerun, choose another directory or explicitly add `--overwrite`; source inputs are never overwritten.

To use JSON instead, provide `{ "decisions": [...], "references": [...] }` records with the same schema and run `verifyrank run --input input.json --output demo_output_json`.

## 6. Build a domain adapter

An adapter must establish candidate identity, reference qualification, and the information available to the upstream policy before exporting weights. It must map one actual reference outcome to one ID and preserve unknown evidence. It must document whether a nondetection is a catalogue criterion, physical absence, or another endpoint. VerifyRank does not infer these scientific meanings.

The optional `scripts/check_methane_parity.py` reads pre-existing methane selection weights and compares generic joint bounds with the project-specific evaluator. Its data are not bundled. The generic frozen conditional score intentionally differs from the earlier evaluator's reranking of known candidates, so no conditional-score parity is claimed. This distinction is part of the adapter contract, not an implementation error.
