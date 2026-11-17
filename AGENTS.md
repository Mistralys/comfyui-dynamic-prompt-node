# AGENTS.md — ComfyUI Dynamic Prompt Node

> Operating manual for AI agents entering this codebase. Read it before making changes.

## 1. Project Documentation

| Document | Path | Purpose |
|---|---|---|
| Project Manifest | `docs/agents/project-manifest/README.md` | Tech stack, file layout, behaviour and constraints |
| README | `README.md` | User-facing description and syntax reference |
| Node help page | `js/docs/Mistralys_DynamicPromptText.md` | In-app help; the filename must equal the node ID |
| Preprocessor grammar | `docs/agents/project-manifest/preprocessor-grammar.md` | Normative `<? ... ?>` grammar, phase markers, implementation map |
| Changelog | `changelog.md` | Release history |

The ComfyUI V3 API skills live in the companion workspace `comfyui-custom-node-skills` (`plugins/comfyui-custom-nodes/skills/`). Check them first for any V3 API question; `skill_test_nodes/` has working examples. The sibling project `comfyui-json-nodes` is the reference for conventions (node ID prefix, packaging, changelog format).

**Exception:** the skills wrongly say node help pages go in `docs/`. In-app help pages must live in `js/docs/<node_id>.md`, with `WEB_DIRECTORY = "./js"` set in `__init__.py`.

## 2. Documentation Maintenance Rules

| Change Made | Documents to Update |
|---|---|
| Syntax or resolver behaviour | `README.md`, `js/docs/Mistralys_DynamicPromptText.md`, `changelog.md`, tests |
| Node inputs/outputs | `README.md`, `js/docs/Mistralys_DynamicPromptText.md`, `docs/agents/project-manifest/README.md` |
| File added or renamed | `docs/agents/project-manifest/README.md` |
| Any user-visible change | `changelog.md` (WIP entry) |

## 3. Key Design Decisions

- **V3 API only** — no V1 fallback.
- **Resolver is a pure-Python package**, `dynamic_prompt/` (lexer, parser, tree, evaluator, errors, text rules), with no ComfyUI imports, so it stays testable without ComfyUI. Modules use relative imports only; there is no `eval`, `exec` or `compile` anywhere (enforced by `tests/test_package_hygiene.py`).
- **Server-side resolution** — the `text` widget keeps `dynamic_prompts=False` so the browser never resolves the text first.
- **Reproducible** — all randomness comes from `random.Random` streams. Per-variable seeds are derived with `hashlib` (`derive_seed`), never the builtin `hash()`, which varies per process.
- **Raw output form** — evaluation keeps escapes (`\{`, `\}`, `\|`, `\$`, `\<?`) in raw form, including inside variable values, until one final unescape pass at the end. Do not unescape earlier.
- **No external dependencies** — stdlib and ComfyUI builtins only.
- **Strict superset of vanilla** — a prompt without `$` or `<?` resolves byte-for-byte as in the v1 resolver (frozen in `tests/legacy_v1_resolver.py`), which matched ComfyUI's built-in `processDynamicPrompt` except for three deliberate deviations. Keep all three: `//` comments need line start or preceding whitespace, an unclosed `{` is literal, and line breaks and indentation around an option are trimmed. Keep the deviation set closed.
- **Preprocessor approved** — the `<? ... ?>` language (variables, `$var` interpolation, input variables) is user-approved and specified in the grammar document. Further syntax (weights, multi-select, wildcard files) is still not planned and needs user approval.
- **Input variables** — the optional `variables` Autogrow input offers sockets `variable_0` to `variable_19` (`MAX_INPUT_VARIABLES` in `nodes.py`), read in the prompt as `$variable_N`. Each value is a single wired string, resolved like the prompt text. JSON-object and multi-value inputs were rejected by the user; do not add them.

## 4. Tests

```bash
python -m unittest discover -s tests -v
```

`tests/test_dynamic_prompt.py` stubs `comfy_api`, so no ComfyUI install is needed.

`tests/legacy_v1_resolver.py` is the frozen v1 resolver and the oracle for the parity tests. Never edit it.

## 5. Release

The user tags and publishes releases (`v*` tag triggers `.github/workflows/publish.yml`). Do not tag or publish.
