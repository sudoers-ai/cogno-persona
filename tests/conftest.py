"""Shared test doubles: a deterministic keyword embedder + sample personas."""

import json
from pathlib import Path

import pytest

from cogno_persona import Persona, PersonaPrompts


class KeywordEmbedder:
    """Deterministic ``Embedder`` — a one-hot vector over keyword buckets.

    Text containing a bucket's keyword gets a 1.0 in that slot, so a query and a
    persona description sharing a domain score cosine 1.0, and an off-domain query
    scores 0.0 (a zero vector → below any positive threshold).
    """

    BUCKETS = {
        0: ("dog", "cat", "vet", "animal", "pet"),
        1: ("invoice", "account", "balance", "payment", "bookkeep"),
        2: ("table", "reservation", "menu", "restaurant"),
    }

    async def embed(self, text: str) -> list[float]:
        t = text.lower()
        vec = [0.0, 0.0, 0.0]
        for i, kws in self.BUCKETS.items():
            if any(k in t for k in kws):
                vec[i] = 1.0
        return vec


@pytest.fixture
def embedder() -> KeywordEmbedder:
    return KeywordEmbedder()


@pytest.fixture
def personas() -> list[Persona]:
    return [
        Persona(persona_id="SECRETARY", description="general front desk assistant"),
        Persona(persona_id="VETERINARY", description="pet animal dog vet health care",
                allowed_modules=["veterinary"]),
        Persona(persona_id="BOOKKEEPER", description="invoice account balance payment bookkeep",
                allowed_modules=["bookkeeper"]),
    ]


@pytest.fixture
def persona_dir(tmp_path: Path) -> Path:
    """A on-disk persona directory: manifest + 4 slot files + a versioned voice."""
    root = tmp_path / "VETERINARY"
    root.mkdir()
    (root / "persona.json").write_text(json.dumps({
        "persona_id": "VETERINARY",
        "description": "pet animal dog vet",
        "version": "current",
        "allowed_modules": ["veterinary"],
        "custom_rules": "Always confirm the pet's name first.",
        "text_only": True,
    }), encoding="utf-8")
    (root / "system.txt").write_text("You are the veterinary specialist.", encoding="utf-8")
    (root / "scope.txt").write_text("Allow pet-health questions only.", encoding="utf-8")
    (root / "limits.txt").write_text("Never diagnose without symptoms.", encoding="utf-8")
    (root / "voice.txt").write_text("Warm, caring vet voice.", encoding="utf-8")
    # versioned voice
    (root / "voice_v1.txt").write_text("Old terse voice.", encoding="utf-8")
    (root / "voice_meta.json").write_text(json.dumps({
        "current": "voice.txt",
        "versions": {
            "v1": {"file": "voice_v1.txt", "date": "2026-01-01", "note": "original"},
            "v2": {"file": "voice.txt", "date": "2026-02-01", "note": "warmer"},
        },
    }), encoding="utf-8")
    return root


@pytest.fixture
def sample_persona() -> Persona:
    return Persona(
        persona_id="VETERINARY",
        description="pet vet",
        prompts=PersonaPrompts(
            system="You are the veterinary specialist for {tenant_name}.",
            scope="Allow pet questions only.",
            limits="No diagnosis without symptoms.",
            voice="Warm vet voice.",
        ),
        custom_rules="Always confirm the pet's name.",
        allowed_modules=["veterinary", "scheduler"],
    )
