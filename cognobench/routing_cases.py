"""
Curated persona catalog + routing cases.

The catalog is a small multi-domain tenant (a base SECRETARY + three specialists).

**The query is the text the selector actually sees in the pipeline:
``noumeno.rewritten`` — canonical English** (NOUMENO always rewrites before the
selector runs), so routing is monolingual. Each case keeps the pre-NOUMENO
``original`` (PT/EN) for documentation only. ``intent`` carries the NER class; a
``SOCIAL`` case exercises the selector's non-routing short-circuit (→ base, no
embedding). A case with ``expected="SECRETARY"`` asserts the query is generic
enough that no specialist should hijack it.
"""

from __future__ import annotations

from dataclasses import dataclass

from cogno_persona import Persona

BASE_ID = "SECRETARY"

CATALOG: list[Persona] = [
    Persona(persona_id="SECRETARY", description="general front desk assistant, greetings, scheduling, generic help"),
    Persona(persona_id="VETERINARY", description="pet and animal health: dogs, cats, vaccines, symptoms, vet appointments",
            allowed_modules=["veterinary"]),
    Persona(persona_id="BOOKKEEPER", description="accounting and finance: invoices, account balance, payments, taxes, expenses",
            allowed_modules=["bookkeeper"]),
    Persona(persona_id="RESTAURANT", description="restaurant service: table reservations, menu, opening hours, food orders",
            allowed_modules=["restaurant"]),
]


@dataclass(frozen=True)
class RoutingCase:
    query: str          # the canonical-English text the selector sees (post-NOUMENO)
    expected: str
    intent: str = ""    # NER intent_class; "SOCIAL" exercises the non-routing skip
    original: str = ""  # pre-NOUMENO original (documentation only)
    note: str = ""


CASES: list[RoutingCase] = [
    # ── specialist hits (originally EN) ──────────────────────────────────
    RoutingCase("my dog has been vomiting since yesterday", "VETERINARY"),
    RoutingCase("can I book a vet appointment for my cat's vaccine?", "VETERINARY"),
    RoutingCase("what is my current account balance and unpaid invoices?", "BOOKKEEPER"),
    RoutingCase("I need to record a payment and an expense for last month", "BOOKKEEPER"),
    RoutingCase("I'd like to reserve a table for four tonight", "RESTAURANT"),
    RoutingCase("what is on the menu and what time do you close?", "RESTAURANT"),
    # ── specialist hits (NOUMENO-rewritten from PT-BR) ───────────────────
    RoutingCase("my dog is vomiting and refuses to eat", "VETERINARY",
                original="meu cachorro está vomitando e não quer comer"),
    RoutingCase("I need to schedule my cat's vaccine", "VETERINARY",
                original="preciso marcar a vacina do meu gato"),
    RoutingCase("what is my account balance and my open invoices?", "BOOKKEEPER",
                original="qual o saldo da minha conta e as faturas em aberto?"),
    RoutingCase("I want to reserve a table for Friday dinner", "RESTAURANT",
                original="quero reservar uma mesa para o jantar de sexta"),
    # ── base fallbacks (generic / social → no specialist should win) ─────
    RoutingCase("hi, can you help me with something?", "SECRETARY", note="generic"),
    RoutingCase("good morning, how are you?", "SECRETARY", intent="SOCIAL",
                original="bom dia, tudo bem?", note="social greeting → skip routing"),
]
