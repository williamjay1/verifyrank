"""CSV, JSON and self-contained HTML reports without client-side code."""
from __future__ import annotations
import csv
import html
import json
from pathlib import Path

TABLES = ("daily_policy", "macro_policy", "daily_comparison", "macro_comparison", "priority")
EMPTY_FIELDS = {
    "daily_policy": ["decision_id", "policy", "candidate_count", "budget", "verified_selected_mass", "known_positive_selected_mass", "unknown_selected_mass", "conditional_score", "conditional_defined", "completion_lower", "completion_upper"],
    "macro_policy": ["policy", "decision_count", "conditional_defined_dates", "conditional_score", "completion_lower", "completion_upper"],
    "daily_comparison": ["decision_id", "policy_a", "policy_b", "conditional_difference", "known_contribution", "lower", "upper", "width", "ambiguous_width", "irreducible_no_followup_width", "interval_classification"],
    "macro_comparison": ["policy_a", "policy_b", "decision_count", "conditional_defined_dates", "conditional_difference", "known_contribution", "lower", "upper", "width", "ambiguous_width", "irreducible_no_followup_width", "interval_classification", "tolerance", "daily_outer_lower", "daily_outer_upper"],
    "priority": ["policy_a", "policy_b", "reference_id", "coefficient", "potential_width_reduction", "state", "eligible", "blocked_reason", "cost", "recovery_probability"],
}


def _cell(value):
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def _table(rows):
    if not rows:
        return "<p>No rows.</p>"
    fields = list(rows[0])
    head = "".join(f"<th>{html.escape(field)}</th>" for field in fields)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(_cell(row.get(field)))}</td>" for field in fields) + "</tr>" for row in rows)
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def write_report(result: dict, output_dir: str | Path, *, overwrite: bool = False,
                 protected_paths=()) -> list[Path]:
    """Write reports; reject existing files unless explicitly allowed.

    protected_paths are resolved before writes so a CLI input cannot be replaced.
    Input Dataset objects are never modified.
    """
    output = Path(output_dir).resolve()
    paths = [output / f"{name}.csv" for name in TABLES] + [output / "report.json", output / "report.html"]
    protected = {Path(path).resolve() for path in protected_paths}
    for path in paths:
        if path.resolve() in protected:
            raise ValueError(f"output would overwrite an input: {path}")
        if path.exists() and not overwrite:
            raise FileExistsError(f"output exists; use --overwrite deliberately: {path}")
    output.mkdir(parents=True, exist_ok=True)
    for name in TABLES:
        rows = result[name]
        with (output / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else EMPTY_FIELDS[name])
            writer.writeheader()
            writer.writerows(rows)
    (output / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    parts = ["<!doctype html><html lang='en'><meta charset='utf-8'><title>VerifyRank report</title>",
             "<style>body{font:15px system-ui;max-width:1200px;margin:2em auto;padding:0 1em;color:#203040}table{border-collapse:collapse;font-size:13px}th,td{padding:.5em;border:1px solid #ccd5dc;text-align:left}.scroll{overflow-x:auto}code{background:#eef2f4}h1,h2{color:#12394b}</style>",
             "<h1>VerifyRank 0.2.0</h1><p>Prepared for public release. Precomputed weights remain frozen.</p>",
             "<p><strong>Intervals are binary reference-completion ranges, not confidence intervals.</strong> "
             "Conditional scores use each policy's verified selection mass. A range containing zero alone does not certify practical equivalence.</p>"]
    for name in ("macro_comparison", "macro_policy", "priority"):
        parts.append(f"<h2>{html.escape(name.replace('_', ' ').title())}</h2>{_table(result[name])}")
    if result["plans"]:
        parts.append("<h2>Reference plans</h2><pre>" + html.escape(json.dumps(result["plans"], indent=2)) + "</pre>")
    parts.append("<h2>Interpretation limits</h2><ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in result["metadata"]["limitations"]) + "</ul>")
    parts.append("<p>All daily rows and exact numeric values are supplied in the adjacent CSV and JSON files. NA means undefined, not zero.</p></html>")
    (output / "report.html").write_text("\n".join(parts), encoding="utf-8")
    return paths
