# Dynamic Prompt Text

Resolves dynamic prompt choices on the server and outputs the final text.

## Inputs

- **text**: The prompt. Use `{a|b|c}` to pick one option per run. Groups can be nested. Define variables with `<? $name = ... ?>` and insert them with `$name`.
- **seed**: Seed for the choices. The same text and seed always give the same result.
- **variable_0**, **variable_1**, ... (optional, under *variables*): Text sockets that grow as you connect them, up to 20. They are available in the prompt as `$variable_0`, `$variable_1`, ... (numbering starts at 0). Sockets accept connections only.

## Outputs

- **PROMPT**: The text with all choices resolved.

## Syntax

| Syntax | Meaning |
|---|---|
| `{a\|b\|c}` | Picks one of the options |
| `{a\|{b\|c}}` | Nested groups |
| `{\|a}` | An empty option (picks nothing or `a`) |
| `\{` `\}` `\|` | Literal brace or pipe |
| `<? $x = "{a\|b}" ?>` | Assigns a variable from a quoted template |
| `<? $x = {a\|b} ?>` | Assigns a variable from a group |
| `$x` | Inserts a variable |
| `$variable_0` | Inserts the text connected to socket 0 |
| `\$` `\<?` | Literal `$` or `<?` |
| `// note` | Line comment, at line start or after whitespace |
| `/* note */` | Block comment, may span lines |

Options may be written on their own lines. Line breaks and indentation around an option are trimmed; spaces within a single line are kept (`{a |b}` keeps the space after `a`).

An unclosed `{` is kept as a literal brace.

Example:

```
<? $color = "{red|blue}" ?>
a $color fox
and a $color door
```

A block alone on its line is removed together with the line break.

An undefined `$name` raises an error giving the line and column. An unconnected `$variable_N` (N below 20) is empty; `$variable_20` and above are undefined. Input variables are read-only, and connected text uses the plain `{a|b|c}` syntax only (`$` and `<?` in it are ordinary text).

## Compatibility

A prompt without `$` or `<?` resolves like ComfyUI's built-in dynamic prompts, with three differences: `//` only starts a comment at the start of a line or after whitespace (so URLs stay intact), an unclosed `{` is a literal brace instead of a group running to the end of the text, and line breaks and indentation around an option are trimmed.
