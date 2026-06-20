"""
A deterministic, network-free embedder for ``--stub`` runs.

One-hot over keyword buckets (EN + PT terms per domain). A query and a persona
description sharing a domain land on the same axis (cosine 1.0); a generic query
hits no bucket (zero vector → 0.0 similarity → base fallback). This makes the
stub bench fully deterministic so it can guard the plumbing at 100% in CI without
Ollama, mirroring cogno-core's stub-mode smoke.
"""

from __future__ import annotations

# domain axis → keywords (lowercased substring match), EN + PT
_BUCKETS: list[tuple[str, ...]] = [
    ("dog", "cat", "vet", "animal", "vaccine", "pet", "cachorro", "gato", "vacina", "vomit"),
    ("invoice", "account", "balance", "payment", "tax", "expense",
     "fatura", "conta", "saldo", "pagamento"),
    ("table", "reservation", "menu", "restaurant", "order", "close",
     "mesa", "reservar", "jantar", "cardápio"),
]


class StubEmbedder:
    """Network-free ``Embedder`` — one-hot over keyword buckets."""

    async def embed(self, text: str) -> list[float]:
        t = text.lower()
        return [1.0 if any(k in t for k in kws) else 0.0 for kws in _BUCKETS]
