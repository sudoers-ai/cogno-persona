"""
cogno_persona.store — the retrieval seam for personas.

``PersonaStore`` is a tiny async Protocol the host implements over its own backing
(a DB table, a cache). Two zero-dependency defaults ship here (the homeo pattern —
in-memory default + injectable store): ``InMemoryPersonaStore`` for tests/seeding
and ``FilePersonaStore`` that lazily loads persona directories from disk via
``cogno_persona.loader.load_persona``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Protocol, runtime_checkable

from cogno_persona.loader import load_persona
from cogno_persona.types import Persona


@runtime_checkable
class PersonaStore(Protocol):
    """Async read access to the set of personas available to a host/tenant."""

    async def get(self, persona_id: str) -> Optional[Persona]: ...

    async def list(self) -> List[Persona]: ...


class InMemoryPersonaStore:
    """Process-local ``PersonaStore`` over a dict. Default for tests and seeding."""

    def __init__(self, personas: Optional[List[Persona]] = None) -> None:
        self._by_id: Dict[str, Persona] = {p.persona_id: p for p in (personas or [])}

    def add(self, persona: Persona) -> None:
        self._by_id[persona.persona_id] = persona

    async def get(self, persona_id: str) -> Optional[Persona]:
        return self._by_id.get(persona_id)

    async def list(self) -> List[Persona]:
        return list(self._by_id.values())


class FilePersonaStore:
    """``PersonaStore`` backed by a directory of persona subdirectories.

    Each immediate subdirectory containing a ``persona.json`` is one persona.
    Loads are cached after first read; pass ``version`` to pin a prompt version
    across the whole store.
    """

    def __init__(self, root_dir: Path | str, *, version: Optional[str] = None) -> None:
        self._root = Path(root_dir)
        self._version = version
        self._cache: Dict[str, Persona] = {}
        self._scanned = False

    def _persona_dirs(self) -> List[Path]:
        if not self._root.is_dir():
            return []
        return [d for d in sorted(self._root.iterdir()) if (d / "persona.json").exists()]

    async def get(self, persona_id: str) -> Optional[Persona]:
        if persona_id in self._cache:
            return self._cache[persona_id]
        path = self._root / persona_id
        if (path / "persona.json").exists():
            persona = load_persona(path, version=self._version)
            self._cache[persona.persona_id] = persona
            return persona
        # Fall back to a full scan (the directory name may differ from the id).
        for persona in await self.list():
            if persona.persona_id == persona_id:
                return persona
        return None

    async def list(self) -> List[Persona]:
        if not self._scanned:
            for d in self._persona_dirs():
                persona = load_persona(d, version=self._version)
                self._cache.setdefault(persona.persona_id, persona)
            self._scanned = True
        return list(self._cache.values())
