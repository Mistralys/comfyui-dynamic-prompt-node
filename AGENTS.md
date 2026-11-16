# AGENTS.md — ComfyUI Dynamic Prompt Node

> Operating manual for AI agents entering this codebase. Read it before making changes.

## 1. Project Documentation

| Document | Path | Purpose |
|---|---|---|
| Project Manifest | `docs/agents/project-manifest/README.md` | Tech stack, file layout, behaviour and constraints |
| README | `README.md` | User-facing description and syntax reference |
| Node help page | `docs/Mistralys_DynamicPromptText.md` | In-app help; the filename must equal the node ID |
| Changelog | `changelog.md` | Release history |

The ComfyUI V3 API skills live in the companion workspace `comfyui-custom-node-skills` (`plugins/comfyui-custom-nodes/skills/`). Check them first for any V3 API question; `skill_test_nodes/` has working examples. The sibling project `comfyui-json-nodes` is the reference for conventions (node ID prefix, packaging, changelog format).

## 2. Documentation Maintenance Rules

| Change Made | Documents to Update |
|---|---|
| Syntax or resolver behaviour | `README.md`, `docs/Mistralys_DynamicPromptText.md`, `changelog.md`, tests |
| Node inputs/outputs | `README.md`, `docs/Mistralys_DynamicPromptText.md`, `docs/agents/project-manifest/README.md` |
| File added or renamed | `docs/agents/project-manifest/README.md` |
| Any user-visible change | `changelog.md` (WIP entry) |

## 3. Key Design Decisions

- **V3 API only** — no V1 fallback.
- **Resolver is pure Python** in `dynamic_prompt.py` with no ComfyUI imports, so it stays testable without ComfyUI.
- **Server-side resolution** — the `text` widget keeps `dynamic_prompts=False` so the browser never resolves the text first.
- **Reproducible** — all randomness comes from `random.Random(seed)`.
- **No external dependencies** — stdlib and ComfyUI builtins only.
- **Vanilla parity** — the syntax matches ComfyUI's built-in `processDynamicPrompt` (frontend `formatUtil`). The only deliberate differences: `//` comments need line start or preceding whitespace, an unclosed `{` is literal, and line breaks and indentation around an option are trimmed. Keep these; do not diverge further.
- **Intentionally focused** — one node. Extra syntax (weights, multi-select, wildcard files) is not planned for 1.x; do not add it without user approval.

## 4. Tests

```bash
python -m unittest discover -s tests -v
```

`tests/test_dynamic_prompt.py` stubs `comfy_api`, so no ComfyUI install is needed.

## 5. Release

The user tags and publishes releases (`v*` tag triggers `.github/workflows/publish.yml`). Do not tag or publish.
