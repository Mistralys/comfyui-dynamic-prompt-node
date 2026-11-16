"""Unit tests for the dynamic prompt resolver and node. Run: python -m unittest discover tests"""
import asyncio
import importlib.util
import os
import sys
import unittest
from collections import Counter
from types import ModuleType

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from dynamic_prompt import resolve_dynamic_prompt as resolve  # noqa: E402


class ResolverTests(unittest.TestCase):
    def test_plain_text_is_unchanged(self):
        self.assertEqual(resolve("a red fox", 1), "a red fox")

    def test_empty_text(self):
        self.assertEqual(resolve("", 1), "")

    def test_same_seed_is_reproducible(self):
        text = "{a|b|c|d|e} {f|g|h|i|j} {k|l|m|n|o}"
        self.assertEqual(resolve(text, 42), resolve(text, 42))

    def test_all_options_reachable(self):
        seen = Counter(resolve("{a|b|c}", seed) for seed in range(200))
        self.assertEqual(set(seen), {"a", "b", "c"})

    def test_single_option_group(self):
        self.assertEqual(resolve("{a}", 0), "a")

    def test_empty_options(self):
        results = {resolve("x{|y}", seed) for seed in range(50)}
        self.assertEqual(results, {"x", "xy"})

    def test_empty_group(self):
        self.assertEqual(resolve("a{}b", 0), "ab")

    def test_nested_groups(self):
        results = {resolve("{a|{b|c}}", seed) for seed in range(100)}
        self.assertEqual(results, {"a", "b", "c"})

    def test_multiple_groups_resolve_independently(self):
        results = {resolve("{a|b}-{a|b}", seed) for seed in range(100)}
        self.assertEqual(results, {"a-a", "a-b", "b-a", "b-b"})

    def test_escaped_special_characters_are_literal(self):
        self.assertEqual(resolve(r"\{a\|b\}", 0), "{a|b}")

    def test_escaped_pipe_inside_group(self):
        self.assertEqual(resolve(r"{a\|b}", 0), "a|b")

    def test_stray_closing_brace_is_literal(self):
        self.assertEqual(resolve("a}b", 0), "a}b")

    def test_block_comment_removed(self):
        self.assertEqual(resolve("a/* hidden {x|y} */b", 0), "ab")

    def test_multiline_block_comment_removed(self):
        self.assertEqual(resolve("a/* one\ntwo */b", 0), "ab")

    def test_line_comment_removed(self):
        self.assertEqual(resolve("a\n// note\nb", 0), "a\n\nb")

    def test_trailing_line_comment_removed(self):
        self.assertEqual(resolve("a // note", 0), "a ")

    def test_url_is_not_a_comment(self):
        self.assertEqual(resolve("see https://example.com/x", 0), "see https://example.com/x")

    def test_unclosed_brace_is_literal(self):
        self.assertEqual(resolve("a {b", 0), "a {b")

    def test_unclosed_outer_brace_still_resolves_inner_group(self):
        results = {resolve("{a {b|c}", seed) for seed in range(50)}
        self.assertEqual(results, {"{a b", "{a c"})

    def test_multiline_options_are_trimmed(self):
        text = "{\n    option one\n    |\n    option two\n    |\n    option three\n}"
        results = {resolve(text, seed) for seed in range(100)}
        self.assertEqual(results, {"option one", "option two", "option three"})

    def test_multiline_options_with_crlf_are_trimmed(self):
        results = {resolve("{\r\n  a\r\n  |\r\n  b\r\n}", seed) for seed in range(50)}
        self.assertEqual(results, {"a", "b"})

    def test_multiline_option_keeps_inner_line_breaks(self):
        self.assertEqual(resolve("{\n  one\n  two\n}", 0), "one\n  two")

    def test_nested_group_at_option_edge_is_trimmed(self):
        results = {resolve("a {\n  {x|y}\n} b", seed) for seed in range(50)}
        self.assertEqual(results, {"a x b", "a y b"})

    def test_single_line_spaces_are_kept(self):
        results = {resolve("[{a |b }]", seed) for seed in range(50)}
        self.assertEqual(results, {"[a ]", "[b ]"})

    def test_whitespace_only_multiline_option_becomes_empty(self):
        results = {resolve("x{\n  |\n  y\n}", seed) for seed in range(50)}
        self.assertEqual(results, {"x", "xy"})

    def test_text_outside_groups_is_not_trimmed(self):
        self.assertEqual(resolve("  a\n  b  ", 0), "  a\n  b  ")

    def test_unicode_text(self):
        self.assertIn(resolve("{猫|犬} ☕", 3), {"猫 ☕", "犬 ☕"})

    def test_huge_seed(self):
        self.assertIn(resolve("{a|b}", 0xFFFFFFFFFFFFFFFF), {"a", "b"})


def _load_package():
    """Load the repo as a package with comfy_api stubbed out."""
    class Input:
        def __init__(self, id, **kw):
            self.id, self.kw = id, kw

    class Output(Input):
        pass

    class Schema:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class NodeOutput:
        def __init__(self, *args):
            self.args = args

    io = ModuleType("io")
    io.ComfyNode = type("ComfyNode", (), {})
    io.Schema = Schema
    io.NodeOutput = NodeOutput
    io.String = type("String", (), {"Input": Input, "Output": Output})
    io.Int = type("Int", (), {"Input": Input})

    latest = ModuleType("comfy_api.latest")
    latest.io = io
    latest.ComfyExtension = type("ComfyExtension", (), {})
    api = ModuleType("comfy_api")
    api.latest = latest
    sys.modules.update({"comfy_api": api, "comfy_api.latest": latest})

    spec = importlib.util.spec_from_file_location(
        "dynamic_prompt_pkg", os.path.join(REPO, "__init__.py"),
        submodule_search_locations=[REPO],
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["dynamic_prompt_pkg"] = pkg
    spec.loader.exec_module(pkg)
    return pkg


class NodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = _load_package()
        cls.node = sys.modules["dynamic_prompt_pkg.nodes"].DynamicPromptTextNode

    def test_schema(self):
        schema = self.node.define_schema()
        self.assertEqual(schema.node_id, "Mistralys_DynamicPromptText")
        text, seed = schema.inputs
        self.assertEqual((text.id, seed.id), ("text", "seed"))
        self.assertTrue(text.kw["multiline"])
        self.assertIs(text.kw["dynamic_prompts"], False)
        self.assertTrue(seed.kw["control_after_generate"])
        self.assertEqual(seed.kw["max"], 0xFFFFFFFFFFFFFFFF)
        self.assertEqual([o.id for o in schema.outputs], ["PROMPT"])

    def test_execute_resolves_text(self):
        result = self.node.execute("{a|b}", 7)
        self.assertEqual(result.args, (resolve("{a|b}", 7),))

    def test_extension_lists_node(self):
        ext = self.pkg.DynamicPromptExtension()
        self.assertEqual(asyncio.run(ext.get_node_list()), [self.node])

    def test_entrypoint_returns_extension(self):
        self.assertIsInstance(asyncio.run(self.pkg.comfy_entrypoint()), self.pkg.DynamicPromptExtension)


if __name__ == "__main__":
    unittest.main()
