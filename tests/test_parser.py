"""Tree-level tests for the parser: groups, lenient/strict handling, trimming, statements, errors."""
import dataclasses
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _package_loader import load_submodule  # noqa: E402

lexer = load_submodule("lexer")
errors = load_submodule("errors")
parser = load_submodule("parser")

Text = parser.Text
Variable = parser.Variable
Group = parser.Group
Assignment = parser.Assignment
Template = parser.Template
PromptSyntaxError = errors.PromptSyntaxError


def parse(source, dialect=lexer.Dialect.BODY):
    return parser.Parser(lexer.lex(source, dialect), source).parse()


def shape(node):
    """Compact nested representation for assertions."""
    if isinstance(node, Template):
        return [shape(p) for p in node.parts]
    if isinstance(node, Text):
        return node.raw
    if isinstance(node, Variable):
        return f"${node.name}"
    if isinstance(node, Group):
        return {"group": [shape(o) for o in node.options]}
    if isinstance(node, Assignment):
        return ("assign", node.name, shape(node.value), node.occurrence)
    raise AssertionError(node)


def error_of(source):
    with unittest.TestCase().assertRaises(PromptSyntaxError) as ctx:
        parse(source)
    return ctx.exception


class GroupTests(unittest.TestCase):
    def test_plain_group(self):
        tree = parse("{a|b}")
        self.assertEqual(len(tree.parts), 1)
        group = tree.parts[0]
        self.assertIsInstance(group, Group)
        self.assertEqual(len(group.options), 2)
        self.assertTrue(all(isinstance(o, Template) for o in group.options))
        self.assertEqual(shape(tree), [{"group": [["a"], ["b"]]}])

    def test_adjacent_text_is_merged(self):
        self.assertEqual(shape(parse("a /* c */ b")), ["a  b"])
        self.assertEqual(shape(parse("x{a|b}y")), ["x", {"group": [["a"], ["b"]]}, "y"])

    def test_empty_source_and_empty_option(self):
        self.assertEqual(shape(parse("")), [])
        self.assertEqual(shape(parse("{|a}")), [{"group": [[], ["a"]]}])

    def test_nested_group(self):
        self.assertEqual(
            shape(parse("{a|{b|c}}")), [{"group": [["a"], [{"group": [["b"], ["c"]]}]]}]
        )

    def test_multiline_option_is_trimmed(self):
        self.assertEqual(shape(parse("{\n  a\n|b}")), [{"group": [["a"], ["b"]]}])
        self.assertEqual(shape(parse("{\n  a  \n  |b}")), [{"group": [["a"], ["b"]]}])

    def test_single_line_option_keeps_spaces(self):
        self.assertEqual(shape(parse("{ a | b }")), [{"group": [[" a "], [" b "]]}])

    def test_trim_only_at_option_ends(self):
        self.assertEqual(shape(parse("{a\nb|c}")), [{"group": [["a\nb"], ["c"]]}])

    def test_group_offset(self):
        self.assertEqual(parse("xy{a}").parts[1].offset, 2)

    def test_escaped_braces_are_text(self):
        self.assertEqual(shape(parse("\\{a\\|b\\}")), ["\\{a\\|b\\}"])


class LenientTests(unittest.TestCase):
    def test_unclosed_brace_is_literal(self):
        self.assertEqual(shape(parse("{")), ["\\{"])
        self.assertEqual(shape(parse("{a")), ["\\{a"])

    def test_unclosed_brace_then_group_matches_v1(self):
        # v1 resolves "{a {b|c}" as a literal brace plus a group.
        tree = parse("{a {b|c}")
        self.assertEqual(shape(tree), ["\\{a ", {"group": [["b"], ["c"]]}])
        self.assertIsInstance(tree.parts[1], Group)

    def test_stray_pipe_and_close_are_text(self):
        self.assertEqual(shape(parse("a|b}c")), ["a|b}c"])

    def test_pipe_after_unclosed_brace_is_text(self):
        self.assertEqual(shape(parse("{a|b")), ["\\{a|b"])

    def test_closed_group_after_stray_close(self):
        self.assertEqual(shape(parse("}{a|b}")), ["}", {"group": [["a"], ["b"]]}])

    def test_many_unclosed_braces_do_not_blow_up(self):
        tree = parse("{" * 2000 + "x")
        self.assertEqual(shape(tree), ["\\{" * 2000 + "x"])

    def test_input_dialect_is_lenient(self):
        self.assertEqual(shape(parse("a {b", lexer.Dialect.INPUT)), ["a \\{b"])
        self.assertEqual(
            shape(parse("$x <? {a|b}", lexer.Dialect.INPUT)),
            ["$x <? ", {"group": [["a"], ["b"]]}],
        )


class StrictTests(unittest.TestCase):
    def test_unclosed_brace_in_string(self):
        err = error_of('<? $a = "x {b" ?>')
        self.assertIn("Unclosed choice group", err.message)
        self.assertEqual((err.line, err.column), (1, 12))

    def test_unclosed_brace_in_string_second_line(self):
        err = error_of('a\n<? $a = "x\n  {b" ?>')
        self.assertIn("Unclosed choice group", err.message)
        self.assertEqual((err.line, err.column), (3, 3))

    def test_unclosed_brace_in_unquoted_value(self):
        err = error_of("<? $a = {x|y ?>")
        self.assertIn("Unclosed choice group", err.message)
        self.assertEqual((err.line, err.column), (1, 9))

    def test_closed_group_in_string(self):
        tree = parse('<? $a = "x {b|c} y" ?>')
        self.assertEqual(
            shape(tree), [("assign", "a", ["x ", {"group": [["b"], ["c"]]}, " y"], 1)]
        )

    def test_stray_pipe_in_string_is_text(self):
        self.assertEqual(shape(parse('<? $a = "x|y}" ?>')), [("assign", "a", ["x|y}"], 1)])


class AssignmentTests(unittest.TestCase):
    def test_two_assignments(self):
        tree = parse('<? $a = "x"; $b = {p|q} ?>')
        self.assertEqual(len(tree.parts), 2)
        a, b = tree.parts
        self.assertIsInstance(a, Assignment)
        self.assertIsInstance(b, Assignment)
        self.assertEqual((a.name, b.name), ("a", "b"))
        self.assertIsInstance(a.value, Template)
        self.assertIsInstance(b.value, Group)
        self.assertEqual(shape(a.value), ["x"])
        self.assertEqual(shape(b.value), {"group": [["p"], ["q"]]})

    def test_line_break_separates_statements(self):
        tree = parse('<?\n$a = "x"\n$b = "y"\n?>')
        self.assertEqual([p.name for p in tree.parts], ["a", "b"])

    def test_empty_blocks_yield_no_part(self):
        self.assertEqual(parse("<??>").parts, ())
        self.assertEqual(parse("<?  ;\n ; ?>").parts, ())
        self.assertEqual(shape(parse("a<??>b")), ["ab"])

    def test_block_does_not_merge_text_across_assignment(self):
        self.assertEqual(shape(parse('a<? $x = "1" ?>b')), ["a", ("assign", "x", ["1"], 1), "b"])

    def test_occurrence_numbering(self):
        tree = parse('<? $a = "1"; $b = "2"; $a = "3" ?>')
        self.assertEqual([(p.name, p.occurrence) for p in tree.parts], [("a", 1), ("b", 1), ("a", 2)])

    def test_occurrence_counts_across_blocks_and_options(self):
        tree = parse('<? $a = "1" ?>{<? $a = "2" ?>x|<? $a = "3" ?>y}')
        group = tree.parts[1]
        self.assertEqual(tree.parts[0].occurrence, 1)
        self.assertEqual(group.options[0].parts[0].occurrence, 2)
        self.assertEqual(group.options[1].parts[0].occurrence, 3)

    def test_multiline_group_value_is_trimmed(self):
        tree = parse("<? $a = {\n  x\n|y} ?>")
        self.assertEqual(shape(tree), [("assign", "a", {"group": [["x"], ["y"]]}, 1)])

    def test_assignment_offset(self):
        self.assertEqual(parse('ab<? $a = "x" ?>').parts[1].offset, 5)

    def test_comments_in_block(self):
        tree = parse('<? $a = "x" // note\n/* c */ $b = "y" ?>')
        self.assertEqual([p.name for p in tree.parts], ["a", "b"])

    def test_input_like_name_with_leading_zero_is_ordinary(self):
        tree = parse('<? $variable_01 = "x" ?>')
        self.assertEqual(tree.parts[0].name, "variable_01")


class InvalidStatementTests(unittest.TestCase):
    def assert_invalid(self, source, line, column):
        err = error_of(source)
        self.assertIn("Invalid statement", err.message)
        self.assertIn("quote", err.message)
        self.assertEqual((err.line, err.column), (line, column), err.message)

    def test_missing_equals(self):
        self.assert_invalid("<? $a ?>", 1, 4)
        self.assert_invalid('<? $a "x" ?>', 1, 7)

    def test_missing_value(self):
        self.assert_invalid("<? $a = ?>", 1, 4)

    def test_unquoted_word_value(self):
        self.assert_invalid("<? $a = red ?>", 1, 9)

    def test_variable_value(self):
        self.assert_invalid("<? $a = $b ?>", 1, 9)

    def test_trailing_tokens(self):
        self.assert_invalid('<? $a = "x" "y" ?>', 1, 13)
        self.assert_invalid('<? $a = {x|y} z ?>', 1, 15)

    def test_statement_not_starting_with_variable(self):
        self.assert_invalid('<? "x" ?>', 1, 4)
        self.assert_invalid("<? = ?>", 1, 4)
        self.assert_invalid("<? foo ?>", 1, 4)

    def test_error_on_later_line(self):
        self.assert_invalid('a\n<?\n$a = "x"\n$b = red\n?>', 4, 6)


class KeywordTests(unittest.TestCase):
    def test_reserved_keywords(self):
        for word in ("if", "elseif", "else", "endif", "and", "or", "not"):
            with self.subTest(word=word):
                err = error_of(f"<? {word} ?>")
                self.assertIn("conditions are not supported yet", err.message)
                self.assertEqual((err.line, err.column), (1, 4))

    def test_keyword_with_expression(self):
        err = error_of('<? if $a == "x" ?>')
        self.assertIn("conditions are not supported yet", err.message)

    def test_keyword_after_separator(self):
        err = error_of('<? $a = "x"; endif ?>')
        self.assertIn("conditions are not supported yet", err.message)
        self.assertEqual((err.line, err.column), (1, 14))

    def test_keyword_prefix_word_is_not_a_keyword(self):
        err = error_of("<? iffy ?>")
        self.assertNotIn("conditions", err.message)
        self.assertIn("Invalid statement", err.message)


class InputVariableTests(unittest.TestCase):
    def test_assignment_to_input_variable(self):
        err = error_of('<? $variable_0 = "x" ?>')
        self.assertIn("$variable_0 is a node input and cannot be assigned", err.message)
        self.assertEqual((err.line, err.column), (1, 4))

    def test_multi_digit_input_variable(self):
        err = error_of('<? $variable_12 = {a|b} ?>')
        self.assertIn("node input", err.message)

    def test_assignment_inside_group_option(self):
        err = error_of('{a|<? $variable_3 = "x" ?>b}')
        self.assertIn("$variable_3 is a node input", err.message)
        self.assertEqual((err.line, err.column), (1, 7))

    def test_assignment_in_option_that_is_never_chosen_still_fails(self):
        err = error_of('{x|y|<? $variable_1 = "z" ?>}')
        self.assertIn("node input", err.message)

    def test_hint_suggests_copying(self):
        err = error_of('<? $variable_0 = "x" ?>')
        self.assertIn('$hair = "$variable_0"', err.message)

    def test_leading_zero_name_is_accepted(self):
        self.assertEqual(parse('<? $variable_01 = "x" ?>').parts[0].name, "variable_01")
        self.assertEqual(parse('<? $variable_ = "x" ?>').parts[0].name, "variable_")


class VariableNodeTests(unittest.TestCase):
    def test_variable_in_text(self):
        tree = parse("a $x b")
        self.assertEqual(shape(tree), ["a ", "$x", " b"])
        self.assertEqual(tree.parts[1], Variable("x", 2))

    def test_variable_in_string_value(self):
        tree = parse('<? $a = "p $x q" ?>')
        value = tree.parts[0].value
        self.assertIsInstance(value, Template)
        self.assertEqual(value.parts[1], Variable("x", 11))
        self.assertEqual(shape(value), ["p ", "$x", " q"])

    def test_variable_in_group_and_value_group(self):
        self.assertEqual(shape(parse("{$a|b}")), [{"group": [["$a"], ["b"]]}])
        self.assertEqual(
            shape(parse("<? $c = {$a|b} ?>")), [("assign", "c", {"group": [["$a"], ["b"]]}, 1)]
        )

    def test_dollar_without_name_is_text(self):
        self.assertEqual(shape(parse("cost $5")), ["cost $5"])


class NodeClassTests(unittest.TestCase):
    def test_nodes_are_frozen(self):
        nodes = [
            Text("a"),
            Variable("x", 0),
            Group((), 0),
            Assignment("a", Template(), 1, 0),
            Template(),
        ]
        for node in nodes:
            field = dataclasses.fields(node)[0].name
            with self.subTest(node=type(node).__name__):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(node, field, "changed")

    def test_nodes_are_slotted(self):
        for node in (Text("a"), Variable("x", 0), Template()):
            self.assertFalse(hasattr(node, "__dict__"))

    def test_nodes_compare_by_value(self):
        self.assertEqual(Text("a"), Text("a"))
        self.assertEqual(parse("{a|b}"), parse("{a|b}"))

    def test_extension_points_exist(self):
        for name in ("_parse_template", "_parse_block", "_parse_statement"):
            self.assertTrue(callable(getattr(parser.Parser, name)), name)

    def test_source_object_is_accepted(self):
        src = "a {b|c}"
        tree = parser.Parser(lexer.lex(src), errors.Source(src)).parse()
        self.assertEqual(shape(tree), ["a ", {"group": [["b"], ["c"]]}])

    def test_parse_function(self):
        src = "x"
        self.assertEqual(shape(parser.parse(lexer.lex(src), src)), ["x"])


if __name__ == "__main__":
    unittest.main()
