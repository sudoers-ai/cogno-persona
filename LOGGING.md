# Logging in cogno-persona

This library follows the Cogno house rule: **libraries emit, the host configures.**

- Each module does `logger = logging.getLogger(__name__)` and emits lazy
  `key=value` messages. The library installs **no** handlers/formatters and never
  calls `basicConfig`.
- The host attaches its handler and sets the level per package, e.g.
  `logging.getLogger("cogno_persona").setLevel(logging.INFO)`.

## Level policy
- **ERROR** — never emitted. `load_persona` raises `FileNotFoundError` for a
  missing manifest; the host decides how to surface it.
- **WARNING** — recoverable load issues: prompt file missing, a requested version
  not found / its file missing, a malformed `_meta.json`, or a frontmatter parse
  failure. The loader degrades gracefully (default file / empty string).
- **INFO** — `event=prompt_versioned` when a non-default prompt version resolves.
- **DEBUG** — none.

## What gets logged
- `cogno_persona.loader` — INFO `event=prompt_versioned`; WARNING
  `event=prompt_missing|version_unknown|version_file_missing|meta_parse_failed|frontmatter_parse_failed`.
- `cogno_persona.{types,store,selector,compose}` — nothing.

Prompt **bodies** are never logged (only file names / version labels / counts).
