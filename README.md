# VerifyRank 0.2.0

VerifyRank evaluates **precomputed, frozen policy selection weights** against incomplete binary reference evidence. It is a small Python package with no third-party runtime dependencies. It neither trains a ranking model nor changes a supplied score or recommendation.

Version 0.2.0 is the initial public software release. The project owner will perform Zenodo archiving; no DOI has been assigned. No operational deployment or external user study is asserted.

## Author and credits

The sole software author and copyright holder is **junjiezhang**. AI use and author responsibility are documented in [AI_USE_DISCLOSURE.md](AI_USE_DISCLOSURE.md). AI tools are not authors. No email address or institutional affiliation is inferred here. Third-party software and observation data retain their original attribution and licence terms.

## Quick start

Python 3.10 or later is required. Install the local source tree with `python -m pip install .`, or install the provided wheel without network access:

```sh
python -m pip install --no-index --no-deps dist/verifyrank-0.2.0-py3-none-any.whl
python -m verifyrank run --decisions examples/synthetic/decisions.csv --references examples/synthetic/references.csv --output demo_output --cost-budget 2
```

The installed console command `verifyrank run` is equivalent to `python -m verifyrank run`. `--input input.json` can replace the two CSV arguments. Report files are never overwritten unless `--overwrite` is explicit; input paths remain protected even then.

The bundled example is **synthetic**. Three decisions compare two policies over a shared ambiguous observation and separate no-follow-up slots. Its joint difference interval is approximately `[-0.04166667, 0.20833333]`, width `0.25`. No-follow-up alone contributes an irreducible width of `1/6`. These values illustrate the arithmetic and are not methane findings.

## Python API

```python
from verifyrank import load_csv, evaluate, write_report

data = load_csv("examples/synthetic/decisions.csv",
                "examples/synthetic/references.csv")
report = evaluate(data, tolerance=0.02,
                  comparisons=[("policy_a", "policy_b")], cost_budget=2)
print(report["macro_comparison"][0])
write_report(report, "demo_output")
```

Other public entry points are `load_json`, `validate`, `prioritize`, `Dataset`, `DecisionWeight`, `Reference`, and `ValidationError`. Cost-aware scheduling, interval classification and bounded returned-label-error sensitivity are available as:

```python
from verifyrank.planning import (
    plan_references, classify_interval, robust_completion_interval,
)
```

See [the worked tutorial](docs/tutorial.md) and [input/output contract](docs/schema.md).

## What the package reports

* Frozen-list conditional precision: positive verified selection mass divided by each policy's own verified selection mass. A zero denominator is undefined, never zero. There is no reranking of the verified subset.
* Daily and equal-decision macro paired binary completion intervals. Reused reference IDs share one outcome across decisions; their coefficients are aggregated before calculating the macro interval.
* Width attributable to ambiguous observations and to irreducible no-follow-up slots. A no-follow-up slot is a hypothetical score slot, not an observation that the planner can recover.
* Label-free priority by absolute aggregate coefficient. Optional cost-aware greedy schedules use supplied costs and hypothetical recovery probabilities, with no claim of knapsack optimality.
* CSV tables, an exact JSON report and a static HTML summary. JSON uses `null` and CSV an empty cell for undefined values; the HTML displays `NA`.

Intervals are **reference-completion ranges, not confidence intervals**. They take known labels as supplied. An interval containing zero alone does not establish equivalence. Practical equivalence is classified only when the entire interval lies within the declared `[-tolerance,+tolerance]` band.

## Contract and scope

Every decision must have the same candidate reference inventory and positive budget across policies, including explicit zero-weight rows. Weights are finite values in `[0,1]` and must sum to the budget. All policies must occur on every decision. Missing policies, duplicate rows, inconsistent references, nonbinary resolved values and extra input columns are rejected rather than silently repaired.

Reference IDs identify **outcomes**, not merely sources or subjects. Repeated views of the same archived source鈥搒cene outcome may share an ID. Different observations of one source must use different IDs. No-follow-up IDs must be decision-specific and `resolvable=false`.

The package cannot verify temporal validity, observation qualification, physical measurement accuracy, the construction of a model's predictions, or field acquisition costs. Those belong to a domain adapter and its audit. Any information availability, budget or endpoint change requires a new declared input, not silent modification inside evaluation.

## Tests and local validation

```sh
python -m unittest discover -s tests -v
```

Tests include exhaustive binary-completion enumeration, cross-decision reference cancellation, budget and schema rejection, label-free planning, zero verified denominators, interval classification, input preservation and CLI execution. All are computational fixtures, not independent environmental validation.

`scripts/check_methane_parity.py` is an optional adapter check against separately held, authorized project files. It imports the archive's previously frozen selection weights, checks inventories and labels, and compares three joint macro intervals with existing results. It does not export methane records. Local validation reports are excluded from the source distribution. Third-party raw or derived observations are **not included** in this software release or licensed by its MIT licence.

Proposed future usability work could test adapter construction and interpretation with independent users; no such study has been performed here.

## Maintenance, CI and container configuration

The [proposed maintenance policy](docs/maintenance.md) states schema compatibility, required regression checks and safe bug reporting. Changes are recorded in [CHANGELOG.md](CHANGELOG.md). No support service or established external adopter group is claimed.

`.github/workflows/tests.yml` defines Python 3.12 source tests, clean wheel installation and synthetic CSV/JSON CLI execution. The [published release's Linux workflow](https://github.com/williamjay1/verifyrank/actions/runs/37425443624) completed successfully. Docker execution remains untested.

The Dockerfile installs the included wheel with `--no-index --no-deps`. Its build context allows only the Dockerfile, wheel and synthetic inputs. Building may still require obtaining the Python base image. The mutable `python:3.12-slim` base tag does not provide a bitwise-reproducible image guarantee. Example commands, to run where Docker is available:

```sh
docker build -t verifyrank:0.2.0 .
docker run --rm -v /absolute/output/directory:/out verifyrank:0.2.0 run --input examples/synthetic/input.json --output /out --cost-budget 2
```

These commands are provided configuration examples. Docker is unavailable on the current validation host, so successful container build or execution is **not claimed**. The executed clean-environment validation described above used the wheel directly.

## Methane case and citation

The observation-derived application and reproduction scripts are available in the separate [methane case repository](https://github.com/williamjay1/verifyrank-methane-case). Those data have source-specific conditions and are not included in this MIT software archive. See CITATION.cff for the sole author and ZENODO_IMPORT.md for the owner-operated DOI step.
