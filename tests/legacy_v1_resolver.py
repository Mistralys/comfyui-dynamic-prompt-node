"""Dynamic prompt resolver: turns {a|b|c} choices into one reproducible text.

Supports nested groups, backslash escapes (\\{ \\} \\|) and // and /* */ comments.
Pure Python with no ComfyUI imports, so it can be tested on its own.
FROZEN COPY of the v1.0.0 resolver, used as a parity oracle in tests. Never edit this file.
"""
import random
import re

# A line comment must start the line or follow whitespace, so URLs ("https://") survive.
_COMMENTS = re.compile(r"/\*[\s\S]*?\*/|(?<!\S)//.*")
_ESCAPES = re.compile(r"\\([{}|])")
# Whitespace around an option is only trimmed when it contains a line break, so {a |b} keeps its space.
_LEADING_LAYOUT = re.compile(r"\A[ \t\r]*\n\s*")
_TRAILING_LAYOUT = re.compile(r"\s*\n[ \t\r]*\Z")


def _trim_layout(option):
    return _TRAILING_LAYOUT.sub("", _LEADING_LAYOUT.sub("", option))


def _read_group(text, i):
    """Read the options of a group whose opening brace precedes index i.

    Returns (options, index after the closing brace), or None if the group is never closed.
    """
    options, choice, depth = [], [], 0
    n = len(text)
    while i < n:
        c = text[i]
        i += 1
        if c == "\\" and i < n:
            choice.append(c + text[i])
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                options.append("".join(choice))
                return options, i
            depth -= 1
        elif c == "|" and depth == 0:
            options.append("".join(choice))
            choice = []
            continue
        choice.append(c)
    return None


def _resolve(text, rng):
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        i += 1
        if ch == "\\" and i < n:
            out.append(ch + text[i])
            i += 1
        elif ch == "{":
            group = _read_group(text, i)
            if group is None:
                # Unclosed brace: keep it as a literal and carry on after it.
                out.append("\\{")
                continue
            options, i = group
            out.append(_resolve(_trim_layout(rng.choice(options)), rng))
        else:
            out.append(ch)
    return "".join(out)


def resolve_dynamic_prompt(text, seed):
    """Resolve all groups in text. The same text and seed always give the same result."""
    rng = random.Random(seed)
    resolved = _resolve(_COMMENTS.sub("", text), rng)
    return _ESCAPES.sub(r"\1", resolved)
