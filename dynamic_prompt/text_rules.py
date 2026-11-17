"""Text constants and helpers shared by the lexer, parser and evaluator.

The comment and layout rules are moved verbatim from the v1 resolver so parity is exact.
"""
import re

# A line comment must start the line or follow whitespace, so URLs ("https://") survive.
BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
LINE_COMMENT = re.compile(r"(?<!\S)//.*")
# Whitespace around an option is only trimmed when it contains a line break, so {a |b} keeps its space.
LEADING_LAYOUT = re.compile(r"\A[ \t\r]*\n\s*")
TRAILING_LAYOUT = re.compile(r"\s*\n[ \t\r]*\Z")

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# variable_0, variable_12: no leading zeros, so each socket has exactly one spelling.
INPUT_VARIABLE = re.compile(r"variable_(?:0|[1-9][0-9]*)")

KEYWORDS = frozenset({"if", "elseif", "else", "endif", "and", "or", "not"})

_OUTPUT_ESCAPES = re.compile(r"\\(\{|\}|\||\$|<\?)")


def trim_layout(option):
    return TRAILING_LAYOUT.sub("", LEADING_LAYOUT.sub("", option))


def is_input_variable(name):
    return INPUT_VARIABLE.fullmatch(name) is not None


def unescape_output(text):
    """The single final pass: turn escape pairs into literals, keep any other backslash pair."""
    return _OUTPUT_ESCAPES.sub(r"\1", text)
