"""Run installed-package tests and synthetic CLI; write local validation only."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "validation"
    temp = destination / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(temp)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ.pop("PYTHONPATH", None)
    import verifyrank
    location = Path(verifyrank.__file__).resolve()
    if ROOT / "src" in location.parents:
        raise RuntimeError("installed-package check must not import source tree")
    wheel = ROOT / "dist/verifyrank-0.2.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for source in (ROOT / "src/verifyrank").glob("*.py"):
            if source.read_bytes() != archive.read("verifyrank/" + source.name):
                raise RuntimeError(f"wheel differs from current source: {source.name}")
        if any(name.endswith((".csv", ".json")) for name in names):
            raise RuntimeError("wheel unexpectedly contains observations or reports")
    started = time.perf_counter()
    tests = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
                           cwd=ROOT, capture_output=True, text=True)
    (destination / "installed_tests.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    test_seconds = time.perf_counter() - started
    if tests.returncode:
        raise RuntimeError("installed-package tests failed; see validation/installed_tests.log")
    paths = [ROOT / "examples/synthetic/decisions.csv", ROOT / "examples/synthetic/references.csv"]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    demo_output = destination / "synthetic_cli"
    started = time.perf_counter()
    command = [sys.executable, "-I", "-m", "verifyrank", "run", "--decisions", str(paths[0]),
               "--references", str(paths[1]), "--output", str(demo_output), "--cost-budget", "2",
               "--strategy", "expected_width_per_cost", "--overwrite"]
    cli = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (destination / "installed_cli.log").write_text(cli.stdout + cli.stderr, encoding="utf-8")
    cli_seconds = time.perf_counter() - started
    if cli.returncode:
        raise RuntimeError("installed CLI failed")
    after = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    if before != after:
        raise RuntimeError("input content changed")
    report = json.loads((demo_output / "report.json").read_text())
    json_cli = subprocess.run([sys.executable, "-I", "-m", "verifyrank", "run", "--input",
                               str(ROOT / "examples/synthetic/input.json"), "--output", str(destination / "synthetic_json_cli"),
                               "--cost-budget", "2", "--strategy", "expected_width_per_cost", "--overwrite"],
                              cwd=ROOT, capture_output=True, text=True)
    (destination / "installed_json_cli.log").write_text(json_cli.stdout + json_cli.stderr, encoding="utf-8")
    if json_cli.returncode:
        raise RuntimeError("JSON CLI failed")
    json_report = json.loads((destination / "synthetic_json_cli/report.json").read_text())
    for key in ("daily_policy", "macro_policy", "daily_comparison", "macro_comparison", "priority", "plans"):
        if report[key] != json_report[key]:
            raise RuntimeError(f"CSV and JSON CLI disagree: {key}")
    pair = report["macro_comparison"][0]
    for key, expected in (("lower", -1/24), ("upper", 5/24), ("width", .25), ("irreducible_no_followup_width", 1/6)):
        if abs(pair[key] - expected) > 1e-12:
            raise RuntimeError(f"synthetic CLI arithmetic mismatch: {key}")
    console = Path(sys.executable).parent / ("verifyrank.exe" if os.name == "nt" else "verifyrank")
    console_result = subprocess.run([str(console), "--version"], capture_output=True, text=True)
    if console_result.returncode or "0.2.0" not in console_result.stdout:
        raise RuntimeError("installed console entry point failed")
    manifest = {"status": "passed", "python": sys.version, "executable": str(Path(sys.executable).resolve()),
                "import_location": str(location), "installed_distributions": sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions()),
                "tests_exit_code": tests.returncode, "tests_wall_seconds": test_seconds,
                "synthetic_cli_exit_code": cli.returncode, "synthetic_cli_wall_seconds": cli_seconds,
                "json_cli_exit_code": json_cli.returncode, "csv_json_outputs_match": True,
                "console_entry_point": console_result.stdout.strip(), "input_content_preserved": before == after,
                "synthetic_interval": pair, "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "wheel_matches_source": True, "wheel_has_no_data_tables": True,
                "boundaries": "Computational package validation; no external user or operational field validation."}
    (destination / "release_validation.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("status", "installed_distributions", "tests_wall_seconds", "synthetic_cli_wall_seconds", "console_entry_point", "input_content_preserved")}))


if __name__ == "__main__":
    main()
