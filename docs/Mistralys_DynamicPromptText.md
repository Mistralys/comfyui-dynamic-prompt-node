# Dynamic Prompt Text

Resolves dynamic prompt choices on the server and outputs the final text.

## Inputs

- **text**: The prompt. Use `{a|b|c}` to pick one option per run. Groups can be nested.
- **seed**: Seed for the choices. The same text and seed always give the same result.

## Outputs

- **PROMPT**: The text with all choices resolved.

## Syntax

| Syntax | Meaning |
|---|---|
| `{a\|b\|c}` | Picks one of the options |
| `{a\|{b\|c}}` | Nested groups |
| `{\|a}` | An empty option (picks nothing or `a`) |
| `\{` `\}` `\|` | Literal brace or pipe |
| `// note` | Line comment, at line start or after whitespace |
| `/* note */` | Block comment, may span lines |

Options may be written on their own lines. Line breaks and indentation around an option are trimmed; spaces within a single line are kept (`{a |b}` keeps the space after `a`).

An unclosed `{` is kept as a literal brace.

## Compatibility

The syntax matches ComfyUI's built-in dynamic prompts, with three differences: `//` only starts a comment at the start of a line or after whitespace (so URLs stay intact), an unclosed `{` is a literal brace instead of a group running to the end of the text, and line breaks and indentation around an option are trimmed.
