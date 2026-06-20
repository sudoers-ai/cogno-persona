"""
Stub-mode smoke for the routing bench — guards the harness plumbing in CI without
Ollama (mirrors cogno-core's cognobench smoke). The deterministic keyword embedder
must route every curated case correctly.
"""

from cognobench.routing_cases import CASES, CATALOG
from cognobench.runner import format_report, main, run_bench
from cognobench.stub_embedder import StubEmbedder


async def test_stub_bench_is_perfect():
    report = await run_bench(StubEmbedder())
    assert report.total == len(CASES)
    assert report.hits == report.total
    assert report.accuracy == 100.0
    assert all(r.hit for r in report.results)


async def test_catalog_well_formed():
    ids = {p.persona_id for p in CATALOG}
    # every case's expected persona exists in the catalog
    assert {c.expected for c in CASES} <= ids


async def test_format_report_renders_summary():
    report = await run_bench(StubEmbedder())
    out = format_report(report)
    assert "routing accuracy: 12/12 = 100.0%" in out


def test_main_stub_passes_gate():
    assert main(["--stub", "--min-score", "100"]) == 0


def test_main_stub_gate_fails_when_bar_impossible():
    # 100% accuracy < 101 bar → non-zero exit (exercises the CI-gate branch)
    assert main(["--stub", "--min-score", "101"]) == 1


def test_main_stub_limit():
    assert main(["--stub", "--limit", "3", "--min-score", "100"]) == 0
