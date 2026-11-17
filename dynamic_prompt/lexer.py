"""Mode-aware lexer for the prompt preprocessor.

One left-to-right scan over the original text turns a prompt into a flat token list. Four
dialects share one scanner (see the dialect table in docs/agents/project-manifest/preprocessor-grammar.md):

* ``BODY``        prompt text and group options.
* ``INPUT``       externally loaded input values: the v1 syntax only, so ``$`` and ``<?`` are text.
* ``STRING``      the inside of a ``"..."`` value in code (internal; no comments, ``\\"`` decoded).
* ``VALUE_GROUP`` an unquoted ``{...}`` value in code (internal; strict, depth tracked).

Escapes stay raw (a backslash and its character are kept as two characters) because the single
final pass ``unescape_output`` decodes them; this is what keeps v1's double-backslash behaviour.
Comments are removed here, in the order v1's global pre-pass would have removed them, so that
prompts without ``$`` or ``<?`` produce exactly the v1 text.

Pure Python with no ComfyUI imports.
"""
import re
from dataclasses import dataclass
from enum import Enum

from .errors import PromptSyntaxError, Source
from .text_rules import BLOCK_COMMENT, IDENTIFIER, LINE_COMMENT


class TokenKind(Enum):
    TEXT = "text"
    GROUP_OPEN = "group_open"
    PIPE = "pipe"
    GROUP_CLOSE = "group_close"
    VARIABLE = "variable"
    BLOCK = "block"
    ASSIGN = "assign"
    SEPARATOR = "separator"
    WORD = "word"
    STRING = "string"


class Dialect(Enum):
    BODY = "body"
    INPUT = "input"
    STRING = "string"
    VALUE_GROUP = "value_group"


@dataclass(frozen=True, slots=True)
class Token:
    """A lexed unit.

    value: raw text for TEXT (escapes kept, comments dropped, in STRING children ``\\"`` decoded);
        the identifier without ``$`` for VARIABLE and the identifier for WORD; the structural
        character for GROUP_OPEN, PIPE, GROUP_CLOSE, ASSIGN and SEPARATOR; the source slice for
        BLOCK and STRING.
    offset, end: half-open range in the original source (the text of a merged TEXT token may
        contain dropped comments, so ``end - offset`` can exceed ``len(value)``).
    children: code tokens of a BLOCK, or the content tokens of a STRING.
    """

    kind: TokenKind
    value: str
    offset: int
    end: int
    children: tuple = ()


# Runs of characters that never need individual attention, per dialect (a fast path only).
_PLAIN = {
    Dialect.BODY: re.compile(r"[^/\\{|}$<]+"),
    Dialect.INPUT: re.compile(r"[^/\\{|}]+"),
    Dialect.STRING: re.compile(r'[^\\{|}$<?"]+'),
    Dialect.VALUE_GROUP: re.compile(r"[^/\\{|}$<?]+"),
}

_STRUCTURAL = {
    "{": TokenKind.GROUP_OPEN,
    "|": TokenKind.PIPE,
    "}": TokenKind.GROUP_CLOSE,
}

_ENTRY_DIALECTS = (Dialect.BODY, Dialect.INPUT)


class _TextBuffer:
    """Collects consecutive text pieces (merged across dropped comments) into one TEXT token."""

    __slots__ = ("parts", "start", "end")

    def __init__(self):
        self.parts = []
        self.start = 0
        self.end = 0

    def add(self, value, start, end):
        if not self.parts:
            self.start = start
        self.parts.append(value)
        self.end = end

    def flush(self, tokens):
        if self.parts:
            tokens.append(Token(TokenKind.TEXT, "".join(self.parts), self.start, self.end))
            self.parts = []


class _Lexer:
    def __init__(self, source):
        self.source = source
        self._locator = Source(source)

    def _error(self, message, offset):
        return self._locator.error(PromptSyntaxError, message, offset)

    # -- v1-parity helpers -------------------------------------------------------------------

    def _comment_end(self, i):
        """Index after a v1 comment starting at i, or None. The line comment lookbehind sees the
        original preceding character, exactly as in v1's global pre-pass."""
        m = BLOCK_COMMENT.match(self.source, i) or LINE_COMMENT.match(self.source, i)
        return m.end() if m else None

    def _read_escape(self, i, decode_quote):
        """Read the escape that starts with the backslash at i. Returns (raw text, end index).

        Closed block comments right after the backslash are dropped first (v1 stripped comments
        before pairing), then the backslash pairs with the next character. ``\\<?`` is kept as
        three raw characters; a lone trailing backslash is a plain character.
        """
        src = self.source
        j = i + 1
        while src.startswith("/*", j):
            m = BLOCK_COMMENT.match(src, j)
            if m is None:
                break
            j = m.end()
        if j >= len(src):
            return "\\", j
        if src.startswith("<?", j):
            return "\\<?", j + 2
        if decode_quote and src[j] == '"':
            return '"', j + 1
        return "\\" + src[j], j + 1

    # -- text scanning (BODY, INPUT, STRING, VALUE_GROUP) -------------------------------------

    def _scan(self, i, dialect, opener):
        """Scan text-like content from i. Returns (tokens, index after the scanned region).

        BODY and INPUT run to the end of the text. STRING starts after its opening quote and ends
        after the closing quote. VALUE_GROUP starts at its ``{`` and ends after the matching
        ``}``. ``opener`` is the offset of the opening quote or brace, used for errors.
        """
        src = self.source
        n = len(src)
        plain = _PLAIN[dialect]
        tokens = []
        text = _TextBuffer()
        depth = 0
        while i < n:
            m = plain.match(src, i)
            if m:
                text.add(m.group(), i, m.end())
                i = m.end()
                continue
            c = src[i]
            if c == "/":
                end = self._comment_end(i)
                if end is None:
                    text.add(c, i, i + 1)
                    i += 1
                else:
                    i = end
            elif c == "\\":
                raw, end = self._read_escape(i, decode_quote=dialect is Dialect.STRING)
                text.add(raw, i, end)
                i = end
            elif c == "$":
                m = IDENTIFIER.match(src, i + 1)
                if m:
                    text.flush(tokens)
                    tokens.append(Token(TokenKind.VARIABLE, m.group(), i, m.end()))
                    i = m.end()
                else:
                    text.add(c, i, i + 1)
                    i += 1
            elif c == "<" and src.startswith("<?", i):
                if dialect is not Dialect.BODY:
                    raise self._unterminated(dialect, opener, "<?")
                text.flush(tokens)
                block = self._lex_block(i)
                tokens.append(block)
                i = block.end
            elif c == "?" and src.startswith("?>", i):
                raise self._unterminated(dialect, opener, "?>")
            elif c == '"' and dialect is Dialect.STRING:
                text.flush(tokens)
                return tokens, i + 1
            elif c in _STRUCTURAL:
                text.flush(tokens)
                tokens.append(Token(_STRUCTURAL[c], c, i, i + 1))
                i += 1
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if dialect is Dialect.VALUE_GROUP and depth == 0:
                        return tokens, i
            else:
                # "<" or "?" that does not start a marker.
                text.add(c, i, i + 1)
                i += 1
        if dialect is Dialect.STRING:
            raise self._error('Unclosed string: expected a closing " (strings may span lines)', opener)
        if dialect is Dialect.VALUE_GROUP:
            raise self._error("Unclosed choice group: expected a closing }", opener)
        text.flush(tokens)
        return tokens, n

    def _unterminated(self, dialect, opener, marker):
        if dialect is Dialect.STRING:
            return self._error(
                f'Unclosed string: found "{marker}" before the closing " (use \\{marker} for a literal)',
                opener,
            )
        return self._error(
            f'Unclosed choice group: found "{marker}" before the closing }} (use \\{marker} for a literal)',
            opener,
        )

    # -- code blocks ---------------------------------------------------------------------------

    def _lex_block(self, start):
        src = self.source
        n = len(src)
        children = []
        i = start + 2
        while i < n:
            c = src[i]
            if c in " \t\r":
                i += 1
            elif c == "\n" or c == ";":
                children.append(Token(TokenKind.SEPARATOR, c, i, i + 1))
                i += 1
            elif c == "?" and src.startswith("?>", i):
                end = i + 2
                return Token(TokenKind.BLOCK, src[start:end], start, end, tuple(children))
            elif c == "/" and src.startswith("//", i):
                i = self._code_line_comment_end(i)
            elif c == "/" and src.startswith("/*", i):
                close = src.find("*/", i + 2)
                if close < 0:
                    raise self._error("Unclosed comment: expected a closing */", i)
                i = close + 2
            elif c == "$":
                m = IDENTIFIER.match(src, i + 1)
                if m is None:
                    raise self._error('Expected a variable name after "$"', i)
                children.append(Token(TokenKind.VARIABLE, m.group(), i, m.end()))
                i = m.end()
            elif c == "=":
                children.append(Token(TokenKind.ASSIGN, c, i, i + 1))
                i += 1
            elif c == '"':
                content, end = self._scan(i + 1, Dialect.STRING, i)
                children.append(Token(TokenKind.STRING, src[i:end], i, end, tuple(content)))
                i = end
            elif c == "{":
                flat, i = self._scan(i, Dialect.VALUE_GROUP, i)
                children.extend(flat)
            elif c == "'":
                raise self._error("Single quotes are reserved; use double quotes", i)
            else:
                m = IDENTIFIER.match(src, i)
                if m is None:
                    raise self._error(f"Unexpected character {c!r}", i)
                children.append(Token(TokenKind.WORD, m.group(), i, m.end()))
                i = m.end()
        raise self._error('Unclosed code block: expected "?>"', start)

    def _code_line_comment_end(self, i):
        """A code line comment ends at the line break or right before the closing ?>."""
        src = self.source
        stops = [p for p in (src.find("\n", i), src.find("?>", i)) if p >= 0]
        return min(stops) if stops else len(src)


def lex(source, dialect=Dialect.BODY):
    """Tokenise source in the BODY or INPUT dialect and return a flat list of tokens.

    BODY raises PromptSyntaxError for malformed code blocks. INPUT never raises. The standalone
    line pass is separate (strip_standalone_lines) and applies to BODY token lists only.
    """
    if dialect not in _ENTRY_DIALECTS:
        raise ValueError(f"Cannot lex with entry dialect {dialect!r}; use Dialect.BODY or Dialect.INPUT")
    tokens, _ = _Lexer(source)._scan(0, dialect, None)
    return tokens


# -- standalone lines -------------------------------------------------------------------------

_LINE_PIECES = re.compile(r"[^\n]*\n|[^\n]+")
_BLANK_PIECE = re.compile(r"[ \t]*(?:\r?\n)?")


def strip_standalone_lines(tokens):
    """Remove the layout around blocks that sit alone on their line.

    Comments are already gone from the token text, so a block followed by a comment counts as
    alone on its line. The leading whitespace, the trailing whitespace and one line break
    (``\\n`` or ``\\r\\n``) disappear; the BLOCK tokens themselves are always kept, so every
    block still runs (it outputs nothing anyway). A multi-line block is one unit. Other lines,
    including comment-only lines, are untouched. Returns a new list; TEXT tokens that were split
    and rejoined get approximate offsets when they contained dropped comments.
    """
    if not any(t.kind is TokenKind.BLOCK for t in tokens):
        return list(tokens)

    lines = [[]]
    for tok in tokens:
        if tok.kind is not TokenKind.TEXT:
            lines[-1].append(tok)
            continue
        pos = 0
        for m in _LINE_PIECES.finditer(tok.value):
            piece = m.group()
            start = min(tok.offset + pos, tok.end)
            end = min(tok.offset + pos + len(piece), tok.end)
            lines[-1].append(Token(TokenKind.TEXT, piece, start, end))
            pos += len(piece)
            if piece.endswith("\n"):
                lines.append([])

    kept = []
    dropped_any = False
    for line in lines:
        if _is_standalone(line):
            # The blocks must survive (they still run); only the layout around them goes.
            dropped_any = True
            kept.extend(t for t in line if t.kind is TokenKind.BLOCK)
        else:
            kept.extend(line)
    if not dropped_any:
        return list(tokens)

    result = []
    for tok in kept:
        if tok.kind is TokenKind.TEXT and result and result[-1].kind is TokenKind.TEXT:
            prev = result[-1]
            result[-1] = Token(TokenKind.TEXT, prev.value + tok.value, prev.offset, tok.end)
        else:
            result.append(tok)
    return result


def _is_standalone(line):
    has_block = False
    for tok in line:
        if tok.kind is TokenKind.BLOCK:
            has_block = True
        elif tok.kind is not TokenKind.TEXT or _BLANK_PIECE.fullmatch(tok.value) is None:
            return False
    return has_block
