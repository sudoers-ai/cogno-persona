"""Unit tests for the version-aware prompt + persona loader."""

from pathlib import Path

from cogno_persona import (
    current_version,
    list_versions,
    load_persona,
    load_prompt,
    parse_frontmatter,
)


def test_load_prompt_basic_and_clean(tmp_path: Path):
    (tmp_path / "p.txt").write_text(
        "---\nnote: hi\n---\nReal body line.\nTODO(docs): drop me", encoding="utf-8"
    )
    text = load_prompt(tmp_path, "p.txt")
    assert text == "Real body line."  # frontmatter + TODO(docs) stripped


def test_load_prompt_missing_returns_empty(tmp_path: Path):
    assert load_prompt(tmp_path, "nope.txt") == ""


def test_load_prompt_with_stage_subdir(tmp_path: Path):
    sub = tmp_path / "superego"
    sub.mkdir()
    (sub / "voice.txt").write_text("voice text", encoding="utf-8")
    assert load_prompt(tmp_path, "voice.txt", stage="superego") == "voice text"


def test_version_resolution(persona_dir: Path):
    assert load_prompt(persona_dir, "voice.txt") == "Warm, caring vet voice."
    assert load_prompt(persona_dir, "voice.txt", version="v1") == "Old terse voice."
    assert load_prompt(persona_dir, "voice.txt", version="v2") == "Warm, caring vet voice."


def test_version_unknown_falls_back(persona_dir: Path):
    # Unknown version → default file.
    assert load_prompt(persona_dir, "voice.txt", version="v99") == "Warm, caring vet voice."


def test_list_and_current_version(persona_dir: Path):
    versions = list_versions(persona_dir, "voice.txt")
    assert set(versions) == {"v1", "v2"}
    assert current_version(persona_dir, "voice.txt") == "v2"
    # No meta for system.txt → empty / None.
    assert list_versions(persona_dir, "system.txt") == {}
    assert current_version(persona_dir, "system.txt") is None


def test_parse_frontmatter_no_yaml_returns_body():
    fm, body = parse_frontmatter("no frontmatter here")
    assert fm == {} and body == "no frontmatter here"


def test_load_persona(persona_dir: Path):
    p = load_persona(persona_dir)
    assert p.persona_id == "VETERINARY"
    assert p.allowed_modules == ["veterinary"]
    assert p.text_only is True
    assert p.custom_rules.startswith("Always confirm")
    assert p.prompt("system") == "You are the veterinary specialist."
    assert p.prompt("voice") == "Warm, caring vet voice."


def test_load_persona_versioned(persona_dir: Path):
    p = load_persona(persona_dir, version="v1")
    assert p.prompt("voice") == "Old terse voice."
    assert p.version == "v1"


def test_load_persona_missing_manifest(tmp_path: Path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_persona(tmp_path)


def test_version_points_to_missing_file_falls_back(tmp_path: Path):
    import json
    (tmp_path / "p.txt").write_text("default body", encoding="utf-8")
    (tmp_path / "p_meta.json").write_text(json.dumps({
        "versions": {"v1": {"file": "gone.txt"}}
    }), encoding="utf-8")
    assert load_prompt(tmp_path, "p.txt", version="v1") == "default body"


def test_malformed_meta_falls_back(tmp_path: Path):
    (tmp_path / "p.txt").write_text("default body", encoding="utf-8")
    (tmp_path / "p_meta.json").write_text("{ not json", encoding="utf-8")
    assert load_prompt(tmp_path, "p.txt", version="v1") == "default body"
    assert list_versions(tmp_path, "p.txt") == {}


def test_parse_frontmatter_with_yaml():
    import pytest
    pytest.importorskip("yaml")
    fm, body = parse_frontmatter("---\nname: voice\nv: 2\n---\nthe body")
    assert fm == {"name": "voice", "v": 2}
    assert body == "the body"
