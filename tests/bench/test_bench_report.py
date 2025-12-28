import json
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="bench gated by RUN_DB_TESTS")
def test_bench_smoke_generates_reports():
    # Run bench script to generate reports, then assert existence
    from scripts.bench.run_bench import main as bench_main

    bench_main()
    base = Path("bench/report")
    assert (base / "report.json").exists()
    assert (base / "report.csv").exists()
    data = json.loads((base / "report.json").read_text(encoding="utf-8"))
    assert "cases" in data


