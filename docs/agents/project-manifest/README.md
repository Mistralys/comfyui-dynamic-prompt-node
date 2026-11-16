# Project Manifest — ComfyUI Dynamic Prompt Node

## Overview

One ComfyUI V3 custom node, **Dynamic Prompt Text** (`Mistralys_DynamicPromptText`), that resolves `{a|b|c}` choices on the server and outputs the final prompt string.

## Tech Stack

- Python 3.10+, ComfyUI V3 API (`comfy_api.latest`), stdlib only.
- Tests: `unittest`, with `comfy_api` stubbed.
- CI: GitHub Actions (`tests.yml`, `publish.yml`).

## File Layout

```
__init__.py                  # ComfyExtension + comfy_entrypoint()
nodes.py                     # DynamicPromptTextNode (schema + execute)
dynamic_prompt.py            # resolve_dynamic_prompt(text, seed), no ComfyUI imports
pyproject.toml               # Package and Registry metadata
tests/test_dynamic_prompt.py # Resolver and node tests
docs/Mistralys_DynamicPromptText.md  # In-app help page
```

## API Surface

| Name | Type | Notes |
|---|---|---|
| `text` | input, `io.String`, multiline | `dynamic_prompts=False` on purpose |
| `seed` | input, `io.Int`, 0 to 2^64-1 | `control_after_generate=True` |
| `PROMPT` | output, `io.String` | Resolved text |

## Data Flow

`text` → strip comments → resolve groups recursively with `random.Random(seed)` → unescape `\{ \} \|` → `PROMPT`.

## Behaviour Rules

- `/* */` comments are removed anywhere; `//` comments only at line start or after whitespace.
- Groups nest. An unclosed `{` is a literal brace; a stray `}` is literal.
- Line breaks and indentation at the edges of a chosen option are trimmed; single-line spaces are kept.
- Only `\{`, `\}` and `\|` are escapes; other backslashes stay.
- Same text and seed always give the same output.
- Vanilla parity: identical to ComfyUI's built-in `processDynamicPrompt` except the `//`, unclosed-`{` and option-trimming rules above (deliberate, user-approved).

## Constraints

See `AGENTS.md`, section 3.
