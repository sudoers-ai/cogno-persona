"""
Curated persona catalog + routing cases.

Two suites:

* ``CASES`` — a single shared catalog (base SECRETARY + 3 specialists). Keyword-
  separable so the deterministic stub embedder routes them 100% (CI plumbing guard).
* ``TENANT_CASES`` — **ported from the parent cogno bench** (``multitenant_cases.py``
  sub-dimension *16b Persona Routing*). Each case carries its **own per-tenant
  catalog**, mirroring how a real tenant defines its own persona set. These include
  semantically-close discriminations (e.g. invoice → BILLING, not ANALYST) that
  only a real embedder resolves, so they run in real mode, not the stub smoke.

**The query is the text the selector actually sees: ``noumeno.rewritten`` — canonical
English** (NOUMENO always rewrites before routing). The parent's cases were in PT;
they are translated to English here (the realistic, monolingual routing input). Each
case keeps the pre-NOUMENO ``original`` for documentation. The two parent cases with
``is_multi_persona=False`` are intentionally **omitted**: in this decomposition that
flag is host policy — when routing is off the host simply does not call the selector.
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
    query: str                              # canonical-English text the selector sees
    expected: str
    intent: str = ""                        # NER intent_class; "SOCIAL" → non-routing skip
    personas: tuple[Persona, ...] = ()      # per-case catalog; empty → shared CATALOG
    base: str = BASE_ID
    original: str = ""                      # pre-NOUMENO original (documentation only)
    note: str = ""


# ── single-tenant suite (shared CATALOG; stub-safe) ──────────────────────
CASES: list[RoutingCase] = [
    RoutingCase("my dog has been vomiting since yesterday", "VETERINARY"),
    RoutingCase("can I book a vet appointment for my cat's vaccine?", "VETERINARY"),
    RoutingCase("what is my current account balance and unpaid invoices?", "BOOKKEEPER"),
    RoutingCase("I need to record a payment and an expense for last month", "BOOKKEEPER"),
    RoutingCase("I'd like to reserve a table for four tonight", "RESTAURANT"),
    RoutingCase("what is on the menu and what time do you close?", "RESTAURANT"),
    RoutingCase("my dog is vomiting and refuses to eat", "VETERINARY",
                original="meu cachorro está vomitando e não quer comer"),
    RoutingCase("I need to schedule my cat's vaccine", "VETERINARY",
                original="preciso marcar a vacina do meu gato"),
    RoutingCase("what is my account balance and my open invoices?", "BOOKKEEPER",
                original="qual o saldo da minha conta e as faturas em aberto?"),
    RoutingCase("I want to reserve a table for Friday dinner", "RESTAURANT",
                original="quero reservar uma mesa para o jantar de sexta"),
    RoutingCase("hi, can you help me with something?", "SECRETARY", note="generic"),
    RoutingCase("good morning, how are you?", "SECRETARY", intent="SOCIAL",
                original="bom dia, tudo bem?", note="social greeting → skip routing"),
]


# ── multi-tenant suite — ported from parent 16b (per-case catalogs) ──────
def _p(pid: str, desc: str) -> Persona:
    return Persona(persona_id=pid, description=desc)


_ANALYST = _p("ANALYST", "financial management, expense and revenue control, cash flow and profit analysis")
_SUPPORT = _p("SUPPORT", "technical support, troubleshooting, software and hardware problems, customer service")
_SALES = _p("SALES", "sales, quotes, pricing, plans and commercial negotiation")
_BILLING = _p("BILLING", "billing, issuing invoices, payment slips and collections")
_HR = _p("HR", "human resources, payroll, vacations and hiring")

TENANT_CASES: list[RoutingCase] = [
    RoutingCase("how much did I spend this month?", "ANALYST",
                personas=(_ANALYST, _SUPPORT), original="Quanto gastei esse mês?",
                note="financial → ANALYST"),
    RoutingCase("my system is throwing a 500 error, I need help", "SUPPORT",
                personas=(_ANALYST, _SUPPORT),
                original="Meu sistema está dando erro 500, preciso de ajuda",
                note="technical → SUPPORT"),
    RoutingCase("what is the price of the premium plan for 50 users?", "SALES",
                personas=(_ANALYST, _SALES, _SUPPORT),
                original="Qual o preço do plano premium para 50 usuários?",
                note="sales → SALES"),
    RoutingCase("anything related to my company finances", "ANALYST",
                personas=(_ANALYST,), original="Qualquer coisa sobre finanças",
                note="single specialist configured → routes"),
    RoutingCase("", "SECRETARY", personas=(_ANALYST, _SUPPORT),
                note="empty query → base fallback"),
    RoutingCase("Hi", "SECRETARY", personas=(_ANALYST, _SUPPORT), original="Oi",
                note="too-short greeting → base"),
    RoutingCase("Ok", "SECRETARY", personas=(_ANALYST, _HR), original="Ok",
                note="too-short closing → base"),
    RoutingCase("I need to issue an invoice for the client", "BILLING",
                personas=(_ANALYST, _BILLING),
                original="Preciso emitir nota fiscal para o cliente",
                note="close semantic: invoice → BILLING, not ANALYST"),
    RoutingCase("show me my revenue and profit analysis for this quarter", "ANALYST",
                personas=(_ANALYST, _SUPPORT),
                note="revenue/profit → ANALYST"),
]

ALL_CASES: list[RoutingCase] = CASES + TENANT_CASES
