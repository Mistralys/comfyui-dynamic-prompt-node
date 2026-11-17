"""Differential tests: the package resolver must equal the frozen v1 oracle for v1-only prompts."""
import ast
import os
import random
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
sys.path.insert(0, REPO)

from dynamic_prompt import resolve_dynamic_prompt as resolve  # noqa: E402
from legacy_v1_resolver import resolve_dynamic_prompt as resolve_v1  # noqa: E402

ALPHABET = ["{", "}", "|", "\\", "/", "*", " ", "\n", "\r", "\t", "a", "b", "<", "?", ">"]
PROMPT_COUNT = 3000
SEEDS = range(5)

QUIRKS = [
    '\\\\{a|b}',
    '\\\\\\{a|b}',
    'a\\',
    '\\',
    '{a\\}|b}',
    '{a|b\\',
    '\\/* x */',
    'a\\// b',
    '{a // x\n|b}',
    '{a /* } */|b}',
    '/* unclosed {a|b}',
    'a /* x */ // y\nb',
    '{{a|b}|{c|d}}',
    '{a|{b|c}',
    '{{a|b}',
    '}{',
    '|',
    '{|}',
    'a < ? > b',
    '\\<a|b>',
    'x?>y',
    '{\n a\n |\n b\n}',
    '{ \r\n a \r\n}',
    '{a\n}\n{\nb}',
    '{ a |b }',
    '{\\{|\\}}',
    'a\\\\|b',
    '{a\\\\|b}',
    'https://example.com // note',
    '{a|b}//c\n{d|e}',
]


def generate_prompts():
    rng = random.Random(20261117)
    prompts = []
    for _ in range(PROMPT_COUNT):
        text = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 40)))
        if "<?" not in text:
            prompts.append(text)
    return prompts


def resolver_test_inputs():
    """Every string literal passed as the first argument of resolve() in ResolverTests."""
    path = os.path.join(TESTS, "test_dynamic_prompt.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    values = []
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef) and cls.name == "ResolverTests":
            for node in ast.walk(cls):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "resolve":
                    first = node.args[0] if node.args else None
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        values.append(first.value)
    return values


class ParityTests(unittest.TestCase):
    def test_generated_prompts_match_v1(self):
        prompts = generate_prompts()
        self.assertGreater(len(prompts), 1000)
        skipped = 0
        for text in prompts:
            for seed in SEEDS:
                expected = resolve_v1(text, seed)
                if "\\<?" in expected:
                    # Known boundary edge: v1 resolved text that now forms the new "\<?" escape
                    # across a group or comment boundary (for example "{\n\<}?"). The final
                    # unescape pass decodes it; see the grammar spec, "Known boundary edge".
                    skipped += 1
                    continue
                self.assertEqual(resolve(text, seed), expected, (text, seed))
        self.assertLess(skipped, 20)

    def test_new_escape_formed_across_a_group_boundary(self):
        # Pins the documented boundary edge excluded above.
        self.assertEqual(resolve_v1("{\n\\<}?", 0), "\\<?")
        self.assertEqual(resolve("{\n\\<}?", 0), "<?")

    def test_known_quirks_match_v1(self):
        texts = QUIRKS + resolver_test_inputs()
        self.assertTrue(resolver_test_inputs())
        for text in texts:
            self.assertNotIn("<?", text)
            for seed in range(50):
                self.assertEqual(resolve(text, seed), resolve_v1(text, seed), (text, seed))


if __name__ == "__main__":
    unittest.main()
