# ComfyUI Dynamic Prompt Node

Resolve dynamic prompts to plain text in your [ComfyUI](https://www.comfy.org/) workflow, reproducibly from a seed.

## Why Use It

ComfyUI's built-in dynamic prompts are resolved in the browser and end up hidden inside the conditioning signal. This node resolves `{a|b|c}` choices on the server and outputs the final text as a string, so you can see it, save it, and pass it on to other nodes.

## Features

- **Visible result** — the resolved prompt is a normal `STRING` output.
- **Reproducible** — the same text and seed always give the same result.
- **Works everywhere** — text arriving through a link, and workflows submitted through the API, are resolved too.
- **Familiar syntax** — the same as ComfyUI's built-in dynamic prompts: nested groups, backslash escapes, and `//` and `/* */` comments.
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

Use `\{`, `\}` and `\|` for literal characters. Other backslashes are left as they are.

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

### Compatibility with ComfyUI's Built-in Dynamic Prompts

The syntax matches ComfyUI's built-in dynamic prompts, with three deliberate improvements:

- `//` only starts a comment at the start of a line or after whitespace, so `https://example.com` stays intact. The built-in version cuts the text from any `//`.
- An unclosed `{` is kept as a literal brace. The built-in version treats the rest of the text as one group.
- Line breaks and indentation around an option are trimmed (see Multi-line Options). The built-in version keeps them in the output.

## Inputs and Outputs

| Name | Type | Description |
|---|---|---|
| `text` | input, string | The prompt, with optional `{a\|b}` groups |
| `seed` | input, int | Seed for the choices, with the usual *control after generate* setting |
| `PROMPT` | output, string | The resolved prompt |

The `text` widget does not use ComfyUI's browser-side dynamic prompts, because the browser must not resolve the text before the server does.

## Development

```bash
python -m unittest discover -s tests -v
```

The resolver in `dynamic_prompt.py` has no ComfyUI imports and can be used on its own.

## Upgrading from the Proof of Concept

The node ID changed to `Mistralys_DynamicPromptText`. Replace the old node in saved workflows.

## License

MIT

