"""Dynamic prompt resolver: turns a prompt template into one reproducible text.

Pipeline (each stage lives in its own module of this package):

1. ``errors.Source`` wraps the text so every error can name a line and column.
2. ``lexer.lex`` scans the text once into tokens (choices, ``$name`` references, ``<? ... ?>``
   blocks); comments are dropped here and ``lexer.strip_standalone_lines`` removes the layout
   around blocks that sit alone on their line.
3. ``parser.parse`` builds a tree of text, variables, choice groups and assignments.
4. ``evaluator.Evaluator`` walks the tree. Body choices draw from ``random.Random(seed)`` exactly
   as v1 did; every assignment draws from its own stream derived from the seed.
5. ``text_rules.unescape_output`` runs once over the result and turns escape pairs into literals.

Raw output form (invariant): from lexing until step 5, text is resolved but every escape still
carries its backslash. Variable values are stored in that form and inserted without being parsed
again, so the final pass runs exactly once. This keeps prompts without ``$`` or ``<?`` identical to
v1, including its double-backslash behaviour.

Pure Python with no ComfyUI imports, so it can be tested on its own.
"""
from .errors import PromptError, PromptSyntaxError, Source, UndefinedVariableError
from .evaluator import Evaluator, RandomStreams, VariableTable
from .lexer import Dialect, lex, strip_standalone_lines
from .parser import parse
from .text_rules import INPUT_VARIABLE, is_input_variable, unescape_output

__all__ = [
    "resolve_dynamic_prompt",
    "PromptError",
    "PromptSyntaxError",
    "UndefinedVariableError",
    "INPUT_VARIABLE",
]


def _resolve_inputs(inputs, streams, variables):
    """Pipeline step 0: resolve each input value on its own stream and define it as ``$variable_N``."""
    for name, value in inputs.items():
        if not isinstance(name, str) or not is_input_variable(name):
            raise ValueError(f"Invalid input name {name!r}; expected variable_0, variable_1, ... (no leading zeros)")
        if not isinstance(value, str):
            raise TypeError(f"Input {name} must be a string, got {type(value).__name__}")
    for name, value in inputs.items():
        source = Source(value)
        tree = parse(lex(value, Dialect.INPUT), source)
        variables.define_input(name, Evaluator(streams, variables, source).evaluate_with(tree, streams.for_input(name)))


def resolve_dynamic_prompt(text, seed, *, inputs=None):
    """Resolve all choices and variables in text. The same text and seed always give the same result.

    ``inputs`` maps ``variable_N`` names to string values (for example, text wired into a node
    socket). Each value is resolved once as a v1-syntax template on its own random stream, so
    connecting or changing an input never alters the body's choices or another input, and is then
    available read-only as ``$variable_N``. Names not in the mapping are undefined variables.
    Invalid names raise ValueError; non-string values raise TypeError.

    The ``INPUT`` dialect is v1 syntax only: choices ``{a|b}``, escapes and comments work, while
    ``$`` and ``<?`` are literal text, so externally loaded text containing ``$price`` never fails
    and resolves exactly as a v1 prompt would. An unclosed ``{`` stays a literal brace.

    Boundary edge: the resolved value is inserted in raw form (escapes keep their backslash) and
    the final unescape pass runs once over the whole result. A value ending in a lone backslash
    therefore combines with the prompt text that follows it: a trailing backslash followed by a
    ``|`` in the prompt unescapes to a literal ``|``.
    """
    source = Source(text)
    tree = parse(strip_standalone_lines(lex(text)), source)
    streams = RandomStreams(seed)
    variables = VariableTable()
    if inputs:
        _resolve_inputs(inputs, streams, variables)
    raw = Evaluator(streams, variables, source).evaluate(tree)
    return unescape_output(raw)
