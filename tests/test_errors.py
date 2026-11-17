"""Error behaviour: type, ValueError ancestry and exact line/column positions."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from dynamic_prompt import (  # noqa: E402
    PromptError,
    PromptSyntaxError,
    UndefinedVariableError,
    resolve_dynamic_prompt as resolve,
)


class ErrorTests(unittest.TestCase):
    def assertError(self, text, cls, line, column, contains=None):
        with self.assertRaises(cls) as caught:
            resolve(text, 0)
        error = caught.exception
        self.assertIsInstance(error, PromptError)
        self.assertIsInstance(error, ValueError)
        self.assertEqual((error.line, error.column), (line, column), str(error))
        self.assertTrue(str(error).startswith(f"Line {line}, column {column}: "), str(error))
        if contains:
            self.assertIn(contains, str(error))
        return error

    def test_unclosed_block(self):
        self.assertError('a\n  <? $x = "1"', PromptSyntaxError, 2, 3, "Unclosed code block")

    def test_unclosed_string(self):
        self.assertError('<? $a = "x ?>', PromptSyntaxError, 1, 9, "Unclosed string")

    def test_close_inside_string(self):
        self.assertError('<? $a = "x\n ?> y" ?>', PromptSyntaxError, 1, 9, "Unclosed string")

    def test_open_inside_string(self):
        self.assertError('<? $a = "x <? y" ?>', PromptSyntaxError, 1, 9, "Unclosed string")

    def test_unclosed_value_group(self):
        self.assertError('<? $a = {x ?>', PromptSyntaxError, 1, 9, "Unclosed choice group")

    def test_unclosed_group_in_string(self):
        self.assertError('<? $a = "{x" ?>', PromptSyntaxError, 1, 10, "Unclosed choice group")

    def test_unclosed_comment_in_code(self):
        self.assertError('<? $a /* x ?>', PromptSyntaxError, 1, 7, "Unclosed comment")

    def test_missing_equals(self):
        self.assertError('<? $a "x" ?>', PromptSyntaxError, 1, 7, "Invalid statement")

    def test_missing_value(self):
        self.assertError('<? $a = ?>', PromptSyntaxError, 1, 4, "Invalid statement")

    def test_unquoted_value(self):
        self.assertError('<? $a = red ?>', PromptSyntaxError, 1, 9, "not quoted")

    def test_bare_variable_value(self):
        self.assertError('<? $a = $b ?>', PromptSyntaxError, 1, 9, "Invalid statement")

    def test_single_quotes(self):
        self.assertError("<? $a = 'x' ?>", PromptSyntaxError, 1, 9, "Single quotes")

    def test_bare_dollar_in_code(self):
        self.assertError('<? $ = "x" ?>', PromptSyntaxError, 1, 4, 'variable name after "$"')

    def test_trailing_tokens(self):
        self.assertError('<? $a = "x" "y" ?>', PromptSyntaxError, 1, 13, "unexpected tokens")

    def test_unexpected_word(self):
        self.assertError("<? hello ?>", PromptSyntaxError, 1, 4, "Invalid statement")

    def test_undefined_variable_in_text(self):
        error = self.assertError("a\nb $missing", UndefinedVariableError, 2, 3, "\\$missing")
        self.assertEqual(error.name, "missing")

    def test_undefined_variable_in_string(self):
        self.assertError('<? $a = "x $nope" ?>', UndefinedVariableError, 1, 12, "Undefined variable $nope")

    def test_undefined_variable_in_value_group(self):
        self.assertError("<? $a = {x|$nope} ?>", UndefinedVariableError, 1, 12, "Undefined variable $nope")

    def test_variable_used_before_assignment(self):
        self.assertError('$a <? $a = "x" ?>', UndefinedVariableError, 1, 1)

    def test_undefined_input_style_name(self):
        self.assertError("$variable_20", UndefinedVariableError, 1, 1)

    def test_assignment_to_input_name_is_error(self):
        self.assertError('<? $variable_0 = "x" ?>', PromptSyntaxError, 1, 4, "node input")

    def test_reserved_keywords(self):
        for word in ("if", "elseif", "else", "endif", "and", "or", "not"):
            error = self.assertError(f"<? {word} ?>", PromptSyntaxError, 1, 4, "not supported yet")
            self.assertIn(f'"{word}"', str(error))

    def test_body_unclosed_brace_stays_lenient(self):
        self.assertEqual(resolve("a {b", 0), "a {b")
        self.assertEqual(resolve("a } | b", 0), "a } | b")

    def test_value_unclosed_brace_is_strict(self):
        self.assertError('<? $a = {x ?>', PromptSyntaxError, 1, 9)
        self.assertError('<? $a = "{x" ?>', PromptSyntaxError, 1, 10)


if __name__ == "__main__":
    unittest.main()
