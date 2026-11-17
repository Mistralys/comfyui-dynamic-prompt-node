"""Tests for the preprocessor foundation modules: errors, text rules, variable table."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _package_loader import load_submodule  # noqa: E402
import legacy_v1_resolver as v1  # noqa: E402

errors = load_submodule("errors")
rules = load_submodule("text_rules")
evaluator = load_submodule("evaluator")

Source = errors.Source
PromptError = errors.PromptError


class SourceLocateTests(unittest.TestCase):
    def test_text_start(self):
        self.assertEqual(Source("abc\ndef").locate(0), (1, 1))

    def test_mid_line(self):
        self.assertEqual(Source("abc\ndef").locate(2), (1, 3))

    def test_directly_after_newline(self):
        self.assertEqual(Source("abc\ndef").locate(4), (2, 1))

    def test_newline_character_belongs_to_its_line(self):
        self.assertEqual(Source("abc\ndef").locate(3), (1, 4))

    def test_after_crlf(self):
        self.assertEqual(Source("ab\r\ncd").locate(4), (2, 1))

    def test_end_of_text(self):
        self.assertEqual(Source("abc\ndef").locate(7), (2, 4))
        self.assertEqual(Source("").locate(0), (1, 1))

    def test_after_several_lines(self):
        self.assertEqual(Source("a\n\n\nbc").locate(5), (4, 2))


class ErrorTests(unittest.TestCase):
    def test_str_format(self):
        self.assertEqual(str(PromptError("m", 3, 7)), "Line 3, column 7: m")

    def test_attributes(self):
        error = PromptError("m", 3, 7)
        self.assertEqual((error.message, error.line, error.column), ("m", 3, 7))

    def test_hierarchy(self):
        for cls in (errors.PromptSyntaxError, errors.UndefinedVariableError):
            self.assertTrue(issubclass(cls, PromptError))
            self.assertTrue(issubclass(cls, ValueError))

    def test_undefined_variable_name(self):
        error = errors.UndefinedVariableError("m", 1, 2, "hair")
        self.assertEqual(error.name, "hair")
        self.assertEqual(str(error), "Line 1, column 2: m")

    def test_source_error_positions_error(self):
        error = Source("ab\ncd").error(errors.PromptSyntaxError, "bad", 4)
        self.assertIsInstance(error, errors.PromptSyntaxError)
        self.assertEqual((error.line, error.column), (2, 2))
        self.assertEqual(str(error), "Line 2, column 2: bad")

    def test_source_error_passes_extra_keywords(self):
        error = Source("$x").error(errors.UndefinedVariableError, "undefined", 0, name="x")
        self.assertEqual(error.name, "x")


class V1ParityTests(unittest.TestCase):
    SAMPLES = [
        "a red fox",
        "a /* c */ b",
        "a //x\r\nb",
        "a //x\nb",
        "https://example.com // trailing",
        "//start\nnext",
        "/* multi\nline */x",
        "a/*b*/c//d",
        "x//y",
    ]
    OPTIONS = ["a", "\n a \n", " a ", "\r\n\ta\r\n", "a\n", "\n\n", "  \n  x  \n  ", "a \nb"]

    def test_comments_match_v1(self):
        for text in self.SAMPLES:
            combined = re.compile(rules.BLOCK_COMMENT.pattern + "|" + rules.LINE_COMMENT.pattern)
            self.assertEqual(combined.sub("", text), v1._COMMENTS.sub("", text), repr(text))

    def test_combined_alternation_equals_v1_pattern(self):
        combined = rules.BLOCK_COMMENT.pattern + "|" + rules.LINE_COMMENT.pattern
        self.assertEqual(combined, v1._COMMENTS.pattern)

    def test_layout_patterns_match_v1(self):
        self.assertEqual(rules.LEADING_LAYOUT.pattern, v1._LEADING_LAYOUT.pattern)
        self.assertEqual(rules.TRAILING_LAYOUT.pattern, v1._TRAILING_LAYOUT.pattern)

    def test_trim_layout_matches_v1(self):
        for option in self.OPTIONS:
            self.assertEqual(rules.trim_layout(option), v1._trim_layout(option), repr(option))


class TextRulesTests(unittest.TestCase):
    def test_input_variable_names(self):
        for name in ("variable_0", "variable_12"):
            self.assertTrue(rules.is_input_variable(name), name)
        for name in ("variable_01", "variable_", "variable_a", "foo", "variable_1x", "xvariable_1"):
            self.assertFalse(rules.is_input_variable(name), name)

    def test_keywords(self):
        self.assertEqual(rules.KEYWORDS, {"if", "elseif", "else", "endif", "and", "or", "not"})

    def test_unescape_output_converts_escapes(self):
        self.assertEqual(rules.unescape_output("\\{ \\} \\| \\$ \\<?"), "{ } | $ <?")

    def test_unescape_output_keeps_other_pairs(self):
        self.assertEqual(rules.unescape_output("\\n \\a \\\\ \\<"), "\\n \\a \\\\ \\<")

    def test_unescape_output_matches_v1_for_v1_escapes(self):
        text = "a\\{b\\}c\\|d\\\\{e"
        self.assertEqual(rules.unescape_output(text), v1._ESCAPES.sub(r"\1", text))

    def test_identifier_full_matches(self):
        for name in ("hair", "_x", "hair_2", "A"):
            self.assertIsNotNone(rules.IDENTIFIER.fullmatch(name), name)
        for name in ("5a", "", "a-b", "a b"):
            self.assertIsNone(rules.IDENTIFIER.fullmatch(name), name)


class VariableTableTests(unittest.TestCase):
    def setUp(self):
        self.table = evaluator.VariableTable()

    def test_assign_and_lookup(self):
        self.table.assign("hair", "red")
        self.assertEqual(self.table.lookup("hair"), "red")
        self.assertIn("hair", self.table)

    def test_reassign_overwrites(self):
        self.table.assign("hair", "red")
        self.table.assign("hair", "blue")
        self.assertEqual(self.table.lookup("hair"), "blue")

    def test_unknown_name(self):
        self.assertIsNone(self.table.lookup("nope"))
        self.assertNotIn("nope", self.table)

    def test_empty_string_value_is_defined(self):
        self.table.assign("empty", "")
        self.assertEqual(self.table.lookup("empty"), "")
        self.assertIn("empty", self.table)

    def test_define_input(self):
        self.table.define_input("variable_0", "x")
        self.assertEqual(self.table.lookup("variable_0"), "x")
        self.assertIn("variable_0", self.table)

    def test_define_input_rejects_other_names(self):
        for name in ("hair", "variable_01"):
            with self.assertRaises(ValueError):
                self.table.define_input(name, "x")

    def test_assign_rejects_input_names(self):
        with self.assertRaises(ValueError):
            self.table.assign("variable_3", "x")


if __name__ == "__main__":
    unittest.main()
