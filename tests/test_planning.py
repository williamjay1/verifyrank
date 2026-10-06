import itertools
import unittest

from verifyrank.planning import classify_interval, plan_references, robust_completion_interval


def ref(key, cost=1., p=None, state="ambiguous", resolvable=True):
    return {"reference_id": key, "state": state, "resolvable": resolvable,
            "cost": cost, "recovery_probability": p, "value": None}


class PlanningTests(unittest.TestCase):
    def test_interval_boundaries(self):
        self.assertEqual(classify_interval(-.02, .02), "practical_equivalence")
        self.assertEqual(classify_interval(.02, .03), "undetermined")
        self.assertEqual(classify_interval(-.03, -.02), "undetermined")
        self.assertEqual(classify_interval(.0201, .03), "positive")
        self.assertEqual(classify_interval(-.03, -.0201), "negative")
        with self.assertRaises(ValueError):
            classify_interval(.1, -.1)

    def test_never_reads_truth(self):
        class Metadata:
            reference_id, state, resolvable, cost = "a", "ambiguous", True, 1.
            recovery_probability = None
            @property
            def value(self):
                raise AssertionError("planner accessed truth")
        result = plan_references({"a": -.2}, [Metadata()], 1.)
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["default_ideal_success_reference_count"], 1)

    def test_unrecoverable_floor_and_failed_result(self):
        c = {"a": .1, "no": -.3}
        result = plan_references(c, [ref("a", p=.5), ref("no", state="no_followup", resolvable=False)], 9)
        self.assertAlmostEqual(result["irreducible_width"], .3)
        self.assertAlmostEqual(result["hypothetical_expected_residual_width"], .35)
        self.assertAlmostEqual(robust_completion_interval(c, {})["interval_width"], .4)
        self.assertAlmostEqual(robust_completion_interval(c, {"a": 1})["interval_width"], .3)
        with self.assertRaises(ValueError):
            plan_references({"no": .1}, [ref("no", state="no_followup")], 1)

    def test_greedy_counterexample(self):
        c = {"a": .09, "b": .12, "c": .12}
        refs = [ref("a", 2), ref("b", 3), ref("c", 3)]
        result = plan_references(c, refs, 6)
        self.assertEqual([x["reference_id"] for x in result["selected"]], ["a", "b"])
        self.assertAlmostEqual(result["residual_width_if_all_selected_resolved"], .12)
        # Exhaustive optimum is b+c: reduction .24 rather than greedy .21.
        optimum = max(sum(c[refs[i]["reference_id"]] for i in range(3) if bits[i])
                      for bits in itertools.product([0, 1], repeat=3)
                      if sum(refs[i]["cost"] for i in range(3) if bits[i]) <= 6)
        self.assertAlmostEqual(optimum, .24)

    def test_probability_strategy_and_cost_skip(self):
        c = {"a": .4, "b": .3, "c": .1}
        refs = [ref("a", 2, .1), ref("b", 2, 1), ref("c", 1, 1)]
        self.assertEqual(plan_references(c, refs, 2)["selected"][0]["reference_id"], "a")
        self.assertEqual(plan_references(c, refs, 2, "expected_width_per_cost")["selected"][0]["reference_id"], "b")
        self.assertEqual(plan_references(c, refs, 1)["selected"][0]["reference_id"], "c")

    def test_invalid_input(self):
        for bad in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                plan_references({"a": .1}, [ref("a", bad)], 1)
        with self.assertRaises(ValueError):
            plan_references({"a": .1}, [ref("a", p=1.1)], 1)
        with self.assertRaises(ValueError):
            plan_references({"a": .1}, [ref("a", state="positive")], 1)

    def test_zero_probability_not_scheduled(self):
        for strategy in ("width_per_cost", "expected_width_per_cost"):
            result = plan_references({"a": .2}, [ref("a", p=0)], 9, strategy)
            self.assertEqual(result["selected_count"], 0)
            self.assertEqual(result["cost_used"], 0)
            self.assertAlmostEqual(result["irreducible_width"], .2)
            self.assertAlmostEqual(result["structural_irreducible_width"], 0)

    def test_binary_error_enumeration(self):
        c = {"a": .3, "b": -.2, "c": .1, "d": -.4}
        observed = {"a": 1, "b": 0, "c": 0}
        for error_budget in range(4):
            outcomes = []
            for binary in itertools.product([0, 1], repeat=4):
                values = dict(zip(c, binary))
                if sum(values[k] != v for k, v in observed.items()) <= error_budget:
                    outcomes.append(.04 + sum(c[k] * v for k, v in values.items()))
            result = robust_completion_interval(c, observed, error_budget, .04)
            self.assertAlmostEqual(result["lower"], min(outcomes))
            self.assertAlmostEqual(result["upper"], max(outcomes))

    def test_empty_all_known_and_zero_cancelled(self):
        self.assertEqual(plan_references({}, [], 0)["initial_width"], 0)
        self.assertEqual(plan_references({"cancelled": 0}, [ref("cancelled")], 5)["selected_count"], 0)
        self.assertAlmostEqual(robust_completion_interval({"a": .2}, {"a": 1})["interval_width"], 0)
        with self.assertRaises(ValueError):
            robust_completion_interval({"a": .1}, {"a": None})


if __name__ == "__main__":
    unittest.main()
