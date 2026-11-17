"""Evaluation runtime: seed derivation, random streams and the variable table."""
import hashlib
import random

from .errors import Source, UndefinedVariableError
from .parser import Assignment, Group, Template, Text, Variable
from .text_rules import is_input_variable

_KEY_SEPARATOR = "\x1f"


def derive_seed(seed, *parts):
    """Derive a stable integer seed from a base seed and key parts.

    SHA-256 keeps the result identical across processes and platforms (unlike hash()).
    """
    key = _KEY_SEPARATOR.join(str(part) for part in (seed, *parts))
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


class RandomStreams:
    """Independent random streams for the body, each assignment and each input variable."""

    def __init__(self, seed):
        self.seed = seed
        self.body = random.Random(seed)

    def for_assignment(self, name, occurrence):
        return random.Random(derive_seed(self.seed, "assign", name, occurrence))

    def for_input(self, name):
        return random.Random(derive_seed(self.seed, "input", name))


class VariableTable:
    """Variable values in raw output form. Input variables are defined once, never assigned."""

    def __init__(self):
        self._values = {}

    def assign(self, name, value):
        if is_input_variable(name):
            raise ValueError(f"{name} is an input variable and cannot be assigned")
        self._values[name] = value

    def define_input(self, name, value):
        if not is_input_variable(name):
            raise ValueError(f"{name} is not an input variable name")
        self._values[name] = value

    def lookup(self, name):
        return self._values.get(name)

    def __contains__(self, name):
        return name in self._values


class Evaluator:
    """Walks a Template and returns its text in raw (still-escaped) output form.

    Choices in the body draw from ``streams.body``; each assignment draws from its own stream, so
    editing assignments never changes the body's choices. Values are stored once, as strings, and
    inserted verbatim by later ``$name`` uses (never parsed or resolved again).
    """

    def __init__(self, streams, variables, source):
        self._streams = streams
        self._variables = variables
        self._source = source if isinstance(source, Source) else Source(source)

    def evaluate(self, template):
        """Evaluate a Template with the body stream and return the raw output text."""
        return self._eval(template, self._streams.body)

    def evaluate_with(self, template, rng):
        """Evaluate a Template drawing from the given stream (used for input values)."""
        return self._eval(template, rng)

    def _eval(self, node, rng):
        kind = type(node)
        if kind is Template:
            return "".join([self._eval(part, rng) for part in node.parts])
        if kind is Text:
            return node.raw
        if kind is Variable:
            return self._lookup(node)
        if kind is Group:
            return self._eval(rng.choice(node.options), rng)
        if kind is Assignment:
            stream = self._streams.for_assignment(node.name, node.occurrence)
            self._variables.assign(node.name, self._eval(node.value, stream))
            return ""
        raise TypeError(f"Cannot evaluate {kind.__name__}")

    def _lookup(self, node):
        if node.name not in self._variables:
            raise self._source.error(
                UndefinedVariableError,
                f"Undefined variable ${node.name}; assign it first, "
                f"or write \\${node.name} for a literal dollar sign",
                node.offset,
                name=node.name,
            )
        return self._variables.lookup(node.name)
