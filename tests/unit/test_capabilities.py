"""The capability ENGINE: declare → validate → emit → select → render.

Every fixture here is invented (``alpha``/``beta``/``bridge``, tools ``t1``/``t2``): the
engine must not need a real capability to work, and a test that borrowed one would hide
the day it starts to.

The laws under test, in the order a turn meets them:

* ``validate`` rejects a table that cannot render honestly — a heading owned twice, a
  variant that can never win, a bridge over a tool no part requires;
* ``emitting_capabilities`` folds the caller's gates, and a composed capability rides its
  parts' gates rather than one of its own;
* ``select_variant`` degrades to a weaker AUTHORED text instead of dropping the block;
* ``render_capabilities`` never renders a block whose tools the turn withholds, and says
  what it would have taken when it renders none.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cogno_persona import (
    Capability,
    MissingCapability,
    emitting_capabilities,
    render_capabilities,
    select_variant,
    validate_capabilities,
)

ALPHA = Capability(
    name="alpha", purpose="do the first thing", family="fam_a",
    variants=((frozenset({"t1"}), "## Alpha duty\nCall `t1`."),))
BETA = Capability(
    name="beta", purpose="do the second thing", family="fam_b",
    variants=((frozenset({"t2"}), "## Beta duty\nCall `t2`."),))
# Two strengths of ONE capability: same heading, fullest first.
GRADED = Capability(
    name="graded", purpose="do it well, or do it at all", family="fam_a",
    variants=(
        (frozenset({"t1", "t2"}), "## Graded duty\nCall `t1` then `t2`."),
        (frozenset({"t1"}), "## Graded duty\nCall `t1` and ask for the rest."),
    ))
BRIDGE = Capability(
    name="bridge", purpose="teach alpha and beta together", family="",
    variants=((frozenset({"t1"}), "## Bridge duty\nWhen `t1` comes back empty, try beta."),),
    includes=("alpha", "beta"))

TABLE = (ALPHA, BETA, BRIDGE)
WIRED = {"fam_a": True, "fam_b": True}


# ── validate ─────────────────────────────────────────────────────────────────────────

def test_a_well_formed_table_has_no_errors():
    assert validate_capabilities(TABLE) == []
    assert validate_capabilities(()) == []


@pytest.mark.parametrize("cap, fragment", [
    (replace(ALPHA, name="beta"), "duplicate capability name"),
    (replace(ALPHA, name="blank", purpose="   "), "empty purpose"),
    (replace(ALPHA, name="empty", variants=()), "no variants"),
    (replace(ALPHA, name="nofam", family=""), "needs a family"),
    (replace(ALPHA, name="badshape", variants=(("t1", "## H\nx", 3),)),
     "a variant is (requires, text)"),
    (replace(ALPHA, name="notfrozen", variants=(({"t1"}, "## H\nx"),)),
     "requires must be a frozenset"),
    (replace(ALPHA, name="noheading", variants=((frozenset({"t1"}), "no heading here"),)),
     "must open with a '## heading' line"),
    (replace(ALPHA, name="oneline", variants=((frozenset({"t1"}), "## Heading only"),)),
     "must open with a '## heading' line"),
])
def test_validate_names_the_malformed_capability(cap, fragment):
    errors = validate_capabilities(TABLE + (cap,))
    assert any(fragment in e for e in errors), errors


def test_a_heading_belongs_to_one_capability():
    """A rendered block is identified by its heading line, so a heading owned twice would
    make two capabilities indistinguishable to anyone reading the prompt back."""
    thief = replace(ALPHA, name="thief", variants=((frozenset({"t2"}), "## Alpha duty\nMine."),))
    assert any("belongs to 'alpha'" in e for e in validate_capabilities(TABLE + (thief,)))


def test_the_variants_of_one_capability_share_a_heading():
    split = replace(GRADED, variants=(GRADED.variants[0],
                                      (frozenset({"t1"}), "## Other duty\nweaker")))
    assert any("must share one heading" in e for e in validate_capabilities((split,)))


def test_a_variant_that_can_never_win_is_dead_text():
    """Selection takes the FIRST fitting variant, so a later one requiring everything an
    earlier one does is unreachable — including an exact duplicate."""
    dead = replace(GRADED, variants=(GRADED.variants[1], GRADED.variants[0]))
    assert any("unreachable" in e for e in validate_capabilities((dead,)))
    dup = replace(ALPHA, variants=(ALPHA.variants[0], ALPHA.variants[0]))
    assert any("unreachable" in e for e in validate_capabilities((dup,)))


@pytest.mark.parametrize("cap, fragment", [
    (replace(BRIDGE, family="fam_a"), "has no family of its own"),
    (replace(BRIDGE, includes=("alpha", "alpha")), "listed twice"),
    (replace(BRIDGE, includes=("alpha", "ghost")), "must be declared earlier"),
    (replace(BRIDGE, includes=("beta", "alpha"),
             variants=((frozenset({"t3"}), "## Bridge duty\nCall `t3`."),)),
     "bridge requires ['t3']"),
])
def test_validate_rejects_a_malformed_bridge(cap, fragment):
    errors = validate_capabilities((ALPHA, BETA, cap))
    assert any(fragment in e for e in errors), errors


def test_a_part_must_be_declared_before_its_bridge():
    """Declaration order IS render order (parts first, bridge after), which is also what
    makes a cycle impossible to write."""
    assert any("declared earlier" in e for e in validate_capabilities((BRIDGE, ALPHA, BETA)))


# ── emit ─────────────────────────────────────────────────────────────────────────────

def test_emitting_folds_the_callers_gates():
    assert [c.name for c in emitting_capabilities(
        TABLE, wired=WIRED, emitting={"fam_a", "fam_b"})] == ["alpha", "beta", "bridge"]
    assert [c.name for c in emitting_capabilities(
        TABLE, wired=WIRED, emitting={"fam_a"})] == ["alpha"]
    assert [c.name for c in emitting_capabilities(
        TABLE, wired={"fam_a": False, "fam_b": True}, emitting={"fam_a", "fam_b"})] == ["beta"]


def test_the_bridge_rides_its_parts_gates_and_never_one_of_its_own():
    """Losing a part degrades the union to the other part with no bridge — never to a
    bridge over a tool that rode no gate at all."""
    got = emitting_capabilities(TABLE, wired={"fam_a": True, "fam_b": False},
                                emitting={"fam_a", "fam_b"})
    assert [c.name for c in got] == ["alpha"]


def test_a_family_the_wiring_does_not_know_fails_loudly():
    """Strict indexing on purpose: a table family absent from the wiring raises on the
    first turn instead of silently never emitting."""
    with pytest.raises(KeyError):
        emitting_capabilities(TABLE, wired={"fam_a": True}, emitting={"fam_a", "fam_b"})


# ── select ───────────────────────────────────────────────────────────────────────────

def test_select_takes_the_fullest_variant_the_surface_honours():
    assert select_variant(GRADED, frozenset({"t1", "t2"}))[0] == 0
    assert select_variant(GRADED, frozenset({"t1"})) == (1, GRADED.variants[1][1])
    assert select_variant(GRADED, frozenset({"t2"})) is None


def test_a_variant_requiring_nothing_always_renders():
    anchor = Capability(name="anchor", purpose="needs no tool", family="fam_a",
                        variants=((frozenset(), "## Anchor duty\nQuote the anchor."),))
    assert select_variant(anchor, frozenset()) == (0, anchor.variants[0][1])


# ── render ───────────────────────────────────────────────────────────────────────────

def test_a_rendered_block_never_commands_a_tool_the_turn_withholds():
    """The whole reason the engine exists: a capability naming an absent tool orders the
    model not to answer on its own and gives it nothing to call."""
    out = render_capabilities([ALPHA, BETA], frozenset({"t1"}))
    assert out.rendered == ("alpha",)
    assert "`t2`" not in out.text
    assert out.unavailable == (MissingCapability(capability="beta", missing=("t2",)),)


def test_blocks_are_joined_in_table_order():
    out = render_capabilities([ALPHA, BETA], frozenset({"t1", "t2"}))
    assert out.text == f"{ALPHA.variants[0][1]}\n\n{BETA.variants[0][1]}"
    assert out.rendered == ("alpha", "beta")
    assert out.unavailable == ()


def test_nothing_rendered_is_an_empty_text_not_a_stray_separator():
    out = render_capabilities([ALPHA], frozenset())
    assert out.text == ""


def test_a_masked_tool_degrades_the_block_instead_of_dropping_it():
    out = render_capabilities([GRADED], frozenset({"t1"}))
    assert out.text == GRADED.variants[1][1]
    assert out.rendered == ("graded",) and out.unavailable == ()


def test_missing_names_the_least_demanding_variant():
    """What it would have TAKEN. Naming the fullest variant's tools would overstate the
    gap — the turn was one tool short of the degraded text, not two short of the full one."""
    out = render_capabilities([GRADED], frozenset())
    assert out.unavailable == (MissingCapability(capability="graded", missing=("t1",)),)


def test_missing_subtracts_what_the_turn_does_offer():
    two = Capability(name="two", purpose="p", family="fam_a",
                     variants=((frozenset({"t1", "t2"}), "## Two duty\nCall `t1` and `t2`."),))
    assert render_capabilities([two], frozenset({"t1"})).unavailable == (
        MissingCapability(capability="two", missing=("t2",)),)


def test_a_capability_with_no_variants_reports_an_empty_gap():
    """Malformed (``validate`` says so), but the renderer must not raise on it: a prompt
    is not the place to discover a table defect."""
    out = render_capabilities([replace(ALPHA, variants=())], frozenset())
    assert out.unavailable == (MissingCapability(capability="alpha", missing=()),)


def test_the_bridge_renders_only_over_parts_at_full_strength():
    """The bridge is written against the parts' fullest text; over a degraded part it
    presumes a flow the page no longer instructs."""
    graded_part = replace(GRADED, name="alpha")   # same slot, now two strengths
    table = [graded_part, BETA, replace(BRIDGE, includes=("alpha", "beta"))]
    full = render_capabilities(table, frozenset({"t1", "t2"}))
    assert full.rendered == ("alpha", "beta", "bridge")
    degraded = render_capabilities([graded_part, BETA, replace(BRIDGE, includes=("alpha", "beta"))],
                                   frozenset({"t1"}))
    assert degraded.rendered == ("alpha",)        # alpha at variant 1, beta absent, no bridge


def test_the_bridge_is_skipped_when_a_part_did_not_render_at_all():
    out = render_capabilities(TABLE, frozenset({"t1"}))
    assert out.rendered == ("alpha",)
    assert "Bridge duty" not in out.text
    # And the bridge is not reported as a gap either: it never got as far as selection.
    assert [m.capability for m in out.unavailable] == ["beta"]


# ── the caller's suffix ──────────────────────────────────────────────────────────────

def test_a_suffix_is_appended_to_the_named_block_only():
    out = render_capabilities([ALPHA, BETA], frozenset({"t1", "t2"}),
                              suffixes={"alpha": "\n- extra line"})
    assert out.text == (f"{ALPHA.variants[0][1]}\n- extra line\n\n{BETA.variants[0][1]}")


def test_a_suffix_for_a_capability_that_did_not_render_contributes_nothing():
    out = render_capabilities([ALPHA], frozenset(), suffixes={"alpha": "\n- extra line"})
    assert out.text == ""


def test_an_empty_suffix_leaves_the_block_byte_identical():
    plain = render_capabilities([ALPHA], frozenset({"t1"})).text
    assert render_capabilities([ALPHA], frozenset({"t1"}), suffixes={"alpha": ""}).text == plain
    assert render_capabilities([ALPHA], frozenset({"t1"}), suffixes={}).text == plain


def test_the_separator_is_the_callers_to_choose():
    out = render_capabilities([ALPHA, BETA], frozenset({"t1", "t2"}), separator="\n")
    assert out.text == f"{ALPHA.variants[0][1]}\n{BETA.variants[0][1]}"
