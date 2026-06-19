"""
cogno_persona.selector — embedding-based persona matching (pure algorithm).

Picks the best specialist persona for a user query by cosine similarity against
each persona's description. Distilled from the parent ``cogno.ego.persona_selector``
with the infra removed: **no CoreDB, no tenant TTL cache, no business hardcodes**.
The host loads the candidate personas (e.g. from a ``PersonaStore``) and injects an
``Embedder``; caching is a host concern (wrap the embedder, or pass precomputed
``candidate_vectors``).

Scoring (all weights configurable):
  * ``base_penalty`` nudges the base persona down so a clear specialist can win
    (only applied when ``apply_base_penalty`` — the host derives that from intent;
    e.g. skip it for SOCIAL/greeting queries so the base persona wins naturally).
  * an inertia ``inertia_boost`` favours the currently active persona, decayed by
    ``correction_decay`` (e.g. number of prior SUPEREGO rejections).
  * a match must clear ``threshold`` (default 0.25 — cross-lingual embeddings have
    a narrower cosine range than the monolingual ~0.45).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

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


class PersonaSelector:
    """Score personas against a query and return the best (or the base fallback)."""

    def __init__(
        self,
        embedder: "Embedder",
        *,
        threshold: float = 0.25,
        base_penalty: float = 0.10,
        inertia_boost: float = 0.05,
    ) -> None:
        self._embedder = embedder
        self.threshold = threshold
        self.base_penalty = base_penalty
        self.inertia_boost = inertia_boost

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
    ) -> SelectionResult:
        """Return the closest persona, or the base when nothing clears the threshold.

        ``candidate_vectors`` (id → embedding) lets a host inject precomputed/cached
        description embeddings to skip re-embedding. The base persona is the
        fast-path winner for empty/short queries (no embedding cost).
        """
        fallback = base_persona_id or (candidates[0].persona_id if candidates else "")

        if not candidates or not query or len(query.strip()) < _MIN_QUERY_LEN:
            return SelectionResult(persona_id=fallback, matched=False)

        query_vec = await self._embedder.embed(query)
        if not query_vec:
            return SelectionResult(persona_id=fallback, matched=False)

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
        if top_score >= eff_threshold:
            return SelectionResult(persona_id=top_id, score=top_score, matched=True, scores=scores)
        return SelectionResult(persona_id=fallback, score=top_score, matched=False, scores=scores)
