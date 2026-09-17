"""Partition core and real morphology tests and write an optional JSON result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

parser = argparse.ArgumentParser()
parser.add_argument("--suite", choices=["core", "morphology", "all"], default="all")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
if args.suite in {"morphology", "all"}:
    os.environ["TLE_REQUIRE_ZEYREK"] = "1"
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for test in sorted((ROOT / "tests").glob("test_*.py")):
    is_integration = test.name.endswith("_integration.py")
    if args.suite == "core" and is_integration:
        continue
    if args.suite == "morphology" and not is_integration:
        continue
    suite.addTests(loader.discover(str(ROOT / "tests"), pattern=test.name))
result = unittest.TextTestRunner(verbosity=2).run(suite)
dependencies = {}
for name in ["zeyrek", "nltk"]:
    try:
        dependencies[name] = version(name)
    except PackageNotFoundError:
        dependencies[name] = None
report = {
    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    "suite": args.suite,
    "python": platform.python_version(),
    "platform": platform.platform(),
    "dependencies": dependencies,
    "tests": result.testsRun,
    "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
    "failed": len(result.failures),
    "errors": len(result.errors),
    "skipped": len(result.skipped),
    "successful": result.wasSuccessful() and not result.skipped,
}
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report["successful"] else 1)
