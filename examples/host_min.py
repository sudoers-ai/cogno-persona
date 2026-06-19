"""
Minimal host wiring for cogno-persona — store → select → compose, end to end.

Run: python examples/host_min.py
(Uses an in-memory store + a toy embedder; no network, no DB.)
"""

import asyncio

from cogno_persona import (
    InMemoryPersonaStore,
    Persona,
    PersonaPrompts,
    PersonaSelector,
    compose_prompt,
)


class ToyEmbedder:
    """One-hot over keyword buckets — stands in for a real cogno-synapse Embedder."""

    BUCKETS = {0: ("dog", "vet", "pet"), 1: ("invoice", "account", "balance")}

    async def embed(self, text: str) -> list[float]:
        t = text.lower()
        return [1.0 if any(k in t for k in kws) else 0.0 for kws in self.BUCKETS.values()]


def seed() -> InMemoryPersonaStore:
    return InMemoryPersonaStore([
        Persona(persona_id="SECRETARY", description="general front desk"),
        Persona(
            persona_id="VETERINARY",
            description="pet dog vet health",
            allowed_modules=["veterinary"],
            custom_rules="Always confirm the pet's name first.",
            prompts=PersonaPrompts(
                system="You are the veterinary specialist for {tenant_name}.",
                scope="Allow pet-health questions only.",
                limits="Never diagnose without symptoms.",
                voice="Warm, caring vet voice.",
            ),
        ),
    ])


async def main() -> None:
    store = seed()
    selector = PersonaSelector(ToyEmbedder())

    result = await selector.select(
        "my dog is sick, need a vet",
        candidates=await store.list(),
        base_persona_id="SECRETARY",
    )
    print(f"selected: {result.persona_id} (matched={result.matched}, score={result.score:.2f})")

    active = await store.get(result.persona_id)
    assert active is not None

    system = compose_prompt(active, "system", base="GLOBAL RULES",
                            context={"tenant_name": "PetCo"})
    print("\n--- composed system prompt ---")
    print(system)

    print("\n--- other slots (host injects into SUPEREGO) ---")
    for slot in ("scope", "limits", "voice"):
        print(f"{slot:>7}: {compose_prompt(active, slot)}")


if __name__ == "__main__":
    asyncio.run(main())
