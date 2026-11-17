"""Line-numbered error types for the prompt preprocessor."""
from bisect import bisect_right


class PromptError(ValueError):
    """Base class for all prompt errors; carries the 1-based line and column."""

    def __init__(self, message, line, column):
        super().__init__(message, line, column)
        self.message = message
        self.line = line
        self.column = column

    def __str__(self):
        return f"Line {self.line}, column {self.column}: {self.message}"


class PromptSyntaxError(PromptError):
    """The prompt text is malformed."""


class UndefinedVariableError(PromptError):
    """A variable was used before it was assigned (or never defined)."""

    def __init__(self, message, line, column, name):
        super().__init__(message, line, column)
        self.name = name


class Source:
    """Prompt text plus offset-to-position lookup, used to build errors."""

    def __init__(self, text):
        self.text = text
        self._newlines = [i for i, ch in enumerate(text) if ch == "\n"]

    def locate(self, offset):
        """Return the 1-based (line, column) of a character offset."""
        # Newlines strictly before the offset; a newline at the offset itself ends the previous line.
        before = bisect_right(self._newlines, offset - 1)
        line_start = self._newlines[before - 1] + 1 if before else 0
        return before + 1, offset - line_start + 1

    def error(self, cls, message, offset, **extra):
        """Build an error of class cls positioned at offset. Extra keywords go to the constructor."""
        line, column = self.locate(offset)
        return cls(message, line, column, **extra)
