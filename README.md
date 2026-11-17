# ComfyUI Dynamic Prompt Node

Resolve dynamic prompts to plain text in your [ComfyUI](https://www.comfy.org/) workflow, reproducibly from a seed.

## Why Use It

ComfyUI's built-in dynamic prompts are resolved in the browser and end up hidden inside the conditioning signal. This node resolves `{a|b|c}` choices on the server and outputs the final text as a string, so you can see it, save it, and pass it on to other nodes.

## Features

- **Visible result** — the resolved prompt is a normal `STRING` output.
- **Reproducible** — the same text and seed always give the same result.
- **Works everywhere** — text arriving through a link, and workflows submitted through the API, are resolved too.
- **Familiar syntax** — a superset of ComfyUI's built-in dynamic prompts: nested groups, backslash escapes, and `//` and `/* */` comments work as you know them.
- **Variables** — assign a choice once in a `<? $name = ... ?>` block and reuse it with `$name`, so the same pick appears everywhere.
- **Input variables** — wire text from other nodes into the prompt as `$variable_0`, `$variable_1`, and so on.
- **No dependencies** — standard library and ComfyUI only.

## Requirements

- ComfyUI with V3 API support
- Python 3.10+

## Quick Start

Install it through the ComfyUI Manager, or clone the repository into ComfyUI's `custom_nodes` directory and restart ComfyUI:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/Mistralys/comfyui-dynamic-prompt-node.git
```

Then add **Dynamic Prompt Text** (category `utils`), type a prompt, and connect the `PROMPT` output to your text encoder or a *Preview as Text* node.

## Supported Prompt Syntax

### Option Lists

`{option1|option2|option3}` picks one option. Each run, the seed decides which one.

```
a portrait of a {red|blue|green} fox
```

### Nested Groups

```
a {small {red|blue}|large} fox
```

### Empty Options

`{|, wearing a hat}` either adds nothing or the text after the pipe.

### Escapes

Use `\{`, `\}` and `\|` for literal characters, `\$` for a literal `$` and `\<?` for a literal `<?`. Other backslashes are left as they are.

### Multi-line Options

Options can be laid out on their own lines. Line breaks and indentation around an option are trimmed, so this resolves to just one of the three texts:

```
{
    option one comes here
    |
    option two here
    |
    option three
}
```

Spaces are only trimmed when the option has a line break at that edge: `{a |b}` keeps the space after `a`. Line breaks inside an option are kept.

### Comments

```
// A line comment, at the start of a line or after whitespace
a fox /* block comment, may span lines */ in the snow
```

### Variables

Assign a variable in a `<? ... ?>` block and insert it anywhere with `$name`:

```
<? $color = "{red|blue|green}" ?>
a $color fox next to a $color door
```

Both `$color` uses give the same pick.

- **Eager.** The value is resolved once, where it is assigned, and every `$name` repeats that result. A variable can be assigned a quoted template (`"..."`) or a group (`{a|b}`).
- **Independent seeding.** Each variable draws from its own random stream derived from the seed and its name, so adding or removing a variable does not change the picks of the others.
- **Standalone lines.** A block alone on its line is removed together with the line break, so assignments at the top leave no blank lines in the output.
- **Comments.** `//` and `/* */` comments work inside blocks.
- **Literal `$`.** Write `\$` for a dollar sign and `\<?` for a literal `<?`.
- **Names end at the first non-name character**, so `{$name}ish` gives the value followed by `ish`.
- **Errors.** Using a variable that was never assigned, or a malformed block, raises an error that names the line and column.

### Input Variables

The node has an optional **variables** input. Connect a string to it and a new socket appears for the next one, up to 20. The sockets are numbered from 0 and available in the prompt as `$variable_0`, `$variable_1`, and so on:

```
a portrait of $variable_0, in the style of $variable_1
```

For example, wire a `Mistralys_JsonString` node into `variable_0` to feed a value from your JSON into the prompt.

- To give an input a meaningful name, copy it: `<? $hair = "$variable_0" ?>`, then use `$hair`. Right-click a socket and use "Rename Slot" to label it in the graph.
- Connected text is resolved once with the plain `{a|b|c}` syntax (choices, escapes, comments), and every use of the variable repeats that choice. `$` and `<?` inside it are ordinary text.
- A socket that is not connected is empty: `$variable_3` gives nothing and is not an error. A number above 19, such as `$variable_20`, is an undefined variable and raises an error.
- Input variables are read-only: `<? $variable_0 = "x" ?>` is an error.
- The sockets accept connections only, there is no text widget.

The full grammar is in `docs/agents/project-manifest/preprocessor-grammar.md`.

### Compatibility with ComfyUI's Built-in Dynamic Prompts

A prompt without `$` or `<?` resolves exactly as it would in ComfyUI's built-in dynamic prompts, apart from three deliberate improvements:

- `//` only starts a comment at the start of a line or after whitespace, so `https://example.com` stays intact. The built-in version cuts the text from any `//`.
- An unclosed `{` is kept as a literal brace. The built-in version treats the rest of the text as one group.
- Line breaks and indentation around an option are trimmed (see Multi-line Options). The built-in version keeps them in the output.

## Inputs and Outputs

| Name | Type | Description |
|---|---|---|
| `text` | input, string | The prompt, with optional `{a\|b}` groups, `<? $name = ... ?>` blocks and `$name` variables |
| `seed` | input, int | Seed for the choices, with the usual *control after generate* setting |
| `variables` | optional input, string sockets | Grows as you connect: `variable_0` to `variable_19`, read in the prompt as `$variable_N` |
| `PROMPT` | output, string | The resolved prompt |

The `text` widget does not use ComfyUI's browser-side dynamic prompts, because the browser must not resolve the text before the server does.

## Development

```bash
python -m unittest discover -s tests -v
```

The resolver in the `dynamic_prompt/` package has no ComfyUI imports and can be used on its own.

## Upgrading to 2.0

- `$word` now means a variable. A prompt that used a literal `$word` (for example a price) now raises an undefined-variable error: write `\$word` instead.
- `\$` and `\<?` are new escapes. Prompts that contain neither `$` nor `<?` resolve exactly as before.

## Coming Next

Conditional blocks with `if`, `elseif`, `else` and `endif` are planned for the preprocessor.

## Upgrading from the Proof of Concept

The node ID changed to `Mistralys_DynamicPromptText`. Replace the old node in saved workflows.

## License

MIT

