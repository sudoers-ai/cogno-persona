"""
cogno_persona.loader — version-aware prompt & persona loading from disk.

Ported from the parent ``cogno.core.prompt_loader`` (stdlib logging instead of the
parent's logger; the prompts root is **required**, not a hard-coded path). Each
prompt may have a sibling ``<name>_meta.json`` mapping version labels to files::

    {
      "current": "voice.txt",
      "versions": {
        "v1": {"file": "voice_v1.txt", "date": "2026-03-22", "note": "Original"},
        "v2": {"file": "voice.txt",    "date": "2026-03-23", "note": "Improved"}
      }
    }

On-disk persona layout consumed by ``load_persona``::

    personas/VETERINARY/
        persona.json     # {persona_id, description, version, allowed_modules, ...}
        system.txt  scope.txt  limits.txt  voice.txt
        voice_meta.json  # optional per-slot version map
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from cogno_persona.types import PROMPT_SLOTS, Persona, PersonaPrompts

log = logging.getLogger(__name__)


def _clean_prompt(text: str) -> str:
    """Strip YAML frontmatter and ``TODO(docs)`` lines — dev notes never reach the LLM."""
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            text = parts[1]
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("TODO(docs)")
    ).strip()


def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Split optional YAML frontmatter from a prompt body.

    Returns ``(frontmatter_dict, body)``. Requires PyYAML for a non-empty
    frontmatter (optional ``[yaml]`` extra); without it, frontmatter is skipped.
    """
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) == 2:
        try:
            import yaml  # optional; only needed if prompts carry frontmatter
            frontmatter = yaml.safe_load(parts[0][4:])
            if isinstance(frontmatter, dict):
                return frontmatter, parts[1]
        except Exception as exc:  # pragma: no cover - exercised only with bad/empty yaml
            log.warning("event=frontmatter_parse_failed error=%s", exc)
    return {}, text


def _meta_path(prompt_path: Path) -> Path:
    return prompt_path.with_name(f"{prompt_path.stem}_meta.json")


def load_prompt(
    prompts_dir: Path | str,
    prompt_name: str,
    *,
    version: Optional[str] = None,
    stage: str = "",
) -> str:
    """Load a prompt template (cleaned), resolving ``version`` via its meta file.

    ``prompts_dir`` is the root; ``stage`` is an optional subdirectory (e.g.
    ``"superego"``). Returns ``""`` if the file is absent.
    """
    root = Path(prompts_dir)
    base_dir = root / stage if stage else root
    path = base_dir / prompt_name

    if version:
        meta_file = _meta_path(path)
        if meta_file.exists():
            try:
                versions = json.loads(meta_file.read_text(encoding="utf-8")).get("versions", {})
                if version in versions:
                    resolved = base_dir / versions[version].get("file", prompt_name)
                    if resolved.exists():
                        log.info("event=prompt_versioned name=%s version=%s file=%s",
                                 prompt_name, version, resolved.name)
                        return _clean_prompt(resolved.read_text(encoding="utf-8"))
                    log.warning("event=version_file_missing version=%s file=%s",
                                version, versions[version].get("file"))
                else:
                    log.warning("event=version_unknown version=%s available=%s",
                                version, list(versions))
            except (json.JSONDecodeError, KeyError) as exc:
                log.warning("event=meta_parse_failed file=%s error=%s", meta_file.name, exc)

    if path.exists():
        return _clean_prompt(path.read_text(encoding="utf-8"))
    log.warning("event=prompt_missing path=%s", path)
    return ""


def list_versions(prompts_dir: Path | str, prompt_name: str, *, stage: str = "") -> dict:
    """Return ``{version_label: {file, date, note}}`` for a prompt, or ``{}``."""
    base_dir = Path(prompts_dir) / stage if stage else Path(prompts_dir)
    meta_file = _meta_path(base_dir / prompt_name)
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8")).get("versions", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def current_version(prompts_dir: Path | str, prompt_name: str, *, stage: str = "") -> Optional[str]:
    """Return the version label whose file matches ``current`` in the meta, or ``None``."""
    base_dir = Path(prompts_dir) / stage if stage else Path(prompts_dir)
    meta_file = _meta_path(base_dir / prompt_name)
    if not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        current_file = meta.get("current", "")
        for label, info in meta.get("versions", {}).items():
            if info.get("file") == current_file:
                return label
    except (json.JSONDecodeError, KeyError):
        return None
    return None


# Default filenames for the four prompt slots inside a persona directory.
_SLOT_FILES: Dict[str, str] = {slot: f"{slot}.txt" for slot in PROMPT_SLOTS}


def load_persona(persona_dir: Path | str, *, version: Optional[str] = None) -> Persona:
    """Assemble a ``Persona`` from a directory: ``persona.json`` + the slot files.

    The manifest carries identity/binding/rules; each prompt slot is loaded (and
    version-resolved) from ``<slot>.txt``. A missing slot file is an empty prompt.
    The manifest's own ``version`` is the default when ``version`` is not passed.
    """
    root = Path(persona_dir)
    manifest_path = root / "persona.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"persona manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("persona_id", root.name)
    resolved_version = version or manifest.get("version") or "current"

    prompts = PersonaPrompts(
        **{
            slot: load_prompt(root, filename, version=version)
            for slot, filename in _SLOT_FILES.items()
        }
    )
    manifest["prompts"] = prompts
    manifest["version"] = resolved_version
    return Persona(**manifest)
