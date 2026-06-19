"""Unit tests for the PersonaStore port + in-memory/file defaults."""

import json
from pathlib import Path

from cogno_persona import (
    FilePersonaStore,
    InMemoryPersonaStore,
    Persona,
    PersonaStore,
)


async def test_in_memory_store(personas):
    store = InMemoryPersonaStore(personas)
    assert isinstance(store, PersonaStore)  # runtime-checkable Protocol
    got = await store.get("VETERINARY")
    assert got is not None and got.allowed_modules == ["veterinary"]
    assert await store.get("MISSING") is None
    assert {p.persona_id for p in await store.list()} == {"SECRETARY", "VETERINARY", "BOOKKEEPER"}


async def test_in_memory_add():
    store = InMemoryPersonaStore()
    assert await store.list() == []
    store.add(Persona(persona_id="NEW"))
    assert (await store.get("NEW")).persona_id == "NEW"


async def test_file_store(persona_dir: Path):
    root = persona_dir.parent  # the tmp dir holding VETERINARY/
    store = FilePersonaStore(root)
    got = await store.get("VETERINARY")
    assert got is not None and got.prompt("system") == "You are the veterinary specialist."
    listed = await store.list()
    assert [p.persona_id for p in listed] == ["VETERINARY"]


async def test_file_store_versioned(persona_dir: Path):
    store = FilePersonaStore(persona_dir.parent, version="v1")
    got = await store.get("VETERINARY")
    assert got.prompt("voice") == "Old terse voice."


async def test_file_store_missing(tmp_path: Path):
    store = FilePersonaStore(tmp_path)
    assert await store.get("NOPE") is None
    assert await store.list() == []


async def test_file_store_scan_finds_by_id_when_dirname_differs(tmp_path: Path):
    # Directory name != persona_id → get() falls back to a scan.
    d = tmp_path / "dir_alpha"
    d.mkdir()
    (d / "persona.json").write_text(json.dumps({"persona_id": "REALID"}), encoding="utf-8")
    store = FilePersonaStore(tmp_path)
    got = await store.get("REALID")
    assert got is not None and got.persona_id == "REALID"
