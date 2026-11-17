# Project Manifest — ComfyUI Dynamic Prompt Node

## Overview

One ComfyUI V3 custom node, **Dynamic Prompt Text** (`Mistralys_DynamicPromptText`), that resolves `{a|b|c}` choices on the server and outputs the final prompt string. A `<? ... ?>` preprocessor adds variables (`$name`) and input variables (`$variable_0` to `$variable_19`, wired into the node's `variables` sockets).

## Tech Stack

- Python 3.10+, ComfyUI V3 API (`comfy_api.latest`), stdlib only.
- Tests: `unittest`, with `comfy_api` stubbed.
- CI: GitHub Actions (`tests.yml`, `publish.yml`).

## File Layout

```
__init__.py                  # ComfyExtension + comfy_entrypoint()
nodes.py                     # DynamicPromptTextNode (schema + execute)
pyproject.toml               # Package and Registry metadata
dynamic_prompt/__init__.py   # Facade: resolve_dynamic_prompt(text, seed, *, inputs=None), __all__, error re-exports; no ComfyUI imports
dynamic_prompt/errors.py     # Source, PromptError, PromptSyntaxError, UndefinedVariableError; line/column in messages
dynamic_prompt/text_rules.py # v1 comment/layout patterns moved verbatim, IDENTIFIER, INPUT_VARIABLE, KEYWORDS, unescape_output
dynamic_prompt/evaluator.py  # derive_seed, RandomStreams, VariableTable, Evaluator (Text, Variable, Group, Assignment; evaluate on the body stream, evaluate_with on an explicit stream for input values)
dynamic_prompt/parser.py     # Template, Text, Variable, Group, Assignment nodes; parse()
dynamic_prompt/lexer.py      # TokenKind, Token, Dialect, lex() (BODY/INPUT), strip_standalone_lines (keeps BLOCK tokens, strips layout only)
tests/test_dynamic_prompt.py # Resolver and node tests
tests/test_lexer.py          # Token-level lexer tests: dialects, comment quirks, errors, standalone lines
tests/test_foundation.py     # Tests for errors, text_rules and the evaluator runtime classes
tests/test_seeding.py        # derive_seed golden value, RandomStreams and PYTHONHASHSEED subprocess tests
tests/test_parser.py         # Parser tests
tests/test_parity.py         # Parity of the package against the frozen v1 resolver
tests/test_variables.py      # Variables, interpolation, escapes
tests/test_whitespace.py     # Standalone-line and inline-block whitespace
tests/test_inputs.py         # Input variables: facade `inputs` mapping and node `variables` Autogrow
tests/test_errors.py         # Error types and Line/column positions
tests/test_package_hygiene.py # Stdlib-only imports; no eval/exec/compile
tests/_package_loader.py     # Loads dynamic_prompt/ submodules as dynamic_prompt_new; still used by the lexer, parser, foundation and seeding tests
tests/legacy_v1_resolver.py  # Frozen v1 resolver, reference for parity tests
js/docs/Mistralys_DynamicPromptText.md  # In-app help page, served via WEB_DIRECTORY in __init__.py
docs/agents/project-manifest/preprocessor-grammar.md  # Normative `<? ... ?>` preprocessor grammar, with phase markers and implementation map
```

The `dynamic_prompt/` package replaced the v1 module `dynamic_prompt.py`, which no longer exists; `nodes.py` imports the package facade. The grammar document's implementation map describes its modules. The facade accepts `inputs` (a `variable_N` to string mapping), which the node fills from its `variables` Autogrow input.

## API Surface

| Name | Type | Notes |
|---|---|---|
| `text` | input, `io.String`, multiline | `dynamic_prompts=False` on purpose |
| `seed` | input, `io.Int`, 0 to 2^64-1 | `control_after_generate=True` |
| `variables` | optional input, `io.Autogrow` (`TemplatePrefix`, `io.String` slots) | Prefix `variable_`, `min=0`, `max=MAX_INPUT_VARIABLES` (20); connection-only. `execute(text, seed, variables=None)` passes every `variable_0` to `variable_19` to the resolver, unconnected ones as `""` |
| `PROMPT` | output, `io.String` | Resolved text |

## Data Flow

1. `variables` inputs -> resolve each (own lex/parse/evaluate on its own stream, INPUT dialect) -> variable table.
2. `text` -> lex -> parse -> evaluate (groups chosen from `random.Random(seed)`; assignments and input values from their own `hashlib`-derived streams) -> unescape (one final pass) -> `PROMPT`.

## Behaviour Rules

- Comments: `/* */` is removed anywhere; `//` only at line start or after whitespace.
- Groups: `{a|b|c}` nest. An unclosed `{` is a literal brace; a stray `}` is literal.
- Variables: `<? $name = value ?>` assigns a quoted string template or a group; `$name` interpolates it. An undefined `$name` raises `UndefinedVariableError`.
- Blocks: `<? ... ?>` blocks produce no output of their own. A block alone on a line is removed with its line; an inline block leaves the surrounding text untouched.
- Whitespace: line breaks and indentation at the edges of a chosen option are trimmed; single-line spaces are kept.
- Escapes: `\{`, `\}`, `\|`, `\$` and `\<?`; other backslashes stay. Escapes stay raw until the single final unescape pass.
- Errors: `PromptSyntaxError` and `UndefinedVariableError` (both `PromptError`) carry line and column in their messages.
- Input variables: `$variable_0` to `$variable_19` come from the node's sockets (0-based); unconnected is empty, `$variable_20` and above are undefined, and all are read-only. Frontend rendering of the Autogrow `min=0` has not been checked in a running ComfyUI and needs a manual check.
- Determinism: same text, seed and inputs always give the same output.
- Parity: a prompt without `$` or `<?` resolves byte-for-byte as in v1, whose only deviations from ComfyUI's `processDynamicPrompt` are the `//`, unclosed-`{` and option-trimming rules above (deliberate, user-approved).
- Known parity deviation (accepted): a v1 output that forms `\<?` across a group or comment boundary now decodes to `<?`.

## Constraints

See `AGENTS.md`, section 3.
