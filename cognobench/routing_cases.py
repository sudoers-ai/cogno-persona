"""
Curated persona catalog + routing cases.

The catalog is a small multi-domain tenant (a base SECRETARY + three specialists).
Each case is a user query labelled with the persona that *should* win — including
cross-lingual (PT-BR/EN) queries, since cross-lingual embeddings have a narrower
cosine range (the reason the selector's default threshold is 0.25, not ~0.45).
A case with ``expected="SECRETARY"`` (the base) asserts the query is generic
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
    query: str
    expected: str
    lang: str = "en"
    note: str = ""


CASES: list[RoutingCase] = [
    # ── specialist hits (EN) ────────────────────────────────────────────
    RoutingCase("my dog has been vomiting since yesterday", "VETERINARY", "en"),
    RoutingCase("can I book a vet appointment for my cat's vaccine?", "VETERINARY", "en"),
    RoutingCase("what's my current account balance and unpaid invoices?", "BOOKKEEPER", "en"),
    RoutingCase("I need to record a payment and an expense for last month", "BOOKKEEPER", "en"),
    RoutingCase("I'd like to reserve a table for four tonight", "RESTAURANT", "en"),
    RoutingCase("what's on the menu and what time do you close?", "RESTAURANT", "en"),
    # ── specialist hits (PT-BR, cross-lingual vs EN descriptions) ───────
    RoutingCase("meu cachorro está vomitando e não quer comer", "VETERINARY", "pt"),
    RoutingCase("preciso marcar a vacina do meu gato", "VETERINARY", "pt"),
    RoutingCase("qual o saldo da minha conta e as faturas em aberto?", "BOOKKEEPER", "pt"),
    RoutingCase("quero reservar uma mesa para o jantar de sexta", "RESTAURANT", "pt"),
    # ── base fallbacks (generic → no specialist should win) ─────────────
    RoutingCase("hi, can you help me with something?", "SECRETARY", "en", "generic greeting"),
    RoutingCase("bom dia, tudo bem?", "SECRETARY", "pt", "social greeting"),
]
