# Plan

## Plan Audit Cycles
- Audits: 2 (Sonnet 5.5 ×2) — Plan Auditor v1.13.1
- Architectural Reviews: 1 (Sonnet 5.5 ×1) — Plan Architect Reviewer v2.5.1

## Summary

Add a small preprocessor language to the Dynamic Prompt Text node so a value such as a main colour can be set once and reused, and so later conditional logic has a home. Code lives in PHP-style `<? ... ?>` blocks. Variables are `$name` both inside blocks and in plain prompt text. This plan does three things: (1) it fixes the **complete grammar** for every phase (blocks, assignment, interpolation, conditions, expressions, whitespace, escapes, errors), (2) it replaces the v1 character scanner with a tokenizer → parser → tree → evaluator pipeline inside a new `dynamic_prompt/` package, and (3) it implements **Phase 1**: `<? ?>` blocks, assignments, `$var` interpolation, choice groups as values, per-variable seeding, strict code errors and **input variables**. Input variables are optional String sockets on the node, `variable_0`, `variable_1`, … (an `io.Autogrow` input that adds a slot each time one is connected). Their values are resolved as templates (choices, escapes and comments only; `$` and `<?` stay literal text) and are available in the prompt as read-only `$variable_N`, so a value loaded by another node (for example a JSON string node) can be wired straight into the prompt. Phase 2 (`if/elseif/else/endif` and expressions) and later phases (helpers) are specified and given parser and evaluator seams, but are not implemented. `resolve_dynamic_prompt(text, seed)` stays callable with two arguments and gains a keyword-only `inputs` mapping; `nodes.py` gains the Autogrow input. Every prompt that contains neither `$` nor `<?` resolves byte-for-byte as in v1, whether or not inputs are connected. Because `$word` in existing prompts now means a variable, this is release **2.0.0**.

## Architectural Context

- `dynamic_prompt.py` (L1–L77) is the whole resolver today. `resolve_dynamic_prompt(text, seed)` (L73–L77) runs three stages: a global comment-strip regex `_COMMENTS` (L10) over the original text, a recursive character scanner (`_resolve` L49–L70 and `_read_group` L21–L46) that draws one `rng.choice` per group from a single `random.Random(seed)`, and a final unescape regex `_ESCAPES` (L11) over the resolved output. Options are trimmed with `_trim_layout` (L13–L18) **before** they are resolved. A backslash always consumes the next character as a raw pair; the unescape happens only at the end.
- `nodes.py` (L1–L35) imports it relatively (`from .dynamic_prompt import resolve_dynamic_prompt`) and calls it in `execute(cls, text, seed)`. Exceptions propagate to ComfyUI, which displays them on the node.
- ComfyUI V3 `io.Autogrow` (upstream `comfy_api/latest/_io.py`; companion skill `comfyui-node-advanced` SKILL.md L83–L133): `TemplatePrefix(input, prefix, min, max)` creates slots `prefix0` … `prefix{max-1}` (0-based, like other Autogrow nodes); slots with index `< min` are required, the rest optional (`min >= 0` is allowed); widget templates are forced connection-only; `execute` receives a dict of **connected** slots only (unconnected slots are omitted; nothing connected gives an empty dict).
- `tests/test_dynamic_prompt.py` imports it as a top-level module (`from dynamic_prompt import resolve_dynamic_prompt`, L13, after `sys.path.insert(0, REPO)`), and loads the repo as a package with `comfy_api` stubbed for node tests (L114–L152).
- `AGENTS.md` §3 binds the design: V3 only, pure Python resolver without ComfyUI imports, server-side resolution (`dynamic_prompts=False`), all randomness via `random.Random(seed)`, stdlib only, vanilla parity with three listed deviations, one node.
- v1 quirks that the new pipeline must reproduce (verified by probe, see research brief): `\\|` → `\|`; `\\{a|b}` → `\\a`; `\/* c */{a|b}` → `{a|b}`; `{x\/**/|y}` → `x|y`; `/*x*///y` → `//y`; `a //x\r\nb` → `a \nb`; a single-option group still advances the random stream.

## Approach / Architecture

### Package layout (all new; replaces `dynamic_prompt.py`)

`dynamic_prompt.py` becomes the package `dynamic_prompt/`. Both existing import styles keep working: `from dynamic_prompt import resolve_dynamic_prompt` (tests, repo root on `sys.path`) and `from .dynamic_prompt import resolve_dynamic_prompt` (`nodes.py`). Every module inside the package uses relative imports only.

| Module (new) | Responsibility |
|---|---|
| `dynamic_prompt/__init__.py` | Public facade: `resolve_dynamic_prompt(text, seed, *, inputs=None)`; re-exports `PromptError`, `PromptSyntaxError`, `UndefinedVariableError`, `INPUT_VARIABLE`. Wires the pipeline: input values (each `Source` → `lex` in `INPUT` dialect → `parse` → evaluate into the table) → prompt `Source` → `lex` → `parse` → `Evaluator.evaluate` → `unescape_output`. |
| `dynamic_prompt/errors.py` | `Source(text)`: holds a text and maps an offset to `(line, column)` (1-based) via `bisect` over precomputed newline offsets, and builds errors from offsets. `PromptError(ValueError)` with `message`, `line`, `column` and `__str__` = `Line {line}, column {column}: {message}`; subclasses `PromptSyntaxError` and `UndefinedVariableError` (adds `name`). Built through a `Source` so every error names a line. `Source` lives here because it exists only to build errors. |
| `dynamic_prompt/text_rules.py` | The v1 text constants and helpers, moved verbatim and split: `BLOCK_COMMENT = r"/\*[\s\S]*?\*/"`, `LINE_COMMENT = r"(?<!\S)//.*"`, `LEADING_LAYOUT`, `TRAILING_LAYOUT`, `trim_layout()`, plus `IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"`, `INPUT_VARIABLE = re.compile(r"variable_(?:0|[1-9][0-9]*)")` (reserved input names, used with `fullmatch`), `KEYWORDS` (reserved words) and `unescape_output()` (final pass, regex `\\([{}|$]|<\?)` → group 1). |
| `dynamic_prompt/lexer.py` | Mode-aware scanner: `TokenKind` enum, frozen `Token(kind, value, offset, end, children)`, `Dialect` enum (`BODY`, `INPUT`, `STRING`, `VALUE_GROUP`), `lex(source, dialect=Dialect.BODY) -> list[Token]`, and the standalone-line pass `strip_standalone_lines(tokens)` (kept here: it works on `TEXT` and `BLOCK` tokens before parsing). |
| `dynamic_prompt/parser.py` | The frozen, slotted tree nodes `Template(parts)`, `Text(raw)`, `Variable(name, offset)`, `Group(options, offset)`, `Assignment(name, value, occurrence, offset)` (Phase 2 adds `Conditional` and expression nodes here or in `expressions.py`), and the recursive-descent `Parser(tokens, source)` → `Template`. One container loop shared by the body, options and string values; lenient group fallback in `BODY`, strict elsewhere; statement parsing for code blocks; option trimming; assignment occurrence numbering. |
| `dynamic_prompt/evaluator.py` | The evaluation runtime: `derive_seed(seed, *parts) -> int` (SHA-256 over a `\x1f`-joined UTF-8 key); `RandomStreams(seed)` with `body` (exactly `random.Random(seed)`), `for_assignment(name, occurrence)` and `for_input(name)`; `VariableTable` (`assign`, `lookup`, `__contains__`, plus `define_input(name, raw)`, which accepts only names matching `INPUT_VARIABLE` and raises `ValueError` otherwise — programmer error; `assign` refuses input names, defence in depth behind the parser check); and `Evaluator(streams, variables, source)` with `evaluate(template) -> str` in raw (still-escaped) output form, dispatching per node type. |

Six package files, split along phase boundaries (lex, parse, evaluate) plus the shared text rules and errors. An earlier draft used ten files; `Source`/`errors`, `tree`/`parser` and `variables`/`seeding`/`evaluator` were each edited together and each piece was tiny, so they were merged (architectural review, 2026-11-17).

### Pipeline

0. **Resolve inputs** (only when `inputs` is given). For each input (in mapping order; inputs are independent of each other, so order has no effect): build `Source(value)`, lex it in the `INPUT` dialect, parse it, evaluate it with `streams.for_input(name)`, and store the raw result with `VariableTable.define_input`. The `INPUT` dialect has no variables and no code: `$` and `<?` are plain text, so an input value is simply a v1 resolve (choices, escapes, comments, option trimming) and cannot fail. The body stream is not touched, so connecting inputs never changes the body's choices.
1. **Lex** (`lexer.py`). One left-to-right scan over the original text with a mode stack. `BODY` text yields `TEXT` (raw, merged across dropped comments, escape pairs kept as their two raw characters), `GROUP_OPEN`, `PIPE`, `GROUP_CLOSE`, `VARIABLE`, and `BLOCK` tokens. A `BLOCK` token's `children` are the code tokens between `<?` and `?>`: `VARIABLE`, `ASSIGN` (`=`), `SEPARATOR` (`;` or line break), `WORD` (bare identifier, used to recognise reserved keywords), `STRING` (whose `children` are `STRING`-dialect text tokens), and flat `GROUP_OPEN`/`PIPE`/`GROUP_CLOSE`/`TEXT`/`VARIABLE` tokens for an unquoted value group, which is lexed in the `VALUE_GROUP` dialect with depth tracking. Then `strip_standalone_lines` removes lines that consist only of blocks, comments and horizontal whitespace.
2. **Parse** (`parser.py`). Builds a `Template`. In `BODY`, an unclosed `{` becomes `Text("\\{")` (raw form, exactly as v1 emits) and parsing resumes at the next token; a stray `|` or `}` at the top level becomes text. Adjacent `Text` parts are merged. Each finished option is trimmed with `trim_layout` on its first and last `Text` part (identical to v1 trimming the raw option string, because raw text is preserved). Each `BLOCK` is parsed as a statement list; assignments are numbered per name in source order (`occurrence` starts at 1).
3. **Evaluate** (`evaluator.py`). `Text` → its raw string; `Variable` → table lookup or `UndefinedVariableError`; `Group` → `rng.choice(options)` then evaluate the chosen option with the same `rng`; `Assignment` → evaluate the value with `streams.for_assignment(name, occurrence)`, store the resulting raw string, output nothing. Body evaluation uses `streams.body`, which is exactly v1's `random.Random(seed)`, consumed in the same order.
4. **Finalise** (`text_rules.unescape_output`). One pass converts raw escapes to their characters — the same stage v1 has, extended with `\$` and `\<?`.

**Raw output form (invariant).** From lexing until the final pass, text is held in "raw output form": resolved, but with every escape still carrying its backslash. Variable values are stored in this form, interpolation inserts them unchanged (no re-parsing, no re-resolution), and the final pass runs exactly once. This is what makes v1 parity exact, including the double-backslash quirks. Phase 2 comparisons must compare `unescape_output(value)` on both sides; the grammar spec records this.

## Language Specification

This section is normative for all phases. Step 11 copies it into the living document `docs/agents/project-manifest/preprocessor-grammar.md`, which becomes the reference for Phase 2 and later work.

### 1. Lexical layers

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

### 2. Grammar (EBNF)

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

(* Phase 2 *)
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

### 3. Blocks

- `<?` opens a block anywhere in `BODY` text, including inside a group option. The block ends at the first `?>` that is not inside a string or a block comment.
- A block holds either a **statement list** (zero or more assignments separated by `;` or line breaks; an empty block is valid and outputs nothing) or exactly **one control statement** (Phase 2). Mixing both in one block is an error.
- A block never produces output. It is replaced by the empty string.

### 4. Assignment

- `$name = "template"` — a quoted string is a template: it may contain choices, `$vars` and escapes, and may span lines. Comments are not recognised inside strings.
- `$name = {a|b|c}` — an unquoted choice group is a value; its options follow body rules except where the `VALUE_GROUP` column above differs.
- Any other value (`$name = red`, `$name = $other`, single quotes) is an error with a hint to quote the value. `'` is reserved for a possible later literal-string form.
- An input variable name (`variable_0`, `variable_1`, …; see §11) is never a valid assignment target. Assigning to one is an error at parse time, whether or not that input is connected and whether or not the assignment would run.
- **Eager:** the value is resolved once, at the assignment, and stored as a string. Every later `$name` yields that same string. Reassignment replaces the value from that point on.
- **Scope:** one global table. A value is visible after its assignment in evaluation order. An assignment inside a group option runs only if that option is chosen.
- **Per-variable seeding:** each assignment draws from its own stream, `random.Random(derive_seed(seed, "assign", name, occurrence))`, where `occurrence` is the 1-based count of assignments to that name in source order. The body keeps v1's `random.Random(seed)`. Consequences: editing, adding or removing assignments never changes the choices made in the body, and never changes another variable's value; inserting an earlier assignment to the same name shifts the occurrence of the later ones.

### 5. Interpolation

- `$name` in `BODY`, `STRING` or `VALUE_GROUP` text inserts the stored value verbatim. The value is not parsed again, so `{`, `|` or `$` inside it are plain text.
- `$` not followed by an identifier start (`$5`, `$ `, a trailing `$`) is a literal dollar sign.
- An undefined `$name` is an error, in prompt text as well as in code. The message suggests `\$name` for a literal dollar sign.
- **Known boundary edge.** Escapes are decoded by one final pass over the whole output, so a stored value that ends in a lone backslash (for example an input value ending in `\`) combined with a directly following `|`, `{`, `}`, `$` or `<?` in the prompt forms an escape pair across the boundary and is unescaped. "Verbatim" therefore means "inserted without re-parsing"; the final pass still applies. This is a deliberate consequence of the raw output form, documented rather than special-cased.
- The name ends at the first non-identifier character. To glue text directly after a value, use a single-option group: `{$hair}ish`. A dedicated delimiter form (for example `${name}`) is a candidate for a later phase (see Phase Roadmap); it is not part of this grammar yet.

### 6. Conditions (Phase 2 — specified, not implemented)

- `<? if EXPR ?> … <? elseif EXPR ?> … <? else ?> … <? endif ?>`. Keyword terminators only; braces always mean choice.
- A conditional must open and close in the same container: the top level, one group option, or one branch. A `|` or `}` that would split it is an error ("`endif` missing before `|`").
- Only the chosen branch is evaluated. Its choices draw from the current stream (body or assignment), so a different branch can change later body choices for the same seed; this is deterministic and documented.
- Assignments inside an untaken branch do not run.
- Expression semantics: values are strings. `==` and `!=` compare `unescape_output` of both sides, case-sensitively. A bare operand is true when its value is non-empty. Precedence from high to low, as the grammar encodes it: parentheses, `==`/`!=`, `not`, `and`, `or` — so `not $a == "x"` means `not ($a == "x")`. `a == b == c` is an error. String literals in expressions may contain `$vars` and escapes, but a choice group inside one is an error. Undefined variables in expressions are errors (an existence helper is a later-phase candidate).
- Operators `&&`, `||`, `!` are not part of the language; Phase 2 reports them with a hint to use `and`, `or`, `not`.

### 7. Whitespace

- **Standalone lines:** a line (in the source, after comment removal) that contains at least one block and otherwise only spaces, tabs and comments disappears completely — leading spaces and tabs, the block(s), trailing spaces and tabs, and one line break (`\n` or `\r\n`). A block that ends the text with no line break after it removes only its own line content. Multi-line blocks count as one unit: the line where `<?` starts must have only horizontal whitespace before it, and the line where `?>` ends only horizontal whitespace (or comments) after it.
- A line containing only a comment keeps its line break, as in v1 (`a\n// note\nb` → `a\n\nb`).
- **Inline blocks** (sharing the line with other text or syntax) are replaced by the empty string; the surrounding spaces are kept.
- Option trimming (v1 multi-line option rule) applies after standalone lines are removed.

### 8. Comments

- Body and value-group text: v1 rules exactly. `/* … */` anywhere (unclosed `/*` stays literal); `//` at line start or after whitespace, up to but not including `\n`.
- Code: `//` anywhere, ending at the line break **or before `?>`** (so `<? $a = "x" // note ?>` works). `/* … */` anywhere; `?>` inside a block comment does not close the block; an unclosed `/*` in code is an error.
- Strings: no comments.

### 9. Escapes

- `\{`, `\}`, `\|` (v1), `\$` and `\<?` (new) produce the literal characters. Inside strings, `\"` produces `"`.
- Any other backslash pair is kept as written (v1). Escapes are decoded by the single final pass, so v1's double-backslash behaviour is preserved.
- There is no escape for a literal `?>` inside a code value; `?>` cannot appear in a value.

### 10. Errors

Code is strict; body text and input values are lenient. Every error is a `PromptError` (a `ValueError`) whose message starts with `Line N, column M:`, pointing at the start of the offending construct. Input values cannot raise prompt errors: their dialect has no code and no variables.

| Error | Phase | Raised for |
|---|---|---|
| Unclosed code block | 1 | `<?` without `?>` (points at `<?`) |
| Unclosed string | 1 | `"` without closing `"`, or `?>` / `<?` found inside a string |
| Unclosed choice group in a value | 1 | `{` without `}` in `STRING` or `VALUE_GROUP` |
| Unclosed comment in code | 1 | `/*` without `*/` inside a block |
| Invalid statement | 1 | missing `=`, missing value, unquoted word value, `$` without a name, single quotes, unexpected character, trailing tokens |
| Undefined variable | 1 | `$name` used before any assignment (body, string or value group), or `$variable_N` above the socket maximum |
| Assignment to input variable | 1 | `$variable_N = …` in a block: "`$variable_N` is a node input and cannot be assigned; use another name, e.g. `$hair = \"$variable_N\"`" (points at the `$`) |
| Unsupported keyword | 1 | `if`, `elseif`, `else`, `endif`, `and`, `or`, `not` in a block: "conditions are not supported yet" (replaced in Phase 2) |
| Mixed block | 2 | a control statement combined with other statements |
| Unbalanced conditional | 2 | `elseif`/`else`/`endif` without `if`, missing `endif`, `else` not last, conditional crossing a group boundary |
| Bad expression | 2 | operator without operand, unbalanced parentheses, chained comparison, choice in an expression string, `&&`/`\|\|`/`!` |

### 11. Input variables

- **Sockets.** The node has optional String sockets `variable_0` … `variable_19` (an `io.Autogrow` input named `variables`; a new slot appears as one is connected). They accept connections only, no widget. The upper bound is the named constant `MAX_INPUT_VARIABLES = 20` in `nodes.py`.
- **Names.** Every name matching `variable_(0|[1-9][0-9]*)` is reserved for inputs, so `$variable_0` always means the socket. Names with a leading zero (`variable_00`, `variable_01`) are ordinary names.
- **Unconnected is empty.** The node passes every slot from 0 to `MAX_INPUT_VARIABLES - 1`; an unconnected slot has the value `""`. Using it outputs nothing and is not an error. A number above the maximum (`$variable_20`) is undefined and raises an error. A direct call to `resolve_dynamic_prompt` without `inputs` defines no input variables.
- **Values are templates.** An input value is resolved with the v1 syntax only (`INPUT` dialect, §1): choices, nesting, option trimming, comments and escapes. `$` and `<?` are plain text, so a value loaded from a file containing `$word` or `<?` never fails and never refers to another input. It is resolved once, before the prompt, and every `$variable_N` in the prompt yields that same string (eager, like assignments). Cross-input references are not part of the grammar; they can be added later as a non-breaking opt-in (see Deferred Items).
- **Own random stream.** Each input draws from `random.Random(derive_seed(seed, "input", name))`. Editing the prompt never changes an input's pick, and connecting, disconnecting or changing an input never changes the body's choices or another input's pick.
- **Read-only.** The prompt cannot assign to an input variable (§4). To give an input a meaningful name, copy it: `<? $hair = "$variable_0" ?>`.
- **Raw output form.** A resolved input value is stored in raw output form like any variable; the single final pass unescapes the whole prompt.

## Rationale

- **Tokenizer → parser → tree → evaluator.** Blocks, strings and value groups are three nested languages with different comment and termination rules; a single character loop cannot host them without growing a flag per rule. Tokens carry offsets, so every error can name a line. A tree separates "what the prompt says" from "how it is resolved", which is exactly the seam Phase 2 needs (a `Conditional` node and expression nodes) and the later node-input phase needs (a pre-filled `VariableTable`).
- **Exact v1 parity through the raw output form.** Keeping escapes raw until one final pass, reusing the v1 regex constants verbatim, and running v1's `random.Random(seed)` in v1's order makes old prompts byte-identical — including quirks such as `\\|` → `\|` — without special cases. A frozen copy of the v1 resolver is used as a differential oracle, so parity is proven, not argued.
- **Comments in the lexer, emulating v1's pre-pass.** v1 strips comments before everything else. The lexer reproduces that by checking comments before escapes at each position, testing `//` against the original preceding character (regex `match(text, pos)` keeps the lookbehind on the original string), and, after a backslash, skipping closed block comments before pairing the backslash with the next character (`\/* c */{` → `\{`). This is what lets comments inside code end at `?>` while body comments behave exactly as before.
- **Per-assignment streams from SHA-256.** `hash()` is salted per process and therefore unusable; `hashlib` is stdlib and stable across Python versions and platforms. Keying by name and occurrence keeps each variable's pick stable when other header lines change.
- **Strict code, lenient text.** Code is written deliberately, so silent fallbacks hide mistakes; prompt text is often pasted and must keep v1's forgiving behaviour.
- **Reserved keywords now.** Rejecting `if`/`else`/… in Phase 1 means Phase 2 adds meaning to text that is currently an error, which is never a breaking change.
- **Input variables through Autogrow sockets.** Wiring a String output into a socket is how ComfyUI nodes normally share values, so the node stays focused and needs no knowledge of where a value comes from (a JSON node, a text loader, a string primitive). Autogrow shows only the sockets in use. `TemplatePrefix` gives 0-based names (`variable_0`, `variable_1`, …), the same numbering users know from other Autogrow nodes, with no name list to maintain.
- **Inputs resolved as templates with their own stream.** A file can hold a choice list (`"deep {crimson|navy}"`) and stay reusable across prompts. Per-input streams keep the v1 body stream untouched, so connected inputs never break parity or reshuffle the body.
- **Input dialect kept minimal (architectural review).** Externally loaded text is data: only choices, escapes and comments are interpreted. Making `$` and `<?` literal protects file-loaded text from failing on a stray `$word`, removes numeric input ordering, input labels and a second error form, and makes an input resolve identical to a v1 resolve (covered by the parity oracle). The reverse change, adding `$` interpolation later, is additive.
- **Unconnected is empty, inputs are read-only.** An empty string lets a prompt use a slot that is sometimes connected (and Phase 2's `<? if $variable_0 ?>` reads as "connected and not empty"). Read-only names guarantee that a connected value is used as given; the check is static (parser) so it fires even inside an option that was not chosen.
- **`inputs` keyword parameter, not a widget-level concern.** The resolver stays ComfyUI-free and testable: `nodes.py` turns the Autogrow dict into a complete `{variable_N: str}` mapping, and the resolver only sees plain strings.

## Considered Alternatives

| Decision | Chosen Shape | Alternatives Considered | Trade-Off Summary |
|---|---|---|---|
| Resolver architecture | Lexer → parser → tree → evaluator | (a) Extend the v1 scanner with flags; (b) textual macro pass that substitutes `$vars` before choice resolution | (a) cannot host three dialects or line-numbered errors without becoming unreadable; (b) re-parses values (a value containing `{` would become a choice) and cannot express eager per-variable seeding or conditionals. |
| Module granularity | Six files split by phase (errors, text rules, lexer, parser + tree, evaluator + runtime, facade) | Ten files (one class per module); one growing module | Tiny modules (`source`, `variables`, `seeding`, `tree`) were always edited with their neighbours and add import plumbing only; phase boundaries (lex, parse, evaluate) are the seams Phase 2 extends. |
| Input value dialect | `INPUT` = v1 syntax; `$` and `<?` literal | Full prompt syntax with `$variable_M` for lower inputs and strict errors | Externally loaded text should not fail on a stray `$word`; cross-input references are unrequested and cost numeric ordering, labels and a second error form. Adding `$` later is additive. |
| Code location | `dynamic_prompt/` package with relative imports | Single larger `dynamic_prompt.py`; separate package imported from a `dynamic_prompt.py` facade | One file reaches roughly 700 lines after Phase 2; a facade module cannot import a sibling package both as a top-level module (tests) and as a submodule (`nodes.py`). Turning the module into a package keeps both import paths with no shim. |
| Escape handling | Raw escapes until one final unescape pass | Decode escapes in the lexer | Lexer decoding is cleaner but changes v1 output for `\\|`, `\\}` and backslash-before-comment cases, breaking the parity requirement. |
| Comment handling | Lexer-integrated, mode-aware, v1-emulating | Keep the global regex pre-pass | The pre-pass cannot let `//` in code end at `?>`, would eat `//` inside strings, and shifts offsets so errors could not name the right line. |
| Seed derivation | `hashlib.sha256` over `seed`, scope, name, occurrence | `random.Random(f"{seed}:{name}")`; `hash()`; one shared stream | String seeding (`version=2`) is documented and stable, but hashlib makes the derived seed independent of any `random` policy for about five lines; `hash()` is salted per process; a shared stream would let header edits reshuffle the body, which the user rejected. |
| Assignment stream key | Name + per-name occurrence | Name only; source offset | Name only makes repeated assignments to one name correlated; an offset changes whenever any earlier text is edited, defeating stability. |
| Undefined `$name` in body text | Error | Leave `$name` literal | The user asked for strict errors; silent passthrough hides typos such as `$hiar`. `\$` gives an explicit literal. |
| Whitespace control | Standalone-line rule (as in Mustache) | Only drop the newline after `?>` (PHP); explicit trim markers such as `-?>` | PHP's rule leaves indentation behind; trim markers add syntax the user did not ask for. The standalone rule makes header blocks and future `if` lines vanish with no extra syntax. |
| Statement separation | `;` or line break | One statement per block | A header with five colours would need five blocks; multi-statement blocks are the natural header shape and match the user's PHP background. |
| Value forms | Quoted template or unquoted choice group only | Also bare `$other` and bare words | Kept to the agreed design; other forms give a helpful error. Bare `$other` was reconsidered for input renaming and rejected by the user (2026-11-17): `$color = "$variable_0"` makes explicit that the value becomes a string. |
| Error signalling | `PromptError(ValueError)` subclasses with line and column | Return an error string as the output; log and continue | ComfyUI already shows raised exceptions on the node; an error string would flow silently into the text encoder. |
| Parity verification | Frozen v1 oracle plus deterministic differential test | Hand-written cases only | Hand-written cases miss the combinatorial edges (escapes × comments × unclosed groups) that the oracle catches for free. |
| Grammar home | Plan section plus living doc `docs/agents/project-manifest/preprocessor-grammar.md` | Plan only | Plans are dated records; Phase 2 implementers need a maintained, normative reference. |
| Input sockets | `io.Autogrow` with `TemplatePrefix` `variable_0`…`variable_19`, `min=0` | (a) Fixed optional String inputs `input_a`…`input_d`; (b) `Autogrow.TemplateNames` with a generated `variable_1`-based name list; (c) one `JSON_OBJECT` input whose keys become variables | (a) fixed count and permanent clutter; (b) works around ComfyUI's 0-based numbering for no real gain — user decision: 0-based like other nodes; (c) rejected by the user: it would tie the node to `comfyui-json-nodes` and dilute its purpose, while wiring single string values is the normal ComfyUI way. |
| Input value semantics | Resolved as a template, own stream per input | Inserted as literal text | User decision: choice lists kept in files are the main use case; a literal value can still escape `\{`. |
| Unconnected slot | Empty string | Undefined (error on use) | User decision: a prompt keeps working when an optional source is unplugged; typos beyond the maximum still error. |
| Input precedence | Read-only, assignment is a parse-time error | Input overrides assignment; assignment acts as default | User decision: a connected input must be used as given; a static error is clearer than silent precedence rules. |
| Unconnected-slot filling | `nodes.py` builds the complete mapping for slots 0…max-1 | Resolver treats any unknown `variable_N` as empty | Keeping the slot count in the node means the resolver needs no ComfyUI knowledge, and a number above the socket count is still reported as a typo. |

## Pattern Alignment

- Follows: pure-Python resolver with no ComfyUI imports and stdlib only — `AGENTS.md` §3, `dynamic_prompt.py`.
- Follows: all randomness from `random.Random` seeded deterministically — `dynamic_prompt.py` L75.
- Follows: public entry point `resolve_dynamic_prompt(text, seed)` and the relative import in `nodes.py` L3.
- Follows: private module-level compiled regex constants and short docstrings — `dynamic_prompt.py` L9–L18 (moved verbatim into `dynamic_prompt/text_rules.py`).
- Follows: tests as `unittest.TestCase` classes with seed-range set assertions and the two-line `sys.path` setup — `tests/test_dynamic_prompt.py` L10–L13, L35–L47.
- Follows: changelog heading style of the sibling `../comfyui-json-nodes/changelog.md`.
- Follows: V3 `io.Autogrow` with `TemplatePrefix` and ComfyUI's 0-based slot numbering — companion skill `comfyui-node-advanced` SKILL.md L87–L115 and `skill_test_nodes/nodes_advanced.py` L75–L99 (`SkillTest_AutogrowPrefix`).
- Follows: values flow between nodes as single typed sockets (vanilla ComfyUI wiring); no cross-pack custom types.
- Departs: the resolver becomes a package instead of a single module. Justified by the multi-dialect pipeline and the Phase 2 growth; both existing import paths keep working.
- Follows: v1's one-cohesive-module granularity as far as the phases allow — six files grouped by phase, not one per class.
- Departs: `AGENTS.md` §3 "Vanilla parity … do not diverge further" and "not planned for 1.x". The user approved the preprocessor; step 12 rewrites both decisions so the new rule is "a strict superset of vanilla; prompts without `$` and `<?` resolve exactly as in 1.x".

## Structural Improvements

| Structure | Observation | Decision | Reason |
|---|---|---|---|
| `dynamic_prompt.py` (whole file) | Single character scanner; no tokens, positions or tree; cannot host code blocks or report lines | Promoted to steps 2–8 | Required by the feature; replacing it is the plan's core. |
| `dynamic_prompt.py` `_read_group` / `_resolve` | Backslash pairing duplicated in two loops | Promoted to step 5 | The lexer becomes the single place that understands backslashes. |
| `dynamic_prompt.py` `_COMMENTS` pre-pass | Global, mode-blind, offset-destroying | Promoted to step 5 | Comments move into the lexer, with v1 emulation, so code comments and line numbers work. |
| `dynamic_prompt.py` `_ESCAPES` final pass | Escapes split between scanning and a final regex (source of the `\\|` quirk) | Rejected (kept as a named stage `unescape_output`) | Unifying into the lexer would change v1 output; the stage is kept deliberately and documented as the raw-output-form invariant. |
| `nodes.py` description and `text` tooltip | Mention only `{a\|b\|c}` | Promoted to step 9 | `nodes.py` is now edited for the input sockets; the description and tooltip must mention variables and `$variable_N`. |
| `nodes.py` `execute(cls, text, seed)` | Positional-only parameters; no place for an optional dynamic input | Promoted to step 9 | Adds `variables=None` and builds the complete input mapping. |
| `tests/test_dynamic_prompt.py` `_load_package()` stub | No `io.Autogrow`; loading the new `nodes.py` would fail | Promoted to step 10 | Required for the node tests to keep running without ComfyUI. |
| `tests/test_dynamic_prompt.py::NodeTests.test_schema` | Unpacks exactly two inputs | Promoted to step 10 | Extend the unpacking to three inputs; existing assertions stay. |
| `tests/test_dynamic_prompt.py` path setup | Two-line `sys.path` idiom will repeat in each new test module | Rejected | Two lines per file are cheaper than a shared helper module that must itself be importable both ways. |
| `tests/` (no oracle) | v1 behaviour will only exist in git history once replaced | Promoted to step 1 | A frozen oracle turns the parity requirement into a test. |
| `pyproject.toml` L3 | `version = "1.1.0"` does not match `changelog.md` (v1.0.0) | Promoted to step 13 | The file is touched for 2.0.0 anyway; set it to `2.0.0`. |
| `README.md`, `docs/Mistralys_DynamicPromptText.md` compatibility text | Both claim the syntax "matches" vanilla with three differences | Promoted to step 13 | Becomes false; reworded as a superset. |
| `docs/agents/project-manifest/README.md` Data Flow and File Layout | Describe the regex pipeline and `dynamic_prompt.py` | Promoted to step 12 | Required by `AGENTS.md` §2 (file added/renamed, node inputs changed). |

## Detailed Steps

1. **Capture the v1 oracle (no dependencies; do this before any other step).** Copy `dynamic_prompt.py` byte-for-byte to the new file `tests/legacy_v1_resolver.py`, adding only a module docstring line stating it is a frozen copy of v1.0.0 used as a parity oracle and must never be edited. Location rationale: inside `tests/`, version-controlled, not matched by `test*.py`, so discovery does not collect it and no later step overwrites it.

2. **Create `dynamic_prompt/errors.py` (new).** `Source(text)` stores the text and a sorted list of newline offsets; `locate(offset) -> tuple[int, int]` returns 1-based line and column (`bisect_right`). `PromptError(ValueError)` takes `message, line, column`; `__str__` returns `Line {line}, column {column}: {message}`. Subclasses: `PromptSyntaxError`, `UndefinedVariableError` (extra `name` attribute). Add a `Source.error(cls, message, offset)` helper so call sites pass offsets, never line numbers.

3. **Create `dynamic_prompt/text_rules.py` (new).** Move the v1 constants verbatim: split `_COMMENTS` into `BLOCK_COMMENT` and `LINE_COMMENT` (same patterns), move `LEADING_LAYOUT`, `TRAILING_LAYOUT` and `trim_layout`. Add `IDENTIFIER` (start and continuation patterns), `INPUT_VARIABLE = re.compile(r"variable_(?:0|[1-9][0-9]*)")` with a helper `is_input_variable(name) -> bool` (`fullmatch`), `KEYWORDS = frozenset({"if", "elseif", "else", "endif", "and", "or", "not"})`, and `unescape_output(raw)` using `re.compile(r"\\([{}|$]|<\?)")` → `\1`.

4. **Create `dynamic_prompt/evaluator.py` with the runtime support classes (new file; step 7 adds `Evaluator` to the same file).** `derive_seed(seed, *parts)`: `int.from_bytes(hashlib.sha256("\x1f".join(map(str, (seed, *parts))).encode("utf-8")).digest(), "big")`. `RandomStreams(seed)`: `body = random.Random(seed)` created once; `for_assignment(name, occurrence)` returns a fresh `random.Random(derive_seed(seed, "assign", name, occurrence))`; `for_input(name)` returns a fresh `random.Random(derive_seed(seed, "input", name))`. `VariableTable()`: `define_input(name, raw)` (raises `ValueError` unless `is_input_variable(name)` - programmer error, not a prompt error), `assign(name, value)` (raises `ValueError` for an input name - defence in depth; the parser rejects it first), `lookup(name) -> str | None`, `__contains__`.

5. **Create `dynamic_prompt/lexer.py` (new).** Implement the token model and dialects from the Language Specification §1, §2, §8, §9:
   - `TokenKind`: `TEXT`, `GROUP_OPEN`, `PIPE`, `GROUP_CLOSE`, `VARIABLE`, `BLOCK`, `ASSIGN`, `SEPARATOR`, `WORD`, `STRING`. `Token` is a frozen slotted dataclass `(kind, value, offset, end, children=())`.
   - `BODY` scan order at each index (this order is what guarantees parity): closed `/* */` → skip; `//` matching `LINE_COMMENT.match(text, i)` (lookbehind sees the original text) → skip to before `\n`; backslash → skip any closed block comments that start right after it, then emit raw `\<?` if `<?` follows, otherwise the raw pair `\` + next character, or a lone `\` at end of text; `<?` → lex a block; `$` + identifier start → `VARIABLE`; `{` `|` `}` → structural tokens; anything else → text. Merge consecutive text into one `TEXT` token.
   - Block (code) mode: skip spaces and tabs; line break and `;` → `SEPARATOR`; `//` → skip to before the line break or `?>`; `/*` → skip to `*/` or raise "Unclosed comment"; `$name` → `VARIABLE` (bare `$` → error); `=` → `ASSIGN`; identifier → `WORD`; `"` → `STRING` with `STRING`-dialect children (no comments, `\"` decoded to `"` in the raw text, `<?`/`?>` → "Unclosed string" error pointing at the opening quote); `{` → `VALUE_GROUP` dialect with depth tracking, emitting flat tokens until the matching `}` (`<?`/`?>` or end of text → "Unclosed choice group" error); `?>` → close; end of text → "Unclosed code block" at `<?`; `'` → error "single quotes are reserved; use double quotes"; anything else → "Unexpected character".
   - `strip_standalone_lines(tokens)` on the top-level `BODY` token list (options are flat in it, so it covers blocks inside options): implement §7 exactly, operating on `TEXT` tokens adjacent to `BLOCK` tokens; drop `TEXT` tokens that become empty.
   - `INPUT` dialect: identical to `BODY` except that `$` and `<?` are ordinary text (no `VARIABLE` or `BLOCK` token is ever emitted; backslash pairing, comments and groups behave as in `BODY`) and `strip_standalone_lines` is skipped (there are no blocks). The result is exactly a v1 scan, so lexing an input value never raises.
   - `lex(source, dialect=Dialect.BODY)` returns the post-processed list; only `BODY` and `INPUT` are valid entry dialects.

6. **Create `dynamic_prompt/parser.py` (new), holding the tree nodes and the parser.**
   - Nodes (frozen, slotted, defined at the top of the module): `Text(raw)`, `Variable(name, offset)`, `Group(options: tuple[Template, ...], offset)`, `Assignment(name, value: Template | Group, occurrence, offset)`, `Template(parts: tuple)`.
   - `Parser` with one container method `_parse_template(tokens, start, stop_kinds, strict)` used for the body (`stop_kinds` empty), group options (`PIPE`, `GROUP_CLOSE`) and string children. Lenient group parsing in `BODY`: when a group reaches the end of its token list without `GROUP_CLOSE`, return a failure; the caller emits `Text("\\{")` and resumes right after the `GROUP_OPEN` token (reproduces v1, including `{a {b|c}` → `{a b`). Strict group parsing (value groups, strings): raise "Unclosed choice group" at the `{`. Top-level `PIPE`/`GROUP_CLOSE` → `Text("|")`/`Text("}")`. Merge adjacent `Text`. Trim each finished option with `trim_layout` on the first and last `Text` part.
   - Block parsing: split children on `SEPARATOR`; empty statements are skipped; a statement must be `VARIABLE ASSIGN (STRING | value group)`; a `WORD` in `KEYWORDS` → "conditions are not supported yet"; an assignment target for which `is_input_variable` is true → `PromptSyntaxError` "`$variable_N` is a node input and cannot be assigned" at the `$` (§4, §10); any other shape → "Invalid statement" with a hint. Assign `occurrence` from a per-parse `Counter` keyed by name in source order. Each assignment becomes an `Assignment` part of the enclosing template.
   - Keep the container loop and the block-statement dispatch as named methods (`_parse_block`, `_parse_statement`) so Phase 2 can add a `Conditional` node by extending them rather than rewriting the loop.

7. **Add `Evaluator` to `dynamic_prompt/evaluator.py` (created in step 4).** `Evaluator(streams, variables, source)` with `evaluate(template) -> str` and a per-node dispatch (`functools.singledispatchmethod` or an explicit type map; one method per node type). `Group` uses the `rng` passed down (body stream at the top level); `Assignment` evaluates its value with `streams.for_assignment(name, occurrence)` and stores the raw string; `Variable` raises `UndefinedVariableError` through `source` with the hint about `\$`. No `eval`, `exec` or `compile` anywhere in the package.

8. **Create `dynamic_prompt/__init__.py` and delete `dynamic_prompt.py`.** The facade: `resolve_dynamic_prompt(text, seed, *, inputs=None)` where `inputs` is `Mapping[str, str] | None`. It builds `RandomStreams(seed)` and an empty `VariableTable`; validates every `inputs` key with `is_input_variable` and every value as `str` (`ValueError`/`TypeError` otherwise — programmer errors); resolves the inputs (Pipeline step 0: `Source(value)`, `lex(..., Dialect.INPUT)`, parse, evaluate with `streams.for_input(name)`, `define_input`; order is irrelevant because inputs are independent); then builds the prompt `Source`, lexes, parses, evaluates with `streams.body`, and returns `unescape_output(raw)`. Module docstring describes the pipeline, the input dialect and the raw-output-form invariant (including the boundary edge in the grammar spec §5). `__all__ = ["resolve_dynamic_prompt", "PromptError", "PromptSyntaxError", "UndefinedVariableError", "INPUT_VARIABLE"]`. Delete the old `dynamic_prompt.py` in the same step so the package is the only import target. Do not modify the root `__init__.py`.

9. **Add the input sockets to `nodes.py`.** Add the module constant `MAX_INPUT_VARIABLES = 20`. In `define_schema`, append after `seed`: `io.Autogrow.Input("variables", optional=True, template=io.Autogrow.TemplatePrefix(input=io.String.Input("variable", tooltip="Text available in the prompt as $variable_N. Choices in it are resolved. Leave unconnected for an empty value."), prefix="variable_", min=0, max=MAX_INPUT_VARIABLES), tooltip=…)`. Change `execute` to `execute(cls, text, seed, variables=None)`: build `inputs = {f"variable_{i}": (connected.get(f"variable_{i}") or "") for i in range(MAX_INPUT_VARIABLES)}` from `connected = variables or {}`, so every slot `variable_0` … `variable_19` is present and unconnected ones are `""`; call `resolve_dynamic_prompt(text, seed, inputs=inputs)`. Keep the prefix `"variable_"` in one module constant (`INPUT_VARIABLE_PREFIX`) used by both methods. Update the node `description` to mention variables ("Resolves {a|b|c} choices and $variables on the server …") and the `text` tooltip to mention `<? $name = … ?>`, `$name` and `$variable_N`. Keep `text` and `seed` unchanged otherwise (`dynamic_prompts=False` stays).

10. **Write the tests** listed in the Test Plan (depends on steps 1–9; the parity tests depend on step 1). Extend the `comfy_api` stub in `tests/test_dynamic_prompt.py::_load_package()` with `io.Autogrow` (an `Input` class storing `id` and keyword arguments, and a `TemplatePrefix` class storing `input`, `prefix`, `min`, `max`), and extend `NodeTests.test_schema` to unpack three inputs (`text, seed, variables = schema.inputs`) while keeping its existing assertions. Run `python -m unittest discover -s tests -v`; every other v1 test in `tests/test_dynamic_prompt.py` must pass without modification. Exception identity: node tests run `nodes.py` through the stub-loaded `dynamic_prompt_pkg`, whose `dynamic_prompt_pkg.dynamic_prompt` is a second copy of the resolver package, so `PromptError` and `UndefinedVariableError` raised from `execute` are not the classes the test module imports at top level. `test_execute_propagates_prompt_error` must take the class from `sys.modules["dynamic_prompt_pkg.dynamic_prompt"]` (or assert `ValueError` plus the `Line N, column M:` prefix), never from the top-level import.

11. **Create the living grammar doc `docs/agents/project-manifest/preprocessor-grammar.md` (new).** Copy the Language Specification section of this plan, mark each subsection with its phase status (Phase 1: implemented; Phase 2: specified), and add a short "Implementation map" listing which module owns each rule.

12. **Update agent documentation.**
    - `AGENTS.md` §1: add the grammar doc row. §3: change "Resolver is pure Python in `dynamic_prompt.py`" to the `dynamic_prompt/` package (lexer → parser → tree → evaluator, relative imports only, no `eval`); replace the vanilla-parity bullet with "Strict superset of vanilla: prompts without `$` and `<?` resolve exactly as in 1.x (proven by `tests/test_parity.py` against `tests/legacy_v1_resolver.py`); the three v1 deviations stay"; replace "Intentionally focused … not planned for 1.x" with "Preprocessor (`<? ?>` blocks, `$variables`; `if/else` next) is approved and specified in the grammar doc; weights, multi-select and wildcard files still need user approval"; add "Input variables: optional Autogrow String sockets `variable_0`…`variable_19` (`MAX_INPUT_VARIABLES` in `nodes.py`), resolved with the v1 syntax on their own streams (choices, escapes, comments; `$` and `<?` literal), empty when unconnected, read-only; no JSON-object or other multi-value inputs (user decision — values are wired as single strings, as in vanilla)", "Per-variable seeding via `hashlib`, never `hash()`" and "Raw output form until one final unescape pass". §4: mention the oracle file must never be edited.
    - `docs/agents/project-manifest/README.md`: Overview mentions variables and input variables; Inputs table adds `variables` (Autogrow, `variable_0`…`variable_19`, optional, connection-only); File Layout replaces `dynamic_prompt.py` with the package tree and adds `tests/legacy_v1_resolver.py`, the new test files and the grammar doc; Data Flow becomes `inputs → resolve each (v1 syntax, own stream) → variable table`, then `text → lex (dialects, comments, standalone lines) → parse (tree) → evaluate (body stream + per-assignment streams, variable table) → unescape → PROMPT`; Behaviour Rules add the variable, block, whitespace, escape and error rules and the parity statement.

13. **Update user documentation and release preparation.**
    - `README.md`: Features gains "Variables" (set a value once, reuse it everywhere); "Familiar syntax" reworded as a superset; new `### Variables` subsection under Supported Prompt Syntax with the colour example (header block, `$name = "deep {crimson|navy}"`, `$name = {red|blue}`, reuse in the body), eager semantics, per-variable seeding, standalone-line whitespace, comments in blocks, `\$`, `{$name}ish`, and the error behaviour; new `### Input Variables` subsection (sockets appear as you connect; example wiring a `Mistralys_JsonString` `VALUE` into `variable_0`; `<? $hair = "$variable_0" ?>` to name it; tip: right-click a socket → "Rename Slot" to label it on the node (display only — the prompt still uses `$variable_0`), combined with a naming line in the header block; choices in input values are resolved once and `$`/`<?` in them stay literal; unconnected is empty; inputs cannot be assigned); Escapes subsection adds `\$` and `\<?`; Compatibility section reworded as superset; new section "Upgrading to 2.0" explaining that `$word` now means a variable (use `\$`) and that `\$` and `\<?` are new escapes; a short "Coming next" note pointing to `if/elseif/else/endif`.
    - `docs/Mistralys_DynamicPromptText.md`: Inputs list adds `variable_0`, `variable_1`, … (optional, connect a string; available as `$variable_N`; tip: "Rename Slot" labels a socket on the node, the variable name stays `$variable_N`, and `<? $hair = "$variable_0" ?>` gives it a name in the prompt); Syntax table rows for `$variable_N` and for `<? $name = "…" ?>`, `<? $name = {a\|b} ?>`, `$name`, `\$`, `\<?`; a three-line variables example; one sentence on standalone lines and errors; Compatibility paragraph reworded.
    - `changelog.md`: insert above v1.0.0 a heading `## v2.0.0 - **WIP; UNRELEASED**` with bullets: added `<? ?>` code blocks with variable assignment; added `$name` interpolation in prompt text; added optional `variable_0`, `variable_1`, … string inputs available as read-only `$variable_N`, with choices resolved; values are resolved once with per-variable seeding; added `\$` and `\<?` escapes; strict, line-numbered errors in code; new parser architecture; breaking: `$word` in existing prompts is now a variable reference.
    - `pyproject.toml`: `version = "2.0.0"`.

## Dependencies

- Step 1 has no dependencies and must run first; steps 8 and 10 depend on it (step 8 deletes the file it copies; `tests/test_parity.py` consumes it).
- Steps 2 and 3 are independent of each other and depend only on step 1 having run. Step 4 depends on step 3 (`VariableTable.define_input` and `assign` use `is_input_variable` from `text_rules.py`).
- Step 5 depends on 2 and 3. Step 6 depends on 2, 3 and 5. Step 7 depends on 2, 4 and 6 (steps 4 and 7 edit the same file, `evaluator.py`, so they run in that order). Step 8 depends on 1–7. Step 9 depends on 8. Step 10 depends on 1–9.
- Step 11 depends on nothing but the plan; steps 12 and 13 depend on 9 (final file layout and node inputs) and 11 (grammar doc path).

## Required Components

- New: `dynamic_prompt/__init__.py`, `dynamic_prompt/errors.py`, `dynamic_prompt/text_rules.py`, `dynamic_prompt/lexer.py`, `dynamic_prompt/parser.py`, `dynamic_prompt/evaluator.py`
- Removed: `dynamic_prompt.py`
- New tests: `tests/legacy_v1_resolver.py`, `tests/test_parity.py`, `tests/test_lexer.py`, `tests/test_variables.py`, `tests/test_whitespace.py`, `tests/test_errors.py`, `tests/test_seeding.py`, `tests/test_inputs.py`, `tests/test_package_hygiene.py`
- Modified test: `tests/test_dynamic_prompt.py` (`io.Autogrow` stub, `test_schema` unpacks three inputs, added node tests)
- New doc: `docs/agents/project-manifest/preprocessor-grammar.md`
- Modified docs and metadata: `AGENTS.md`, `docs/agents/project-manifest/README.md`, `README.md`, `docs/Mistralys_DynamicPromptText.md`, `changelog.md`, `pyproject.toml`
- Modified: `nodes.py` (Autogrow `variables` input, `MAX_INPUT_VARIABLES`, `execute` signature, description and tooltip)
- Unchanged (verify): root `__init__.py`

## Assumptions

- The parity guarantee covers prompts that contain neither `$` nor `<?`. This is slightly narrower than "neither `<?` nor `$name`": `\$` is a new escape, so `price \$5` now gives `price $5`, and a contrived raw `\\` immediately followed by `$` can also differ. Both are 2.0.0 changes listed in the changelog. Prompts with `$` not followed by an identifier and not preceded by a backslash (`$5`, `a $ b`) are tested to stay unchanged.
- ComfyUI shows a `ValueError` raised from `execute` on the node, so no wrapping in `nodes.py` is needed (consistent with `nodes.py` having no error handling today).
- `comfy node publish` packages all git-tracked files, so the new `dynamic_prompt/` directory ships without packaging configuration (`pyproject.toml` has no include list).
- ASCII identifiers are sufficient for variable names.
- The user's ComfyUI supports `io.Autogrow` with `TemplatePrefix` (user confirmed 2026-11-17: current version, Autogrow nodes already in use). Behaviour of `min=0` and the `execute` dict shape follow upstream `comfy_api/latest/_io.py` (research brief).
- 20 input slots are enough for one prompt; the limit is one constant (`MAX_INPUT_VARIABLES`, upstream hard limit 100).

## Constraints

- Python 3.10+ only features; stdlib only; no ComfyUI imports in `dynamic_prompt/`; no `eval`, `exec` or `compile`.
- `resolve_dynamic_prompt(text, seed)` keeps working with two positional arguments; the only addition is the keyword-only `inputs`. The root `__init__.py` stays unchanged.
- The resolver never imports ComfyUI: Autogrow handling stays in `nodes.py`, which passes a plain `dict[str, str]`.
- Body randomness is exactly `random.Random(seed)` consumed in v1 order; input resolution never draws from it.
- No release: agents do not tag or publish (`AGENTS.md` §5).

## Out of Scope

- Phase 2 implementation: `if/elseif/else/endif`, expression parsing and evaluation, `Conditional` and expression nodes (specified above, seams prepared).
- Later phases: helper functions (for example `defined($x)`, case helpers), a delimiter form such as `${name}`, single-quoted literal strings, bare word values, a lazy re-pick variable syntax, an escape for literal `?>` inside values.
- Weights, multi-select and wildcard files (still require user approval per `AGENTS.md` §3).
- A `JSON_OBJECT` (or any other multi-value) input — rejected by the user; values are wired as single strings.
- Non-string input sockets (Int, Float, Boolean); connect them through a converter node.
- Using socket labels as variable names (user decision 2026-11-17: no workaround for ComfyUI's naming). "Rename Slot" labels exist only in the frontend and are not sent to the server; reading them via `io.Hidden.extra_pnginfo` (missing for API prompts, unreliable in subgraphs) or a frontend JS extension is rejected. Users label sockets with "Rename Slot" and name values in the prompt with `<? $name = "$variable_N" ?>`.

## Phase Roadmap

- **Phase 1 (this plan):** pipeline, blocks, assignments, interpolation, choices as values, per-variable seeding, standalone lines, comments in code, strict errors, reserved keywords, input variables (`variable_N` Autogrow sockets, resolved as templates, read-only).
- **Phase 2 (specified in §6 and §10):** add `if`/`elseif`/`else`/`endif` handling in `parser._parse_block` and the container loop (a `Conditional(branches, else_branch)` node; a branch is `(condition, Template)`), a new `dynamic_prompt/expressions.py` with a precedence-climbing parser over code tokens (the lexer gains `==`, `!=`, `(`, `)` tokens) and expression nodes, and evaluator methods for them. Replace the "not supported yet" error with the balanced-structure errors. Comparisons use `unescape_output` on both sides.
- **Later:** possible helpers and the open syntax candidates listed in Out of Scope, each needing user approval.

## Human Actions

| # | Action | When | Why an agent cannot do it |
|---|--------|------|---------------------------|
| 1 | Smoke-test the node in ComfyUI: one empty `variable_0` socket shows initially, a new socket appears on connect, a `Mistralys_JsonString` `VALUE` output resolves into `$variable_0`, and a workflow with nothing connected runs | After the run | Needs a running ComfyUI frontend; the test suite stubs `comfy_api`. |
| 2 | Review the WIP changelog entry, then tag `v2.0.0` to trigger `.github/workflows/publish.yml` | After the run | Releases are the user's decision and agents must not tag or publish (`AGENTS.md` §5). |

## Acceptance Criteria

- AC-01: For every prompt containing neither `$` nor `<?`, and every seed, `resolve_dynamic_prompt` returns exactly what the v1 resolver (`tests/legacy_v1_resolver.py`) returns, including the probed quirks (`\\|`, `\\{a|b}`, `\/* c */{a|b}`, `{x\/**/|y}`, `/*x*///y`, `a //x\r\nb`).
- AC-02: All 32 existing tests in `tests/test_dynamic_prompt.py` pass with their assertions unchanged (only `test_schema`'s unpacking is extended to three inputs); the root `__init__.py` is unchanged; `resolve_dynamic_prompt(text, seed)` still works with two arguments; `from dynamic_prompt import resolve_dynamic_prompt` and the package-relative import both work; `dynamic_prompt.py` no longer exists.
- AC-03: `<? $c = "deep {crimson|navy}" ?>` followed by `$c hair, $c dress` yields the same resolved colour in both places, and the value can be either option across seeds.
- AC-04: An unquoted group value `<? $c = {red|blue} ?>` works, including nested groups and multi-line options with v1 trimming.
- AC-05: String templates interpolate earlier variables (`"$a and $b"`), and an interpolated value containing `{`, `|` or `$` (via escapes) is inserted verbatim without being resolved again.
- AC-06: For a fixed seed, adding, removing or editing assignments does not change the choices made in the body text, and does not change the value of any other variable; reassigning a name yields an independent second pick.
- AC-07: The same text and seed always give the same output, including across processes (seed derivation uses `hashlib`, pinned by a golden value).
- AC-08: `\$name` produces a literal `$name`; `\<?` produces a literal `<?`; `$5`, `a $ b` and a trailing `$` stay literal; an undefined `$name` raises `UndefinedVariableError`.
- AC-09: A line holding only blocks, whitespace and comments disappears with its line break (LF and CRLF, single and multi-line blocks, several blocks on one line, block at end of text, block inside a multi-line group option); an inline block outputs nothing and keeps surrounding text; a comment-only line still keeps its line break.
- AC-10: Inside blocks, `//` comments end at a line break or before `?>`, `/* */` comments work and may contain `?>`; inside strings `//` and `/*` are plain text; several statements may be separated by `;` or line breaks; an empty block is valid.
- AC-11: Each Phase 1 error in Language Specification §10 raises a `PromptError` subclass (a `ValueError`) whose message starts with `Line N, column M:` pointing at the offending construct, and an error raised inside the node propagates from `DynamicPromptTextNode.execute`.
- AC-12: Body text stays lenient: an unclosed `{` in body text is still a literal brace, while an unclosed `{` inside a quoted or unquoted value raises an error.
- AC-13: `if`, `elseif`, `else`, `endif`, `and`, `or`, `not` inside a block raise a "not supported yet" `PromptSyntaxError`.
- AC-14: The `dynamic_prompt/` package imports only the standard library and its own modules, and contains no call to `eval`, `exec` or `compile`.
- AC-15: The Language Specification exists as `docs/agents/project-manifest/preprocessor-grammar.md`, and `AGENTS.md`, the project manifest, `README.md`, the help page, `changelog.md` (`## v2.0.0 - **WIP; UNRELEASED**`) and `pyproject.toml` (`2.0.0`) are updated as in steps 11–13, including the input sockets.
- AC-16: The node schema has a third input, an `io.Autogrow` input `variables` (optional) using `TemplatePrefix` with a String slot template, `prefix="variable_"`, `min=0` and `max=20` (slots `variable_0` … `variable_19`); `execute` accepts it as `variables=None`, and `text`/`seed` are unchanged.
- AC-17: A connected input's value is available as `$variable_N` in prompt text, strings and value groups; choices in it are resolved once and every use yields the same string; `$` and `<?` inside an input value stay literal text and never raise; an unconnected slot yields `""` without error; `$variable_20` is undefined.
- AC-18: Each input's pick depends only on the seed, its name and its own value: editing the prompt, or connecting/changing another input, does not change it; connecting inputs does not change the body's choices (a prompt without `$` and `<?` still equals the v1 oracle with inputs connected).
- AC-19: Assigning to `$variable_N` raises `PromptSyntaxError` at parse time (also inside an unchosen option, and also when the input is not connected); an input value is resolved with the v1 syntax only: `$name`, `$variable_M` and `<?` in it are plain text (a lone `$word` or `<?` is never an error and never refers to another input).

## Testing Strategy

Three layers. (1) **Differential parity**: a deterministic generator builds thousands of prompts from v1's special characters and compares the new resolver against the frozen v1 oracle over several seeds, plus a curated list of known quirks. (2) **Behavioural tests** through `resolve_dynamic_prompt` for variables, whitespace and errors, using the existing seed-range set-assertion pattern for randomness and exact strings for deterministic cases. (3) **Unit tests** for the lexer dialects and seed derivation, and a static hygiene check on the package source. All tests run without ComfyUI, as today.

## Test Plan

- `tests/test_parity.py::ParityTests.test_generated_prompts_match_v1` — `random.Random(20261117)` generates 3000 strings (length 0–40) over the alphabet `{ } | \ / * space \n \r \t a b < ? >`, discarding any containing `<?`; for seeds 0–4 each output equals `legacy_v1_resolver.resolve_dynamic_prompt` — AC-01.
- `tests/test_parity.py::ParityTests.test_known_quirks_match_v1` — the probed quirk cases plus every input from `tests/test_dynamic_prompt.py::ResolverTests`, across seeds 0–49 — AC-01.
- `tests/test_dynamic_prompt.py` (all existing tests unchanged; `test_schema` unpacking extended to three inputs) — AC-02.
- `tests/test_dynamic_prompt.py::NodeTests.test_schema_variables_input` (new) — third input is the Autogrow stub with id `variables`, `optional=True`, `TemplatePrefix` with `prefix="variable_"`, `min=0`, `max=20`, String slot template — AC-16.
- `tests/test_dynamic_prompt.py::NodeTests.test_execute_without_variables` (new) — `execute("{a|b}", 7)` and `execute("{a|b}", 7, variables={})` both equal `resolve("{a|b}", 7)` — AC-16, AC-18.
- `tests/test_dynamic_prompt.py::NodeTests.test_execute_with_variables` (new) — `execute("x $variable_1 $variable_0", 0, variables={"variable_1": "b"})` gives `x b ` (slot 0 unconnected → empty) — AC-16, AC-17.
- `tests/test_dynamic_prompt.py::NodeTests.test_execute_propagates_prompt_error` (new) — `execute("$missing", 0)` raises the package-loaded `UndefinedVariableError`, obtained as `sys.modules["dynamic_prompt_pkg.dynamic_prompt"].UndefinedVariableError` (not the top-level import: node tests load `nodes.py` through the stub-loaded `dynamic_prompt_pkg`, which holds a second copy of the resolver package, so its exception classes are distinct objects from the top-level `dynamic_prompt` ones); also asserts the message starts with `Line 1, column 1:` — AC-11, AC-02.
- `tests/test_package_hygiene.py::HygieneTests.test_old_module_removed` — `dynamic_prompt.py` does not exist and `dynamic_prompt/__init__.py` does — AC-02.
- `tests/test_package_hygiene.py::HygieneTests.test_stdlib_only_imports` — `ast` walk over every package file: absolute imports are in `sys.stdlib_module_names`, others are relative — AC-14.
- `tests/test_package_hygiene.py::HygieneTests.test_no_dynamic_code_execution` — `ast` walk finds no call to `eval`, `exec` or `compile` — AC-14.
- `tests/test_variables.py::AssignmentTests.test_string_value_is_reused` — colour example yields identical colour in both uses, both options reachable over seeds — AC-03.
- `tests/test_variables.py::AssignmentTests.test_group_value` / `test_nested_group_value` / `test_multiline_group_value_is_trimmed` — AC-04.
- `tests/test_variables.py::AssignmentTests.test_string_interpolates_earlier_variables` and `test_value_is_not_resolved_again` (value `"\{a\|b\}"` interpolated stays `{a|b}`) — AC-05.
- `tests/test_variables.py::AssignmentTests.test_reassignment_replaces_value` and `test_assignment_inside_unchosen_option_does_not_run` — AC-06, AC-05.
- `tests/test_variables.py::SeedingTests.test_header_edit_keeps_body_choices` — for seeds 0–49, body `{a|b|c} {d|e|f}` resolves the same with and without a header of assignments — AC-06.
- `tests/test_variables.py::SeedingTests.test_other_assignment_does_not_change_value` — `$hair` value equal with and without an added `$eyes` assignment before it, seeds 0–49 — AC-06.
- `tests/test_variables.py::SeedingTests.test_second_assignment_is_independent_pick` — over seeds, first and second picks of the same name are not always equal — AC-06.
- `tests/test_variables.py::SeedingTests.test_reproducible` — same text and seed twice → same output — AC-07.
- `tests/test_seeding.py::DeriveSeedTests.test_golden_value` (imports `derive_seed` from `dynamic_prompt.evaluator`) — `derive_seed(0, "assign", "hair", 1)` equals an integer constant pinned at implementation time (the integer is pinned, never a resolved prompt, because `rng.choice` sequences are not guaranteed across Python versions); `test_independent_of_hash_seed` runs a subprocess with `PYTHONHASHSEED=1` and `=2` and compares a resolved prompt with assignments — AC-07.
- `tests/test_variables.py::EscapeTests.test_escaped_dollar`, `test_escaped_block_open`, `test_dollar_without_name_is_literal` (`$5`, `a $ b`, trailing `$`) — AC-08.
- `tests/test_variables.py::StatementTests.test_semicolon_and_newline_separators`, `test_empty_block`, `test_line_comment_ends_at_block_close`, `test_block_comment_may_contain_close`, `test_comments_are_text_inside_strings` — AC-10.
- `tests/test_whitespace.py::StandaloneTests` — `test_single_line_block_vanishes`, `test_crlf`, `test_multiline_block_vanishes`, `test_two_blocks_on_one_line`, `test_block_at_end_without_newline`, `test_block_with_trailing_comment`, `test_block_inside_multiline_option`, `test_inline_block_keeps_surrounding_text`, `test_comment_only_line_keeps_newline` — AC-09.
- `tests/test_errors.py::ErrorTests` — one test per Phase 1 row in §10 (`test_unclosed_block`, `test_unclosed_string`, `test_close_inside_string`, `test_unclosed_value_group`, `test_unclosed_comment_in_code`, `test_missing_equals`, `test_unquoted_value`, `test_single_quotes`, `test_bare_dollar_in_code`, `test_trailing_tokens`, `test_undefined_variable_in_text`, `test_undefined_variable_in_string`), each asserting the exception class, `isinstance(..., ValueError)`, and exact `line`/`column` — AC-11.
- `tests/test_errors.py::ErrorTests.test_body_unclosed_brace_stays_lenient` and `test_value_unclosed_brace_is_strict` — AC-12.
- `tests/test_errors.py::ErrorTests.test_reserved_keywords` — each keyword raises "not supported yet" — AC-13.
- `tests/test_inputs.py::InputValueTests` — `test_input_is_interpolated` (prompt text, string and value group), `test_input_choices_resolved_once` (`{red|blue}` input used twice → same colour; both reachable over seeds 0–49), `test_empty_input_is_empty`, `test_unknown_input_number_is_undefined` (`$variable_20`), `test_input_escapes_and_comments` (`\{x\}` stays literal, `/* c */` removed), `test_input_lenient_unclosed_brace`, `test_input_dollar_and_block_open_are_literal` (`$price`, `$variable_0` and `<?` in an input value are inserted as written, no error), `test_input_trailing_backslash_boundary` (value ending in `\` followed by `|` in the prompt unescapes across the boundary, pinning the documented edge) — AC-17, AC-19, AC-08.
- `tests/test_inputs.py::InputSeedingTests` — `test_prompt_edit_keeps_input_pick`, `test_other_input_keeps_input_pick`, `test_inputs_do_not_change_body_choices` (seeds 0–49, `{a|b|c} {d|e|f}` with and without inputs), `test_parity_with_inputs_connected` (generated parity prompts from `test_parity.py`'s generator subset, inputs `{x|y}` connected, equal to v1 oracle) — AC-18, AC-01.
- `tests/test_inputs.py::InputErrorTests` — `test_assign_to_input_is_error` (with and without the input, inside an unchosen option, exact line/column), `test_invalid_input_name_raises_value_error` (`inputs={"foo": "x"}` and `{"variable_01": "x"}`), `test_non_string_input_raises_type_error` — AC-19, AC-11.
- `tests/test_seeding.py::DeriveSeedTests.test_input_stream_golden_value` — `derive_seed(0, "input", "variable_0")` pinned — AC-07, AC-18.
- `tests/test_lexer.py::LexerTests` — token kinds and offsets for: body text with escapes kept raw, backslash before block comment, `//` lookbehind on original text, block children, string children with `\"`, value-group flattening, merged text across comments, `INPUT` dialect lexing `$name` and `<?` as plain `TEXT` (no `VARIABLE` or `BLOCK` token) while still pairing `\<?` as a raw escape — supports AC-01, AC-10, AC-19.
- Documentation (AC-15) is verified by review against steps 11–13; no automated test.

## Documentation Updates

- `docs/agents/project-manifest/preprocessor-grammar.md` (new) — normative grammar with phase status and implementation map.
- `AGENTS.md` — §1 grammar doc row; §3 package architecture, superset parity rule, approved preprocessor and input variables (Autogrow `variable_N` String sockets only; no JSON-object or multi-value inputs), hashlib seeding, raw-output-form invariant; §4 oracle note.
- `docs/agents/project-manifest/README.md` — Overview, node inputs (`variables` Autogrow, `variable_0`…`variable_19`), File Layout (package, new tests, oracle, grammar doc), Data Flow (inputs resolved first on their own streams), Behaviour Rules (input variables).
- `README.md` — Features (also "Input variables"), Variables subsection, new "Input Variables" subsection (wiring a `Mistralys_JsonString` `VALUE` into `variable_0`, naming via `<? $hair = "$variable_0" ?>`, "Rename Slot" tip (label is display-only), choices resolved with `$` and `<?` literal, empty when unconnected, read-only), Escapes, Compatibility (superset), "Upgrading to 2.0", "Coming next".
- `docs/Mistralys_DynamicPromptText.md` — Inputs list gains `variable_0`, `variable_1`, … with the "Rename Slot" tip; Syntax table rows (including `$variable_N`), example, standalone/error note, Compatibility.
- `changelog.md` — `## v2.0.0 - **WIP; UNRELEASED**` entry including input variables and the breaking change.
- `pyproject.toml` — `version = "2.0.0"`.

## Deferred Items

| # | Deferred Item | Origin | Reason Deferred | Notes |
|---|---------------|--------|-----------------|-------|
| 1 | Cross-input references (`$variable_M` usable inside a lower-numbered input value) and `$name` interpolation in input values | Architectural review of this plan, Decision 1 (2026-11-17) | No concrete use was named; it would add numeric input ordering, input labels and a second error form, and would make file-loaded text fail on a stray `$word`. | Additive and non-breaking if reintroduced as an opt-in. Reconsider only if the user names a concrete use. |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **Subtle v1 parity loss** (escapes, comment adjacency, trimming, rng order) | Frozen oracle and a 3000-prompt differential test over five seeds; v1 regexes moved verbatim; body stream identical to v1. |
| **Existing user prompts contain `$word`** (for example prices or shell-like text) | Major version 2.0.0; error message names the line and suggests `\$`; README "Upgrading to 2.0" section and changelog breaking-change bullet. |
| **Standalone-line logic leaves or eats wrong whitespace** | Precise spec (§7) and nine dedicated tests including CRLF, end of text, and blocks inside options; comment-only lines covered by a parity test. |
| **Runaway string or value group swallows the rest of the prompt** | `?>` and `<?` inside strings and value groups are errors pointing at the opening quote or brace. |
| **Seed derivation differs across Python versions or processes** | SHA-256 via `hashlib`; golden-value test and a subprocess test with different `PYTHONHASHSEED` values. |
| **Phase 2 forces a rewrite of Phase 1 structure** | Keywords reserved now; container loop and block dispatch are named extension points; grammar for Phase 2 fixed in the living doc; raw-output-form comparison rule recorded. |
| **Package import breaks in ComfyUI or tests** | Relative imports only inside the package; node tests load the repo as a package exactly as ComfyUI does; hygiene test asserts the old module is gone. |
| **Autogrow behaves differently in the frontend than upstream source suggests** (`min=0` slot display, dict shape) | `execute` tolerates `None`, missing keys and an empty dict; node tests cover all three; manual smoke test listed in Human Actions. |
| **An input value contains text that looks like syntax by accident** (a `$price` or `<?` in a loaded file) | The `INPUT` dialect treats `$` and `<?` as plain text, so such values never fail; only a closed `{a\|b}` is a choice, and `\{` escapes it. A value ending in a lone backslash can unescape across the boundary into the prompt text (documented in the grammar, pinned by a test). |
| **Quadratic backtracking on many unclosed `{`** | Same complexity as v1's `_read_group` rescans; prompts are short. Recorded, not optimised. |

## Recommended Workflow
- **Workflow:** ledger
- **Rationale:** A new multi-module parser package, a node schema change and a strict v1 parity requirement benefit from separate QA, code review and documentation stages.
