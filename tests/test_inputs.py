"""Tests for input variables ($variable_N). Run: python -m unittest discover -s tests"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.dirname(TESTS))

from dynamic_prompt import PromptSyntaxError, UndefinedVariableError  # noqa: E402
from dynamic_prompt import resolve_dynamic_prompt as resolve  # noqa: E402
from legacy_v1_resolver import resolve_dynamic_prompt as resolve_v1  # noqa: E402
from test_parity import generate_prompts  # noqa: E402

SEEDS = range(50)


class InputValueTests(unittest.TestCase):
    def test_input_in_prompt_text(self):
        self.assertEqual(resolve("a $variable_0 b", 0, inputs={"variable_0": "x"}), "a x b")

    def test_input_in_string_and_value_group(self):
        inputs = {"variable_0": "red"}
        self.assertEqual(resolve('<? $s = "[$variable_0]" ?>$s', 0, inputs=inputs), "[red]")
        self.assertEqual(resolve("<? $s = {$variable_0|$variable_0} ?>$s", 0, inputs=inputs), "red")

    def test_choices_resolved_once(self):
        seen = set()
        for seed in SEEDS:
            out = resolve("$variable_0 $variable_0", seed, inputs={"variable_0": "{red|blue}"})
            first, second = out.split(" ")
            self.assertEqual(first, second)
            seen.add(first)
        self.assertEqual(seen, {"red", "blue"})

    def test_empty_input(self):
        self.assertEqual(resolve("$variable_0", 0, inputs={"variable_0": ""}), "")

    def test_unmapped_input_is_undefined(self):
        with self.assertRaises(UndefinedVariableError):
            resolve("$variable_20", 0, inputs={"variable_0": "x"})

    def test_no_inputs_defines_nothing(self):
        for inputs in (None, {}):
            with self.assertRaises(UndefinedVariableError):
                resolve("$variable_0", 0, inputs=inputs)

    def test_input_uses_v1_syntax_only(self):
        value = "\\{x\\} /* c */ {a|b"
        self.assertEqual(resolve("$variable_0", 0, inputs={"variable_0": value}), "{x}  {a|b")

    def test_dollar_and_php_tags_are_literal(self):
        value = "$price $variable_0 <? x ?>"
        self.assertEqual(resolve("$variable_0", 0, inputs={"variable_0": value}), value)

    def test_input_trailing_backslash_boundary(self):
        # The value stays raw, so its trailing backslash escapes the following "|" at the final pass.
        self.assertEqual(resolve("$variable_0|", 0, inputs={"variable_0": "a" + "\\"}), "a|")


class InputSeedingTests(unittest.TestCase):
    def test_input_pick_unchanged_by_prompt_edit(self):
        for seed in SEEDS:
            inputs = {"variable_0": "{p|q|r|s}"}
            a = resolve("$variable_0", seed, inputs=inputs)
            b = resolve("{x|y|z} {1|2} $variable_0", seed, inputs=inputs).split(" ")[-1]
            self.assertEqual(a, b)

    def test_input_pick_unchanged_by_other_inputs(self):
        for seed in SEEDS:
            base = resolve("$variable_1", seed, inputs={"variable_1": "{p|q|r|s}"})
            other = resolve(
                "$variable_1", seed,
                inputs={"variable_0": "{1|2|3}", "variable_1": "{p|q|r|s}", "variable_2": "{u|v}"},
            )
            self.assertEqual(base, other)

    def test_body_choices_unchanged_by_inputs(self):
        for seed in SEEDS:
            plain = resolve("{a|b|c} {d|e|f}", seed)
            wired = resolve("{a|b|c} {d|e|f}", seed, inputs={"variable_0": "{x|y|z}", "variable_1": "{1|2}"})
            self.assertEqual(plain, wired)

    def test_parity_with_inputs_connected(self):
        for text in generate_prompts()[:1000]:
            for seed in range(5):
                expected = resolve_v1(text, seed)
                if "\\<?" in expected:
                    continue
                self.assertEqual(resolve(text, seed, inputs={"variable_0": "{x|y}"}), expected, (text, seed))


class InputErrorTests(unittest.TestCase):
    def assert_assignment_error(self, text, inputs, line, column):
        with self.assertRaises(PromptSyntaxError) as ctx:
            resolve(text, 0, inputs=inputs)
        self.assertEqual((ctx.exception.line, ctx.exception.column), (line, column))

    def test_assigning_an_input_variable(self):
        text = 'x\n<? $variable_0 = "1" ?>'
        for inputs in (None, {"variable_0": "v"}):
            self.assert_assignment_error(text, inputs, 2, 4)

    def test_assigning_inside_an_unchosen_option(self):
        text = '{a|<? $variable_0 = "1" ?>}'
        for inputs in (None, {"variable_0": "v"}):
            self.assert_assignment_error(text, inputs, 1, 7)

    def test_invalid_names(self):
        for name in ("foo", "variable_01", "Variable_0", "variable_", 3):
            with self.assertRaises(ValueError, msg=repr(name)):
                resolve("x", 0, inputs={name: "x"})

    def test_non_string_values(self):
        for value in (None, 5, b"x", ["x"]):
            with self.assertRaises(TypeError, msg=repr(value)):
                resolve("x", 0, inputs={"variable_0": value})

    def test_invalid_entry_blocks_all_resolution(self):
        with self.assertRaises(TypeError):
            resolve("x", 0, inputs={"variable_0": "ok", "variable_1": 1})


if __name__ == "__main__":
    unittest.main()
