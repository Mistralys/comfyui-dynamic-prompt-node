"""Behavioural tests for variables, escapes and statements. Run: python -m unittest discover -s tests"""
import os
import sys
import unittest
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from dynamic_prompt import resolve_dynamic_prompt as resolve  # noqa: E402


class AssignmentTests(unittest.TestCase):
    def test_string_value_is_reused(self):
        text = '<? $c = "deep {crimson|navy}" ?>$c hair, $c dress'
        results = {resolve(text, seed) for seed in range(50)}
        self.assertEqual(results, {"deep crimson hair, deep crimson dress", "deep navy hair, deep navy dress"})

    def test_group_value(self):
        results = {resolve("<? $c = {red|blue} ?>$c/$c", seed) for seed in range(50)}
        self.assertEqual(results, {"red/red", "blue/blue"})

    def test_nested_group_value(self):
        results = {resolve("<? $c = {a|{b|c}} ?>$c", seed) for seed in range(100)}
        self.assertEqual(results, {"a", "b", "c"})

    def test_multiline_group_value_is_trimmed(self):
        results = {resolve("<? $c = {\n  one\n  two\n  |\n  three\n} ?>[$c]", seed) for seed in range(50)}
        self.assertEqual(results, {"[one\n  two]", "[three]"})

    def test_string_interpolates_earlier_variables(self):
        text = '<? $a = "x"; $b = "y"; $c = "$a and $b" ?>$c'
        self.assertEqual(resolve(text, 0), "x and y")

    def test_value_is_not_resolved_again(self):
        text = '<? $a = "\\{a\\|b\\}" ?>$a|$a'
        self.assertEqual(resolve(text, 0), "{a|b}|{a|b}")

    def test_escaped_dollar_in_value_is_not_a_variable(self):
        text = '<? $a = "\\$b" ?>$a'
        self.assertEqual(resolve(text, 0), "$b")

    def test_reassignment_replaces_value(self):
        text = '<? $a = "one" ?>$a <? $a = "two" ?>$a'
        self.assertEqual(resolve(text, 0), "one two")

    def test_reassignment_may_use_previous_value(self):
        text = '<? $a = "x"; $a = "$a$a" ?>$a'
        self.assertEqual(resolve(text, 0), "xx")

    def test_assignment_inside_unchosen_option_does_not_run(self):
        # Only the chosen option runs, so $a exists exactly when "first" was chosen.
        outcomes = set()
        for seed in range(50):
            try:
                outcomes.add(resolve('{<? $a = "1" ?>x|y}$a', seed))
            except ValueError:
                outcomes.add("error")
        self.assertEqual(outcomes, {"x1", "error"})


class SeedingTests(unittest.TestCase):
    BODY = "{a|b|c} {d|e|f}"

    def test_header_edit_keeps_body_choices(self):
        headers = [
            "",
            '<? $h = {x|y|z} ?>',
            '<? $h = {x|y|z}; $e = {p|q} ?>',
            '<? $e = "{p|q}"; $h = "{x|y|z}"; $h = "{1|2}" ?>',
        ]
        for seed in range(50):
            outputs = {resolve(header + self.BODY, seed) for header in headers}
            self.assertEqual(len(outputs), 1, (seed, outputs))

    def test_other_assignment_does_not_change_value(self):
        for seed in range(50):
            plain = resolve('<? $hair = {red|blue|green|pink} ?>$hair', seed)
            extra = resolve('<? $eyes = {a|b|c} ?><? $hair = {red|blue|green|pink} ?>$hair', seed)
            self.assertEqual(plain, extra, seed)

    def test_second_assignment_is_independent_pick(self):
        text = '<? $a = {x|y|z|w}; $first = "$a"; $a = {x|y|z|w} ?>$first$a'
        differing = [seed for seed in range(50) if len(set(resolve(text, seed))) == 2]
        same = [seed for seed in range(50) if len(set(resolve(text, seed))) == 1]
        self.assertTrue(differing)
        self.assertTrue(same)

    def test_reproducible(self):
        text = '<? $a = {x|y|z} ?>{p|q|r} $a {s|t|u}'
        for seed in range(20):
            self.assertEqual(resolve(text, seed), resolve(text, seed))

    def test_all_values_reachable(self):
        seen = Counter(resolve("<? $a = {x|y|z} ?>$a", seed) for seed in range(100))
        self.assertEqual(set(seen), {"x", "y", "z"})


class EscapeTests(unittest.TestCase):
    def test_escaped_dollar(self):
        self.assertEqual(resolve("\\$name", 0), "$name")

    def test_escaped_block_open(self):
        self.assertEqual(resolve("\\<? x", 0), "<? x")

    def test_dollar_without_name_is_literal(self):
        self.assertEqual(resolve("$5 a $ b $", 0), "$5 a $ b $")

    def test_trailing_dollar_is_literal(self):
        self.assertEqual(resolve("a $", 0), "a $")

    def test_dollar_in_string_value_without_name_is_literal(self):
        self.assertEqual(resolve('<? $a = "costs $5" ?>$a', 0), "costs $5")

    def test_name_ends_at_first_non_identifier_character(self):
        self.assertEqual(resolve('<? $a = "x" ?>$a-$a.', 0), "x-x.")

    def test_single_option_group_glues_text(self):
        self.assertEqual(resolve('<? $a = "red" ?>{$a}ish', 0), "redish")


class StatementTests(unittest.TestCase):
    def test_semicolon_and_newline_separators(self):
        self.assertEqual(resolve('<? $a = "1"; $b = "2"\n$c = "3" ?>$a$b$c', 0), "123")

    def test_empty_block(self):
        self.assertEqual(resolve("a<??>b", 0), "ab")
        self.assertEqual(resolve("a<?  \n ?>b", 0), "ab")

    def test_line_comment_ends_at_block_close(self):
        self.assertEqual(resolve('<? $a = "x" // note ?>$a', 0), "x")

    def test_line_comment_ends_at_line_break(self):
        self.assertEqual(resolve('<? $a = "x" // note\n$b = "y" ?>$a$b', 0), "xy")

    def test_block_comment_may_contain_close(self):
        self.assertEqual(resolve('<? $a = "x" /* ?> still comment */ ?>$a', 0), "x")

    def test_comments_are_text_inside_strings(self):
        self.assertEqual(resolve('<? $a = "x//y /*z" ?>$a', 0), "x//y /*z")

    def test_trailing_semicolons_are_accepted(self):
        self.assertEqual(resolve('<? $a = "x"; ?>$a', 0), "x")


if __name__ == "__main__":
    unittest.main()
