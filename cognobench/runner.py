"""
The bench harness: run the PersonaSelector over the routing cases and score it.

Drives the *real* library (``PersonaSelector`` + the curated catalog) via DI — any
``Embedder`` works. ``--stub`` uses the deterministic keyword embedder (CI smoke,
must be 100%); the default builds a real Ollama embedder from cogno-synapse.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence

from cogno_persona import Persona, PersonaSelector

from cognobench.routing_cases import BASE_ID, CASES, CATALOG, RoutingCase
from cognobench.stub_embedder import StubEmbedder


@dataclass(frozen=True)
class CaseResult:
    query: str
    lang: str
    expected: str
    predicted: str
    score: float
    hit: bool


@dataclass
class BenchReport:
    results: List[CaseResult]

    @property
    def hits(self) -> int:
        return sum(1 for r in self.results if r.hit)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def accuracy(self) -> float:
        return 100.0 * self.hits / self.total if self.total else 0.0


async def run_bench(
    embedder,
    *,
    cases: Sequence[RoutingCase] = CASES,
    personas: Sequence[Persona] = CATALOG,
    base_id: str = BASE_ID,
    threshold: float = 0.25,
) -> BenchReport:
    selector = PersonaSelector(embedder, threshold=threshold)
    results: List[CaseResult] = []
    for case in cases:
        res = await selector.select(case.query, personas, base_persona_id=base_id)
        results.append(CaseResult(
            query=case.query, lang=case.lang, expected=case.expected,
            predicted=res.persona_id, score=round(res.score, 3),
            hit=res.persona_id == case.expected,
        ))
    return BenchReport(results)


def format_report(report: BenchReport) -> str:
    lines = ["", "  ok  lang  score   expected → predicted   query", "  " + "─" * 70]
    for r in report.results:
        mark = "✅" if r.hit else "❌"
        arrow = f"{r.expected} → {r.predicted}"
        lines.append(f"  {mark}  {r.lang:<4}  {r.score:>5.2f}  {arrow:<22}  {r.query[:34]}")
    lines.append("  " + "─" * 70)
    lines.append(f"  routing accuracy: {report.hits}/{report.total} = {report.accuracy:.1f}%")
    return "\n".join(lines)


def _build_embedder(args: argparse.Namespace):
    if args.stub:
        return StubEmbedder()
    # Real mode: a local Ollama embedder via cogno-synapse, cached so each persona
    # description is embedded once across all cases.
    from cogno_synapse import OllamaEmbedder
    from cogno_synapse.cache import CachingEmbedder
    return CachingEmbedder(OllamaEmbedder(model=args.model, base_url=args.base_url))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="cogno-persona routing benchmark")
    parser.add_argument("--stub", action="store_true",
                        help="use the deterministic keyword embedder (no network)")
    parser.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    parser.add_argument("--threshold", type=float, default=0.25, help="selector match threshold")
    parser.add_argument("--min-score", type=float, default=None,
                        help="exit non-zero if accuracy is below this percentage (CI gate)")
    parser.add_argument("--model", default="nomic-embed-text", help="Ollama embedding model")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL")
    args = parser.parse_args(argv)

    cases = CASES[: args.limit] if args.limit else CASES
    embedder = _build_embedder(args)
    report = asyncio.run(run_bench(embedder, cases=cases, threshold=args.threshold))
    print(format_report(report))

    if args.min_score is not None and report.accuracy < args.min_score:
        print(f"  FAIL: accuracy {report.accuracy:.1f}% < min {args.min_score:.1f}%", file=sys.stderr)
        return 1
    return 0
