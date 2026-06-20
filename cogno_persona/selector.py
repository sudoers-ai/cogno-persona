"""
cogno_persona.selector — embedding-based persona matching (pure algorithm).

Picks the best specialist persona for a user query by cosine similarity against
each persona's description. Distilled from the parent ``cogno.ego.persona_selector``
with the infra removed: **no CoreDB, no tenant TTL cache, no business hardcodes**.
The host loads the candidate personas (e.g. from a ``PersonaStore``) and injects an
``Embedder``; caching is a host concern (wrap the embedder, or pass precomputed
``candidate_vectors``).

In the real pipeline the ``query`` is ``noumeno.rewritten`` — **canonical English**
(NOUMENO always rewrites), so routing is monolingual; the cross-lingual caveat on
the threshold only applies if a host feeds raw multilingual text.

Scoring (all weights configurable):
  * ``intent_class`` in ``non_routing_intents`` (default ``{"SOCIAL"}``) → straight to
    base, no embedding (a greeting has no domain; the parent skipped it off NER too).
  * ``restrict_to`` competes only among the personas an *identity* is allowed (N:N).
  * ``base_penalty`` nudges the base persona down so a clear specialist can win.
  * an inertia ``inertia_boost`` favours the currently active persona, decayed by
    ``correction_decay`` (e.g. number of prior SUPEREGO rejections).
  * a match must clear ``threshold`` (default 0.25).
  * an optional injected ``reranker`` reorders the above-threshold shortlist — the
    seam for tenants with many similar personas (default off; core stays zero-dep).
"""

from __future__ import annotations

import math
from typing import (
    TYPE_CHECKING,
    Collection,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

from cogno_persona.types import Persona, SelectionResult

if TYPE_CHECKING:  # runtime-light: the Embedder protocol travels type-only
    from cogno_synapse import Embedder

# Short queries carry too little signal to route to a specialist ("Oi", "Ok").
_MIN_QUERY_LEN = 5


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity; ``0.0`` for a zero vector or mismatched/empty input."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


@runtime_checkable
class Reranker(Protocol):
    """A relevance re-scorer over a shortlist (a cross-encoder, injected by the host).

    Given the query and one document per candidate (``"<id>: <description>"``),
    return a relevance score per document, highest = most relevant. Optional: a
    plain cosine ``PersonaSelector`` never needs one. The concrete cross-encoder
    is a host concern (mirror cogno-engram's reranker shape).
    """

    async def rerank(self, query: str, documents: Sequence[str]) -> Sequence[float]: ...


class PersonaSelector:
    """Score personas against a query and return the best (or the base fallback)."""

    def __init__(
        self,
        embedder: "Embedder",
        *,
        threshold: float = 0.25,
        base_penalty: float = 0.10,
        inertia_boost: float = 0.05,
        non_routing_intents: Collection[str] = frozenset({"SOCIAL"}),
        rerank_top_k: int = 5,
    ) -> None:
        self._embedder = embedder
        self.threshold = threshold
        self.base_penalty = base_penalty
        self.inertia_boost = inertia_boost
        self.non_routing_intents = frozenset(non_routing_intents)
        self.rerank_top_k = rerank_top_k

    async def select(
        self,
        query: str,
        candidates: Sequence[Persona],
        *,
        base_persona_id: Optional[str] = None,
        current_persona_id: Optional[str] = None,
        apply_base_penalty: bool = True,
        correction_decay: int = 0,
        threshold: Optional[float] = None,
        candidate_vectors: Optional[Dict[str, List[float]]] = None,
        intent_class: Optional[str] = None,
        restrict_to: Optional[Collection[str]] = None,
        reranker: Optional[Reranker] = None,
    ) -> SelectionResult:
        """Return the closest persona, or the base when nothing clears the threshold.

        ``intent_class`` short-circuits non-routing intents (e.g. ``SOCIAL``) to the
        base with no embedding. ``restrict_to`` limits competition to an identity's
        allowed personas. ``candidate_vectors`` (id → embedding) lets a host inject
        precomputed embeddings to skip re-embedding. ``reranker`` (if injected)
        reorders the above-threshold shortlist.
        """
        fallback = base_persona_id or (candidates[0].persona_id if candidates else "")

        # (2) Non-routing intent (SOCIAL/greeting) → base, no embedding cost.
        if intent_class and intent_class in self.non_routing_intents:
            return SelectionResult(persona_id=fallback, matched=False)

        # (3) N:N identity filter — compete only among allowed personas.
        if restrict_to is not None:
            allowed = set(restrict_to)
            candidates = [p for p in candidates if p.persona_id in allowed]

        if not candidates or not query or len(query.strip()) < _MIN_QUERY_LEN:
            return SelectionResult(persona_id=fallback, matched=False)

        query_vec = await self._embedder.embed(query)
        if not query_vec:
            return SelectionResult(persona_id=fallback, matched=False)

        by_id: Dict[str, Persona] = {p.persona_id: p for p in candidates}
        scores: List[tuple[str, float]] = []
        for persona in candidates:
            pid = persona.persona_id
            vec = (candidate_vectors or {}).get(pid)
            if vec is None:
                vec = await self._embedder.embed(f"{pid}: {persona.description}")
            score = cosine(query_vec, vec)
            if pid == base_persona_id and apply_base_penalty:
                score -= self.base_penalty
            if current_persona_id and pid == current_persona_id:
                score += self.inertia_boost - (correction_decay * self.inertia_boost)
            scores.append((pid, score))

        scores.sort(key=lambda s: s[1], reverse=True)
        eff_threshold = threshold if threshold is not None else self.threshold
        top_id, top_score = scores[0]
        if top_score < eff_threshold:
            return SelectionResult(persona_id=fallback, score=top_score, matched=False, scores=scores)

        if reranker is None:
            return SelectionResult(persona_id=top_id, score=top_score, matched=True, scores=scores)

        # Optional rerank stage: re-score the above-threshold shortlist (top-k).
        shortlist = [(pid, s) for pid, s in scores if s >= eff_threshold][: self.rerank_top_k]
        docs = [f"{pid}: {by_id[pid].description}" for pid, _ in shortlist]
        rerank_scores = await reranker.rerank(query, docs)
        reranked = sorted(
            ((shortlist[i][0], float(rerank_scores[i])) for i in range(len(shortlist))),
            key=lambda s: s[1],
            reverse=True,
        )
        best_id, best_score = reranked[0]
        return SelectionResult(persona_id=best_id, score=best_score, matched=True, scores=reranked)
