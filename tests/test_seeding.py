"""Tests for seed derivation and random streams. Run: python -m unittest discover -s tests"""
import ast
import os
import random
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _package_loader import load_submodule  # noqa: E402

evaluator = load_submodule("evaluator")
derive_seed = evaluator.derive_seed
RandomStreams = evaluator.RandomStreams


class DeriveSeedTests(unittest.TestCase):
    def test_golden_value(self):
        # Pins the SHA-256 key format; a change here silently reshuffles every user's variables.
        self.assertEqual(derive_seed(0, "assign", "hair", 1), 2917107427997320453)

    def test_input_stream_golden_value(self):
        # Pins the input stream key; a change here silently reshuffles every connected input.
        self.assertEqual(derive_seed(0, "input", "variable_0"), 10886624414350897158)

    def test_is_deterministic(self):
        self.assertEqual(derive_seed(5, "input", "variable_0"), derive_seed(5, "input", "variable_0"))

    def test_parts_change_the_result(self):
        base = derive_seed(0, "assign", "hair", 1)
        self.assertNotEqual(base, derive_seed(1, "assign", "hair", 1))
        self.assertNotEqual(base, derive_seed(0, "input", "hair", 1))
        self.assertNotEqual(base, derive_seed(0, "assign", "eyes", 1))
        self.assertNotEqual(base, derive_seed(0, "assign", "hair", 2))

    def test_part_boundaries_are_unambiguous(self):
        self.assertNotEqual(derive_seed(0, "ab", "c"), derive_seed(0, "a", "bc"))

    def test_module_does_not_use_builtin_hash(self):
        with open(evaluator.__file__, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertIn("hashlib", imports)
        self.assertNotIn("hash", calls)


class RandomStreamsTests(unittest.TestCase):
    def test_body_matches_plain_random(self):
        streams = RandomStreams(42)
        expected = random.Random(42)
        self.assertEqual([streams.body.random() for _ in range(5)], [expected.random() for _ in range(5)])

    def test_for_assignment_uses_derived_seed(self):
        streams = RandomStreams(7)
        expected = random.Random(derive_seed(7, "assign", "hair", 2))
        self.assertEqual(streams.for_assignment("hair", 2).random(), expected.random())

    def test_for_input_uses_derived_seed(self):
        streams = RandomStreams(7)
        expected = random.Random(derive_seed(7, "input", "variable_3"))
        self.assertEqual(streams.for_input("variable_3").random(), expected.random())

    def test_streams_are_fresh_and_independent(self):
        streams = RandomStreams(7)
        streams.for_assignment("hair", 1).random()
        fresh = random.Random(derive_seed(7, "assign", "hair", 1)).random()
        self.assertEqual(streams.for_assignment("hair", 1).random(), fresh)
        streams.body.random()
        fresh_input = random.Random(derive_seed(7, "input", "variable_0")).random()
        self.assertEqual(streams.for_input("variable_0").random(), fresh_input)


class HashSeedIndependenceTests(unittest.TestCase):
    PROMPT = '<? $a = {x|y|z|w}; $b = "{p|q|r} $a" ?>{1|2|3|4} $a $b {5|6|7|8}'
    SCRIPT = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from dynamic_prompt import resolve_dynamic_prompt as r; "
        "print(repr([r(sys.argv[2], s) for s in range(10)]))"
    )

    def run_with_hash_seed(self, hash_seed):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, PYTHONHASHSEED=str(hash_seed))
        result = subprocess.run(
            [sys.executable, "-c", self.SCRIPT, repo, self.PROMPT],
            env=env, capture_output=True, text=True, check=True,
        )
        return result.stdout

    def test_independent_of_hash_seed(self):
        first = self.run_with_hash_seed(1)
        self.assertEqual(first, self.run_with_hash_seed(2))
        self.assertTrue(first.startswith("["))


if __name__ == "__main__":
    unittest.main()
