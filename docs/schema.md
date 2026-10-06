# Input and output contract

## Two CSV tables or one JSON object

CSV headers are case-sensitive, unique and exact. Unknown columns, including hidden truth fields, are rejected. UTF-8 with or without a byte-order mark is accepted. JSON contains exactly two arrays: `decisions` and `references`. Their objects use the same field names. Duplicated JSON object keys are rejected. The structural JSON schema is `input.schema.json`; cross-row constraints are enforced by `verifyrank.validate`.

### decisions.csv

| Field | Type | Meaning |
|---|---|---|
| decision_id | nonempty string | One decision occasion; macro summaries weight distinct occasions equally |
| policy | nonempty string | Policy identifier |
| reference_id | nonempty string | Link to one binary reference outcome or decision-specific no-follow-up slot |
| weight | finite number in [0,1] | Frozen marginal probability of selecting the reference at this decision |
| budget | positive finite number | Total selection mass at this decision |

The `(decision_id,policy,reference_id)` key is unique. Budget is constant within a decision-policy block and equal across its policies. The weights sum to budget within numerical tolerance `1e-10` (absolute and relative). The software never rescales them. Candidate inventories must match across policies, so zero weights must be explicit. Every policy occurs on every decision. Fractional selection weights naturally represent randomized selection or threshold ties; the package does not infer tie membership from outcomes.

### references.csv

| Field | Type | Meaning |
|---|---|---|
| reference_id | unique nonempty string | The same ID always means exactly the same outcome |
| state | positive / negative / ambiguous / no_followup | Declared evidence state |
| value | 1 / 0 / blank | Positive requires 1, negative requires 0, unknown states require blank (JSON null) |
| resolvable | true / false | Whether an existing unknown reference may be audited; CSV also accepts 1/0 |
| cost | positive finite number | Supplied relative cost of a unique-reference audit, not an inferred field cost |
| recovery_probability | optional number in [0,1] | Hypothetical probability an audit returns usable evidence; blank/null assumes ideal success |

Known states need no further audit; their `resolvable` field does not place them in a plan. `no_followup` must be `resolvable=false` and must not be reused across decisions. Unused reference rows are allowed and explicitly counted; they do not affect evaluation. The optional recovery probability describes usability, not whether a returned label is correct. A failure stays unknown. A successful audit supplies a new input version with a qualified binary value; the original file is preserved.

No truth values may be attached to an unknown reference. The package cannot turn the absence of a real observation into an auditable historical label. A newly acquired observation would define a new endpoint or evaluation task.

## Report files

| File | Unit and contents |
|---|---|
| daily_policy.csv | Decision×policy; selection budget, known positive mass, verified mass, unknown mass, frozen conditional score, single-policy completion endpoints |
| macro_policy.csv | Policy; equal-decision endpoints, conditional mean over its defined dates, defined-date count |
| daily_comparison.csv | Decision×ordered policy pair; conditional difference, paired completion interval, evidence-state widths and interval classification |
| macro_comparison.csv | Ordered pair; equal-decision joint interval, shared-reference aggregation, daily outer endpoints, conditional mean on common-defined dates and denominator |
| priority.csv | Ordered pair×unique unknown reference; coefficient, potential width reduction, eligibility, blocked reason and supplied cost/probability |
| report.json | All tables, optional plans, metadata, software version, interpretation limits and CLI input hashes |
| report.html | Static human-readable macro summary, priority table, plans and limits |

An ordered pair always means `policy_a minus policy_b`. With no requested comparison list, every unordered policy pair is returned in lexicographic orientation. JSON numeric values are finite; undefined conditional quantities are `null`. A CSV blank denotes the same undefined quantity. No interval field is a confidence interval or a standard error.

For a daily pair, `c=(weight_a-weight_b)/budget`. Across T dates the coefficient of reference g is the sum of all its daily c divided by T. Known contribution is the sum of resolved coefficients times their supplied values. The lower endpoint adds negative unknown coefficients; the upper adds positive unknown coefficients. Width is the sum of absolute aggregated unknown coefficients. Shared outcomes can cancel across dates. No-follow-up slots cannot cancel merely by incorrectly reusing a source ID across dates.

Macro conditional differences average only dates where both frozen verified denominators are positive; the report gives that count. They are not necessarily equal to subtraction of the two policies' independently averaged conditional scores. Macro completion always uses all decisions. Their populations must not be conflated.

Planning priorities use only unresolved coefficients and reference metadata. Costs are charged once per selected reference. `residual_width_if_all_selected_resolved` is an ideal successful-recovery scenario; `hypothetical_expected_residual_width` uses supplied recovery probabilities. Neither supplies returned labels or certifies a direction. `classify_interval` must be applied to a recomputed interval after actual qualified results arrive.
