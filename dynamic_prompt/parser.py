"""Parser and tree nodes for the prompt preprocessor.

The parser turns the flat token list of ``lexer.lex`` into a ``Template`` tree. Text stays in raw
output form (escapes keep their backslash); nothing is resolved here.

Group handling differs by context (see the dialect table in
docs/agents/project-manifest/preprocessor-grammar.md):

* Lenient (prompt text, input values): an unclosed ``{`` becomes the literal ``Text("\\\\{")`` and
  parsing resumes right after the brace, a stray ``|`` or ``}`` becomes text. This reproduces v1.
* Strict (strings and unquoted values in code): an unclosed ``{`` raises ``PromptSyntaxError``.

Pure Python with no ComfyUI imports.
"""
from collections import Counter
from dataclasses import dataclass

from .errors import PromptSyntaxError, Source
from .lexer import TokenKind
from .text_rules import KEYWORDS, LEADING_LAYOUT, TRAILING_LAYOUT, is_input_variable


# -- tree nodes -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Text:
    """Literal text in raw output form."""

    raw: str


@dataclass(frozen=True, slots=True)
class Variable:
    """A ``$name`` reference; offset is the position of the ``$`` in the source."""

    name: str
    offset: int


@dataclass(frozen=True, slots=True)
class Template:
    """A sequence of parts (Text, Variable, Group, Assignment) evaluated in order."""

    parts: tuple = ()


@dataclass(frozen=True, slots=True)
class Group:
    """A ``{a|b|c}`` choice; options are Templates, already trimmed."""

    options: tuple
    offset: int


@dataclass(frozen=True, slots=True)
class Assignment:
    """``$name = value``. value is a Template (quoted string) or a Group (unquoted choice).

    occurrence is the 1-based count of assignments to this name in source order; it keys the
    assignment's random stream.
    """

    name: str
    value: object
    occurrence: int
    offset: int


_NO_STOPS = frozenset()
_OPTION_STOPS = frozenset({TokenKind.PIPE, TokenKind.GROUP_CLOSE})

_VALUE_HINT = 'write assignments as $name = "value" or $name = {a|b}, and quote text values'


class Parser:
    """Recursive-descent parser. ``source`` is the prompt text or an errors.Source for it."""

    def __init__(self, tokens, source):
        self._tokens = tokens
        self._source = source if isinstance(source, Source) else Source(source)
        self._occurrences = Counter()
        self._unmatched_cache = {}

    def parse(self):
        """Parse the whole token list into a Template."""
        template, _ = self._parse_template(self._tokens, 0, _NO_STOPS, False)
        return template

    # -- errors --------------------------------------------------------------------------------

    def _error(self, message, offset):
        return self._source.error(PromptSyntaxError, message, offset)

    def _invalid(self, detail, offset):
        return self._error(f"Invalid statement: {detail}; {_VALUE_HINT}", offset)

    # -- container loop --------------------------------------------------------------------------

    def _parse_template(self, tokens, start, stop_kinds, strict):
        """Parse tokens from start until a token whose kind is in stop_kinds (not consumed) or the
        end of the list. Serves the prompt body, group options and string contents. Returns
        (Template, index of the stop token or len(tokens))."""
        parts = []
        i = start
        n = len(tokens)
        while i < n:
            tok = tokens[i]
            kind = tok.kind
            if kind in stop_kinds:
                break
            if kind is TokenKind.TEXT:
                self._add_text(parts, tok.value)
            elif kind is TokenKind.VARIABLE:
                parts.append(Variable(tok.value, tok.offset))
            elif kind is TokenKind.BLOCK:
                parts.extend(self._parse_block(tok))
            elif kind is TokenKind.GROUP_OPEN:
                if not strict and i in self._unmatched_opens(tokens):
                    self._add_text(parts, "\\{")
                else:
                    group, i = self._parse_group(tokens, i, strict)
                    parts.append(group)
                    continue
            elif kind is TokenKind.PIPE or kind is TokenKind.GROUP_CLOSE:
                # Not a stop here: a stray "|" or "}" is plain text.
                self._add_text(parts, tok.value)
            else:
                raise self._error(f"Unexpected {kind.value} in text", tok.offset)
            i += 1
        return Template(tuple(parts)), i

    @staticmethod
    def _add_text(parts, raw):
        """Append raw text, merging into a preceding Text part."""
        if not raw:
            return
        if parts and type(parts[-1]) is Text:
            parts[-1] = Text(parts[-1].raw + raw)
        else:
            parts.append(Text(raw))

    def _unmatched_opens(self, tokens):
        """Indices of GROUP_OPEN tokens that never close, as v1 decides it: a ``}`` closes the
        nearest open ``{``. Computed once per token list so lenient parsing never backtracks."""
        key = id(tokens)
        cached = self._unmatched_cache.get(key)
        if cached is None:
            stack = []
            for index, tok in enumerate(tokens):
                if tok.kind is TokenKind.GROUP_OPEN:
                    stack.append(index)
                elif tok.kind is TokenKind.GROUP_CLOSE and stack:
                    stack.pop()
            cached = frozenset(stack)
            self._unmatched_cache[key] = cached
        return cached

    # -- groups ----------------------------------------------------------------------------------

    def _parse_group(self, tokens, i, strict):
        """Parse the group whose GROUP_OPEN is tokens[i]. Returns (Group, index after its close).

        Callers in lenient mode only get here for a group that closes; an unclosed group in
        strict mode raises."""
        opener = tokens[i]
        options = []
        j = i + 1
        while True:
            template, j = self._parse_template(tokens, j, _OPTION_STOPS, strict)
            options.append(self._trim_option(template))
            if j >= len(tokens):
                raise self._error("Unclosed choice group: expected a closing }", opener.offset)
            closing = tokens[j].kind is TokenKind.GROUP_CLOSE
            j += 1
            if closing:
                return Group(tuple(options), opener.offset), j

    @staticmethod
    def _trim_option(template):
        """Apply v1's option trimming: layout with a line break is removed at the start of the
        first part and the end of the last part, when those are Text."""
        parts = list(template.parts)
        if parts and type(parts[0]) is Text:
            parts[0] = Text(LEADING_LAYOUT.sub("", parts[0].raw))
        if parts and type(parts[-1]) is Text:
            parts[-1] = Text(TRAILING_LAYOUT.sub("", parts[-1].raw))
        return Template(tuple(p for p in parts if type(p) is not Text or p.raw))

    # -- blocks and statements -------------------------------------------------------------------

    def _parse_block(self, block):
        """Parse a BLOCK token into the parts it contributes (Assignments; it never outputs text).

        Phase 2 extension point: a control statement block will return a Conditional here."""
        parts = []
        statement = []
        for tok in block.children:
            if tok.kind is TokenKind.SEPARATOR:
                if statement:
                    parts.append(self._parse_statement(statement))
                    statement = []
            else:
                statement.append(tok)
        if statement:
            parts.append(self._parse_statement(statement))
        return parts

    def _parse_statement(self, tokens):
        """Parse one non-empty statement (the tokens between separators) into an Assignment.

        Phase 2 extension point: control keywords will be dispatched here."""
        first = tokens[0]
        if first.kind is TokenKind.WORD:
            if first.value in KEYWORDS:
                raise self._error(
                    f'"{first.value}" is reserved: conditions are not supported yet', first.offset
                )
            raise self._invalid(f'unexpected word "{first.value}"', first.offset)
        if first.kind is not TokenKind.VARIABLE:
            raise self._invalid("a statement must start with a $variable", first.offset)

        if len(tokens) < 2 or tokens[1].kind is not TokenKind.ASSIGN:
            offset = first.offset if len(tokens) < 2 else tokens[1].offset
            raise self._invalid(f'expected "=" after ${first.value}', offset)

        name = first.value
        if is_input_variable(name):
            raise self._error(
                f'${name} is a node input and cannot be assigned; use another name, '
                f'e.g. $hair = "${name}"',
                first.offset,
            )

        if len(tokens) < 3:
            raise self._invalid(f"missing value after ${name} =", first.offset)

        value_tok = tokens[2]
        if value_tok.kind is TokenKind.STRING:
            value = self._parse_string(value_tok)
            end = 3
        elif value_tok.kind is TokenKind.GROUP_OPEN:
            value, end = self._parse_group(tokens, 2, True)
        elif value_tok.kind is TokenKind.WORD:
            raise self._invalid(
                f'the value "{value_tok.value}" is not quoted', value_tok.offset
            )
        elif value_tok.kind is TokenKind.VARIABLE:
            raise self._invalid(
                f'a bare ${value_tok.value} is not a value (write "${value_tok.value}" in quotes)',
                value_tok.offset,
            )
        else:
            raise self._invalid("the value must be a string or a choice group", value_tok.offset)

        if end < len(tokens):
            raise self._invalid("unexpected tokens after the value", tokens[end].offset)

        self._occurrences[name] += 1
        return Assignment(name, value, self._occurrences[name], first.offset)

    def _parse_string(self, token):
        template, _ = self._parse_template(token.children, 0, _NO_STOPS, True)
        return template


def parse(tokens, source):
    """Parse a token list from ``lexer.lex`` into a Template."""
    return Parser(tokens, source).parse()
