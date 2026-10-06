import dataclasses
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verifyrank import Dataset, DecisionWeight as D, Reference as R, ValidationError
from verifyrank import evaluate, load_csv, load_json, prioritize, validate, write_report

ROOT = Path(__file__).resolve().parents[1]


def tiny():
    refs = (R("p", "positive", 1, False, 1), R("u", "ambiguous", None, True, 1))
    rows = (D("d", "a", "p", 1, 1), D("d", "a", "u", 0, 1),
            D("d", "b", "p", 0, 1), D("d", "b", "u", 1, 1))
    return Dataset(rows, refs)


class ValidationTests(unittest.TestCase):
    def test_duplicate_weight_rows_rejected(self):
        data = tiny()
        with self.assertRaisesRegex(ValidationError, "duplicate"):
            validate(Dataset(data.decisions + data.decisions[:1], data.references))

    def test_duplicate_and_inconsistent_references_rejected(self):
        data = tiny()
        for ref in (data.references[0], R("p", "negative", 0, False, 1)):
            with self.assertRaisesRegex(ValidationError, "duplicate"):
                validate(Dataset(data.decisions, data.references + (ref,)))

    def test_illegal_weights_and_budget(self):
        for replacement in (float("nan"), float("inf"), -0.1, 1.1, True, "1"):
            data = tiny()
            rows = (dataclasses.replace(data.decisions[0], weight=replacement),) + data.decisions[1:]
            with self.assertRaises(ValidationError):
                validate(Dataset(rows, data.references))
        data = tiny()
        rows = tuple(dataclasses.replace(row, budget=2) for row in data.decisions)
        with self.assertRaisesRegex(ValidationError, "sum"):
            validate(Dataset(rows, data.references))

    def test_nonbinary_and_wrong_resolved_values(self):
        data = tiny()
        for value in (0.5, 0, None, True):
            with self.assertRaises(ValidationError):
                validate(Dataset(data.decisions, (dataclasses.replace(data.references[0], value=value), data.references[1])))
        with self.assertRaises(ValidationError):
            validate(Dataset(data.decisions, (data.references[0], dataclasses.replace(data.references[1], value=0))))

    def test_no_followup_cannot_resolve_or_share_across_dates(self):
        data = tiny()
        with self.assertRaisesRegex(ValidationError, "no_followup"):
            validate(Dataset(data.decisions, (data.references[0], R("u", "no_followup", None, True, 1))))
        rows = data.decisions + tuple(dataclasses.replace(row, decision_id="d2") for row in data.decisions)
        with self.assertRaisesRegex(ValidationError, "decision-specific"):
            validate(Dataset(rows, (data.references[0], R("u", "no_followup", None, False, 1))))

    def test_inventory_and_missing_policy_rejected(self):
        data = tiny()
        rows = tuple(row for row in data.decisions if not (row.policy == "b" and row.reference_id == "p"))
        with self.assertRaisesRegex(ValidationError, "inventory"):
            validate(Dataset(rows, data.references))
        rows = data.decisions + tuple(dataclasses.replace(row, decision_id="d2") for row in data.decisions if row.policy == "a")
        with self.assertRaisesRegex(ValidationError, "missing policy"):
            validate(Dataset(rows, data.references))

    def test_csv_and_json_loading_equal_and_no_hidden_truth(self):
        data = load_csv(ROOT / "examples/synthetic/decisions.csv", ROOT / "examples/synthetic/references.csv")
        obj = {"decisions": [dataclasses.asdict(x) for x in data.decisions],
               "references": [dataclasses.asdict(x) for x in data.references]}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "input.json"
            path.write_text(json.dumps(obj), encoding="utf-8")
            self.assertEqual(data, load_json(path))
            obj["references"][2]["hidden_truth"] = 1
            path.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "extra"):
                load_json(path)

    def test_duplicate_json_keys_and_csv_headers_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "input.json"
            path.write_text('{"decisions":[],"decisions":[],"references":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "duplicated"):
                load_json(path)
            csvpath = Path(td) / "decisions.csv"
            csvpath.write_text("decision_id,policy,reference_id,weight,budget,budget\n", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "duplicated"):
                load_csv(csvpath, ROOT / "examples/synthetic/references.csv")

    def test_json_preserves_declared_numeric_and_boolean_types(self):
        data = tiny()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "input.json"
            for table, field, value in [("decisions", "weight", "1"), ("references", "resolvable", "false"),
                                         ("references", "value", "1"), ("references", "cost", True)]:
                obj = {"decisions": [dataclasses.asdict(row) for row in data.decisions],
                       "references": [dataclasses.asdict(row) for row in data.references]}
                obj[table][0][field] = value
                path.write_text(json.dumps(obj), encoding="utf-8")
                with self.assertRaises(ValidationError):
                    load_json(path)


class ArithmeticTests(unittest.TestCase):
    def test_missing_does_not_become_negative_and_zero_mass_is_undefined(self):
        result = evaluate(tiny())
        b = next(row for row in result["daily_policy"] if row["policy"] == "b")
        self.assertIsNone(b["conditional_score"])
        self.assertEqual((b["completion_lower"], b["completion_upper"]), (0, 1))
        pair = result["macro_comparison"][0]
        self.assertEqual((pair["lower"], pair["upper"]), (0, 1))
        self.assertEqual(pair["interval_classification"], "undetermined")
        self.assertEqual(pair["conditional_defined_dates"], 0)

    def test_policy_specific_verified_denominators(self):
        refs = (R("p", "positive", 1, False, 1), R("n", "negative", 0, False, 1), R("u", "ambiguous", None, True, 1))
        rows = tuple(D("d", p, r, w, 1) for p, ws in [("a", [.5, .25, .25]), ("b", [.25, .25, .5])] for r, w in zip(["p", "n", "u"], ws))
        result = evaluate(Dataset(rows, refs))
        self.assertAlmostEqual(result["daily_comparison"][0]["conditional_difference"], 2/3 - .5)

    def test_shared_reference_cancels_across_dates(self):
        data = tiny()
        reverse = tuple(D("d2", row.policy, row.reference_id, 1 - row.weight, 1) for row in data.decisions)
        result = evaluate(Dataset(data.decisions + reverse, data.references))
        pair = result["macro_comparison"][0]
        self.assertEqual((pair["lower"], pair["upper"], pair["width"]), (0, 0, 0))
        self.assertEqual((pair["daily_outer_lower"], pair["daily_outer_upper"]), (-.5, .5))
        self.assertEqual(pair["interval_classification"], "practical_equivalence")

    def test_macro_bounds_match_exhaustive_unique_reference_completions(self):
        data = load_csv(ROOT / "examples/synthetic/decisions.csv", ROOT / "examples/synthetic/references.csv")
        result = evaluate(data)
        pair = result["macro_comparison"][0]
        unknown = [ref.reference_id for ref in data.references if ref.value is None]
        known = {ref.reference_id: ref.value for ref in data.references if ref.value is not None}
        outcomes = []
        for bits in itertools.product([0, 1], repeat=len(unknown)):
            labels = known | dict(zip(unknown, bits))
            signed = [(1 if row.policy == "policy_a" else -1) * row.weight * labels[row.reference_id] / row.budget / 3 for row in data.decisions]
            outcomes.append(math.fsum(signed))
        self.assertAlmostEqual(pair["lower"], min(outcomes))
        self.assertAlmostEqual(pair["upper"], max(outcomes))
        self.assertAlmostEqual(pair["width"], .25)
        self.assertAlmostEqual(pair["irreducible_no_followup_width"], 1/6)

    def test_label_free_priority_does_not_access_value(self):
        class Poison:
            reference_id = "u"
            state = "ambiguous"
            resolvable = True
            cost = 1
            recovery_probability = 1
            @property
            def value(self):
                raise AssertionError("planner accessed a hidden outcome")
        row = prioritize({"u": -.4}, [Poison()])[0]
        self.assertEqual(row["potential_width_reduction"], .4)

    def test_resolved_label_changes_do_not_change_priority(self):
        data = tiny()
        changed = Dataset(data.decisions, (R("p", "negative", 0, False, 1), data.references[1]))
        self.assertEqual(evaluate(data)["priority"], evaluate(changed)["priority"])
        self.assertNotEqual(evaluate(data)["macro_comparison"], evaluate(changed)["macro_comparison"])

    def test_evaluation_does_not_mutate_weights(self):
        data = tiny()
        before = repr(data)
        evaluate(data)
        self.assertEqual(repr(data), before)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            data.decisions[0].weight = .5

    def test_cost_plan_cannot_remove_no_followup_width(self):
        data = load_csv(ROOT / "examples/synthetic/decisions.csv", ROOT / "examples/synthetic/references.csv")
        result = evaluate(data, cost_budget=100)
        plan = result["plans"][0]
        self.assertGreaterEqual(plan["residual_width_if_all_selected_resolved"], 1/6 - 1e-12)


class ReportTests(unittest.TestCase):
    def test_all_known_priority_csv_retains_schema_header(self):
        data = tiny()
        data = Dataset(data.decisions, (data.references[0], R("u", "negative", 0, False, 1)))
        with tempfile.TemporaryDirectory() as td:
            write_report(evaluate(data), td)
            self.assertIn("reference_id", (Path(td) / "priority.csv").read_text())

    def test_html_escapes_identifiers_and_refuses_overwrite(self):
        data = tiny()
        rows = tuple(dataclasses.replace(row, policy="<script>alert(1)</script>" if row.policy == "a" else "b") for row in data.decisions)
        result = evaluate(Dataset(rows, data.references))
        with tempfile.TemporaryDirectory() as td:
            files = write_report(result, td)
            self.assertEqual(len(files), 7)
            text = (Path(td) / "report.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>", text)
            self.assertIn("&lt;script&gt;", text)
            with self.assertRaises(FileExistsError):
                write_report(result, td)

    def test_output_must_not_replace_protected_input(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            path.write_text("original input", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "input"):
                write_report(evaluate(tiny()), td, overwrite=True, protected_paths=[path])
            self.assertEqual(path.read_text(), "original input")

    def test_cli_synthetic_success_and_read_only_inputs(self):
        paths = [ROOT / "examples/synthetic/decisions.csv", ROOT / "examples/synthetic/references.csv"]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        with tempfile.TemporaryDirectory() as td:
            process = subprocess.run([sys.executable, "-m", "verifyrank", "run", "--decisions", str(paths[0]), "--references", str(paths[1]), "--output", td, "--cost-budget", "2"], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads((Path(td) / "report.json").read_text())
            self.assertEqual(result["metadata"]["decision_count"], 3)
            self.assertEqual(result["version"], "0.2.0")
            self.assertEqual(result["plans"][0]["cost_used"], 2)
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths])


if __name__ == "__main__":
    unittest.main()
