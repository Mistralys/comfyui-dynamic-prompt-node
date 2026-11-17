# Preprocessor Grammar

Living, normative reference for the `<? ... ?>` preprocessor language of the Dynamic Prompt Text node. It is maintained alongside the code; the dated plan `docs/agents/plans/2026-11-17-prompt-preprocessor/plan.md` is only the historical record. Phase 2 (conditions) and later work start here.

Phase markers used below:

- **Phase 1: implemented** - part of release 2.0.0.
- **Phase 2: specified** - designed and reserved, not yet implemented.

Prompts that contain neither `$` nor `<?` resolve exactly as in v1.0.0 (proven by differential tests against `tests/legacy_v1_resolver.py`, which must never be edited).

## Raw output form (invariant)

*Phase 1: implemented.*

From lexing until the final pass, text is held in "raw output form": resolved, but with every escape still carrying its backslash. Variable values are stored in this form, interpolation inserts them unchanged (no re-parsing, no re-resolution), and the final pass (`unescape_output`) runs exactly once. This is what makes v1 parity exact, including the double-backslash quirks.

**Rule for Phase 2 comparisons:** `==` and `!=` must compare `unescape_output(value)` of both sides, never the raw forms.

## 1. Lexical layers

*Phase 1: implemented.*

A prompt is **body text**. Code appears only inside **blocks** `<? ... ?>`. An **input value** (the text connected to a `variable_N` socket) is externally loaded text: choices, escapes and comments only, with no variables and no code. Four text dialects share the body rules, with differences:

| Rule | `BODY` (prompt text, options) | `INPUT` (input value) | `STRING` (`"..."` in code) | `VALUE_GROUP` (unquoted `{...}` value in code) |
|---|---|---|---|---|
| `{a\|b}` choices, nesting | yes | yes | yes | yes |
| `$name` interpolation | yes | no (`$` is literal text) | yes | yes |
| Escapes `\{ \} \| \$ \<?` | yes | yes | yes | yes |
| `\"` → `"` | no (raw pair) | no (raw pair) | yes | no (raw pair) |
| `/* */` and `//` comments | yes (v1 rules) | yes (v1 rules) | **no** (text is data) | yes (v1 rules) |
| `<?` | opens a block | literal text | error | error |
| `?>` | literal text | literal text | error | error |
| `"` | literal | literal | ends the string | literal |
| Unclosed `{` | literal brace (lenient) | literal brace (lenient) | error | error |

## 2. Grammar (EBNF)

*Phase 1: implemented for everything above the "Phase 2" marker. Phase 2: specified for the productions below it.*

```
prompt          = body ;
body            = { text | escape | group | variable | block } ;
group           = "{" option { "|" option } "}" ;          (* BODY: unclosed "{" is literal *)
option          = body ;
variable        = "$" identifier ;
identifier      = ( "A".."Z" | "a".."z" | "_" ) { "A".."Z" | "a".."z" | "0".."9" | "_" } ;
escape          = "\{" | "\}" | "\|" | "\$" | "\<?" ;
block           = "<?" code "?>" ;
code            = statement-list | control ;                (* control: Phase 2 *)
statement-list  = [ statement { separator statement } ] [ separator ] ;
separator       = ";" | line-break ;
statement       = assignment ;
assignment      = variable "=" value ;
value           = string | value-group ;
input-variable  = "variable_" ( "0" | ( "1".."9" ) { "0".."9" } ) ;   (* reserved: read-only, never an assignment target *)
input-value     = { text | escape | group } ;               (* INPUT dialect: "$" and "<?" are plain text; no variable, no block *)
string          = '"' { string-text | escape | '\"' | group | variable } '"' ;
value-group     = "{" option { "|" option } "}" ;           (* VALUE_GROUP dialect, strict *)

(* Phase 2: specified, not implemented *)
control         = "if" expr | "elseif" expr | "else" | "endif" ;
conditional     = if-block body { elseif-block body } [ else-block body ] endif-block ;
expr            = or-expr ;
or-expr         = and-expr { "or" and-expr } ;
and-expr        = not-expr { "and" not-expr } ;
not-expr        = "not" not-expr | comparison ;
comparison      = operand [ ( "==" | "!=" ) operand ] ;     (* non-associative *)
operand         = variable | string | "(" expr ")" ;
```

Code whitespace (spaces, tabs) between code tokens is insignificant; line breaks are statement separators. Keywords are lowercase and case-sensitive. Variable names are ASCII and case-sensitive; the name is the longest identifier after `$`.

## 3. Blocks

*Phase 1: implemented (statement lists). Phase 2: specified (single control statement per block).*

- `<?` opens a block anywhere in `BODY` text, including inside a group option. The block ends at the first `?>` that is not inside a string or a block comment.
- A block holds either a **statement list** (zero or more assignments separated by `;` or line breaks; an empty block is valid and outputs nothing) or exactly **one control statement** (Phase 2). Mixing both in one block is an error.
- A block never produces output. It is replaced by the empty string.

## 4. Assignment

*Phase 1: implemented.*

- `$name = "template"` - a quoted string is a template: it may contain choices, `$vars` and escapes, and may span lines. Comments are not recognised inside strings.
- `$name = {a|b|c}` - an unquoted choice group is a value; its options follow body rules except where the `VALUE_GROUP` column above differs.
- Any other value (`$name = red`, `$name = $other`, single quotes) is an error with a hint to quote the value. `'` is reserved for a possible later literal-string form.
- An input variable name (`variable_0`, `variable_1`, ...; see section 11) is never a valid assignment target. Assigning to one is an error at parse time, whether or not that input is connected and whether or not the assignment would run.
- **Eager:** the value is resolved once, at the assignment, and stored as a string. Every later `$name` yields that same string. Reassignment replaces the value from that point on.
- **Scope:** one global table. A value is visible after its assignment in evaluation order. An assignment inside a group option runs only if that option is chosen.
- **Per-variable seeding:** each assignment draws from its own stream, `random.Random(derive_seed(seed, "assign", name, occurrence))`, where `occurrence` is the 1-based count of assignments to that name in source order. The body keeps v1's `random.Random(seed)`. Consequences: editing, adding or removing assignments never changes the choices made in the body, and never changes another variable's value; inserting an earlier assignment to the same name shifts the occurrence of the later ones. `derive_seed` uses SHA-256 (`hashlib`), never `hash()`.

## 5. Interpolation

*Phase 1: implemented.*

- `$name` in `BODY`, `STRING` or `VALUE_GROUP` text inserts the stored value verbatim. The value is not parsed again, so `{`, `|` or `$` inside it are plain text.
- `$` not followed by an identifier start (`$5`, `$ `, a trailing `$`) is a literal dollar sign.
- An undefined `$name` is an error, in prompt text as well as in code. The message suggests `\$name` for a literal dollar sign.
- **Known boundary edge.** Escapes are decoded by one final pass over the whole output, so a stored value that ends in a lone backslash (for example an input value ending in `\`) combined with a directly following `|`, `{`, `}`, `$` or `<?` in the prompt forms an escape pair across the boundary and is unescaped. "Verbatim" therefore means "inserted without re-parsing"; the final pass still applies. This is a deliberate consequence of the raw output form, documented rather than special-cased.
- The name ends at the first non-identifier character. To glue text directly after a value, use a single-option group: `{$hair}ish`. A dedicated delimiter form (for example `${name}`) is a candidate for a later phase; it is not part of this grammar yet.

## 6. Conditions

*Phase 2: specified, not implemented.*

- `<? if EXPR ?> ... <? elseif EXPR ?> ... <? else ?> ... <? endif ?>`. Keyword terminators only; braces always mean choice.
- A conditional must open and close in the same container: the top level, one group option, or one branch. A `|` or `}` that would split it is an error ("`endif` missing before `|`").
- Only the chosen branch is evaluated. Its choices draw from the current stream (body or assignment), so a different branch can change later body choices for the same seed; this is deterministic and documented.
- Assignments inside an untaken branch do not run.
- Expression semantics: values are strings. `==` and `!=` compare `unescape_output` of both sides, case-sensitively. A bare operand is true when its value is non-empty. Precedence from high to low, as the grammar encodes it: parentheses, `==`/`!=`, `not`, `and`, `or` - so `not $a == "x"` means `not ($a == "x")`. `a == b == c` is an error. String literals in expressions may contain `$vars` and escapes, but a choice group inside one is an error. Undefined variables in expressions are errors (an existence helper is a later-phase candidate).
- Operators `&&`, `||`, `!` are not part of the language; Phase 2 reports them with a hint to use `and`, `or`, `not`.

## 7. Whitespace

*Phase 1: implemented.*

- **Standalone lines:** a line (in the source, after comment removal) that contains at least one block and otherwise only spaces, tabs and comments disappears from the output completely - leading spaces and tabs, the block(s)' output, trailing spaces and tabs, and one line break (`\n` or `\r\n`). The block itself is not discarded: `strip_standalone_lines` keeps every `BLOCK` token in the stream so the parser still executes it (assignments take effect), and removes only the surrounding whitespace and one line break. The facade applies `strip_standalone_lines` to `BODY` tokens only, never to `INPUT` tokens. A block that ends the text with no line break after it removes only its own line content. Multi-line blocks count as one unit: the line where `<?` starts must have only horizontal whitespace before it, and the line where `?>` ends only horizontal whitespace (or comments) after it.
- A line containing only a comment keeps its line break, as in v1 (`a\n// note\nb` → `a\n\nb`).
- **Inline blocks** (sharing the line with other text or syntax) are replaced by the empty string; the surrounding spaces are kept.
- Option trimming (v1 multi-line option rule) applies after standalone lines are removed.

## 8. Comments

*Phase 1: implemented.*

- Body and value-group text: v1 rules exactly. `/* ... */` anywhere (unclosed `/*` stays literal); `//` at line start or after whitespace, up to but not including `\n`.
- Code: `//` anywhere, ending at the line break **or before `?>`** (so `<? $a = "x" // note ?>` works). `/* ... */` anywhere; `?>` inside a block comment does not close the block; an unclosed `/*` in code is an error.
- Strings: no comments.

## 9. Escapes

*Phase 1: implemented.*

- `\{`, `\}`, `\|` (v1), `\$` and `\<?` (new) produce the literal characters. Inside strings, `\"` produces `"`.
- Any other backslash pair is kept as written (v1). Escapes are decoded by the single final pass, so v1's double-backslash behaviour is preserved.
- Accepted parity deviation: because decoding happens once at the end, a v1 output in which `\<?` is formed across a group or comment boundary decodes to `<?`; v1 kept the backslash. It is rare and pinned by `test_new_escape_formed_across_a_group_boundary`.
- There is no escape for a literal `?>` inside a code value; `?>` cannot appear in a value.

## 10. Errors

*Phase 1: implemented for the rows marked Phase 1. Phase 2: specified for the rows marked Phase 2.*

Code is strict; body text and input values are lenient. Every error is a `PromptError` (a `ValueError`) whose message starts with `Line N, column M:`, pointing at the start of the offending construct. Input values cannot raise prompt errors: their dialect has no code and no variables.

| Error | Phase | Raised for |
|---|---|---|
| Unclosed code block | 1 (implemented) | `<?` without `?>` (points at `<?`) |
| Unclosed string | 1 (implemented) | `"` without closing `"`, or `?>` / `<?` found inside a string |
| Unclosed choice group in a value | 1 (implemented) | `{` without `}` in `STRING` or `VALUE_GROUP` |
| Unclosed comment in code | 1 (implemented) | `/*` without `*/` inside a block |
| Invalid statement | 1 (implemented) | missing `=`, missing value, unquoted word value, `$` without a name, single quotes, unexpected character, trailing tokens |
| Undefined variable | 1 (implemented) | `$name` used before any assignment (body, string or value group), or `$variable_N` above the socket maximum |
| Assignment to input variable | 1 (implemented) | `$variable_N = ...` in a block: "`$variable_N` is a node input and cannot be assigned; use another name, e.g. `$hair = \"$variable_N\"`" (points at the `$`) |
| Unsupported keyword | 1 (implemented) | `if`, `elseif`, `else`, `endif`, `and`, `or`, `not` in a block: "conditions are not supported yet" (replaced in Phase 2) |
| Mixed block | 2 (specified) | a control statement combined with other statements |
| Unbalanced conditional | 2 (specified) | `elseif`/`else`/`endif` without `if`, missing `endif`, `else` not last, conditional crossing a group boundary |
| Bad expression | 2 (specified) | operator without operand, unbalanced parentheses, chained comparison, choice in an expression string, `&&`/`\|\|`/`!` |

## 11. Input variables

*Phase 1: implemented.*

- **Sockets.** The node has optional String sockets `variable_0` ... `variable_19` (an `io.Autogrow` input named `variables`; a new slot appears as one is connected). They accept connections only, no widget. The upper bound is the named constant `MAX_INPUT_VARIABLES = 20` in `nodes.py`.
- **Names.** Every name matching `variable_(0|[1-9][0-9]*)` is reserved for inputs, so `$variable_0` always means the socket. Names with a leading zero (`variable_00`, `variable_01`) are ordinary names.
- **Unconnected is empty.** The node passes every slot from 0 to `MAX_INPUT_VARIABLES - 1`; an unconnected slot has the value `""`. Using it outputs nothing and is not an error. A number above the maximum (`$variable_20`) is undefined and raises an error. A direct call to `resolve_dynamic_prompt` without `inputs` defines no input variables.
- **Values are templates.** An input value is resolved with the v1 syntax only (`INPUT` dialect, section 1): choices, nesting, option trimming, comments and escapes. `$` and `<?` are plain text, so a value loaded from a file containing `$word` or `<?` never fails and never refers to another input. It is resolved once, before the prompt, and every `$variable_N` in the prompt yields that same string (eager, like assignments). Cross-input references are not part of the grammar; they can be added later as a non-breaking opt-in.
- **Own random stream.** Each input draws from `random.Random(derive_seed(seed, "input", name))`. Editing the prompt never changes an input's pick, and connecting, disconnecting or changing an input never changes the body's choices or another input's pick.
- **Read-only.** The prompt cannot assign to an input variable (section 4). To give an input a meaningful name, copy it: `<? $hair = "$variable_0" ?>`.
- **Raw output form.** A resolved input value is stored in raw output form like any variable; the single final pass unescapes the whole prompt.

## Parse tree

*Phase 1: implemented.*

`parser.py` turns the token list into a tree of frozen, slotted dataclasses. Text stays in raw output form; nothing is resolved at parse time.

| Node | Fields | Notes |
|---|---|---|
| `Template` | `parts` | Tuple of `Text`, `Variable`, `Group` and `Assignment` parts, evaluated in order. Adjacent text is merged into one `Text`. |
| `Text` | `raw` | Literal text in raw output form. |
| `Variable` | `name`, `offset` | `offset` is the position of the `$` in the source. |
| `Group` | `options`, `offset` | `options` is a tuple of `Template`s, already trimmed. |
| `Assignment` | `name`, `value`, `occurrence`, `offset` | `value` is a `Template` (quoted string) or a `Group` (unquoted choice). `occurrence` is the 1-based per-name count in source order, including assignments inside group options; it keys the assignment's random stream (section 4). |

- **One container loop.** `Parser._parse_template(tokens, start, stop_kinds, strict)` serves the prompt body, group options and string contents. `_parse_block` and `_parse_statement` are the Phase 2 extension points.
- **Lenient and strict groups.** In lenient mode (body, input values) an unclosed `{` becomes `Text("\\{")` and parsing resumes right after the brace; a stray `|` or `}` becomes text. Which `{` is unclosed is decided in one linear pass (a `}` closes the nearest open `{`, as in v1), so the parser never backtracks. In strict mode (strings, value groups) an unclosed `{` is an "Unclosed choice group" error at the brace.
- **Option trimming.** `LEADING_LAYOUT` is trimmed from the first `Text` and `TRAILING_LAYOUT` from the last `Text` of each option, equivalent to v1 trimming the raw option string.
- **Token list lifetime.** The unclosed-brace cache is keyed by `id(tokens)`, so each token list must stay alive for the lifetime of its `Parser`. Callers apply `strip_standalone_lines` to `BODY` tokens before constructing the `Parser`.
- **Known inconsistency.** For an unclosed strict group the reported position is the innermost `{` for some inputs and the outermost for others. The error is always raised and always points at a real unclosed `{`; making it consistently the outermost is a candidate follow-up. This is not covered by tests.

## Implementation map

Package `dynamic_prompt/` (relative imports only; no `eval`, `exec` or `compile`).

| Module | Owns |
|---|---|
| `errors.py` | `Source` (offset to 1-based line and column, error construction), `PromptError`, `PromptSyntaxError`, `UndefinedVariableError`; the `Line N, column M:` format and every error row in section 10. |
| `text_rules.py` | The v1 text constants and helpers (`BLOCK_COMMENT`, `LINE_COMMENT`, `LEADING_LAYOUT`, `TRAILING_LAYOUT`, `trim_layout`), `IDENTIFIER`, `INPUT_VARIABLE` and `is_input_variable` (reserved names, section 11), `KEYWORDS`, and `unescape_output` (the single final pass; section 9 and the raw-output-form rule). |
| `lexer.py` | Dialects and the dialect table (section 1), tokenisation of text, groups, variables and blocks, comment rules (section 8), escape pairing (section 9), and `strip_standalone_lines` (section 7). |
| `parser.py` | Tree nodes (`Template`, `Text`, `Variable`, `Group`, `Assignment`), group parsing (lenient in `BODY`, strict in strings and value groups), option trimming, statement parsing and assignment rules (sections 3 and 4), occurrence numbering, assignment to input variables and unsupported-keyword errors. Phase 2 adds `Conditional` and expression nodes here (or in `expressions.py`) by extending `_parse_block` and `_parse_statement`. |
| `evaluator.py` | `derive_seed`, `RandomStreams` (body, per-assignment, per-input streams), `VariableTable`, and `Evaluator` (interpolation and eager assignment, sections 4, 5 and 11; `evaluate` draws from the body stream, `evaluate_with` from an explicit stream, which the facade uses for each input value); the undefined-variable error. Phase 2 conditional evaluation lands here. |
| `__init__.py` | The public facade `resolve_dynamic_prompt(text, seed, *, inputs=None)` and re-exports; wires input resolution, lex, parse, evaluate and the final `unescape_output`; owns the raw-output-form invariant at the pipeline level. |
