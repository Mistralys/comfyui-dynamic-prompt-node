"""Standalone-line and inline-block whitespace behaviour (Language Specification section 7)."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from dynamic_prompt import resolve_dynamic_prompt as resolve  # noqa: E402


class StandaloneTests(unittest.TestCase):
    def test_single_line_block_vanishes(self):
        self.assertEqual(resolve('a\n<? $x = "1" ?>\nb', 0), "a\nb")

    def test_crlf(self):
        self.assertEqual(resolve('a\r\n<? $x = "1" ?>\r\nb', 0), "a\r\nb")

    def test_multiline_block_vanishes(self):
        self.assertEqual(resolve('a\n<? $x = "1"\n   $y = "2" ?>\nb', 0), "a\nb")

    def test_two_blocks_on_one_line(self):
        self.assertEqual(resolve('a\n<? $x = "1" ?> <? $y = "2" ?>  \nb', 0), "a\nb")

    def test_block_at_end_without_newline(self):
        self.assertEqual(resolve('a\n<? $x = "1" ?>', 0), "a\n")

    def test_block_with_trailing_comment(self):
        self.assertEqual(resolve('a\n  <? $x = "1" ?> // note\nb', 0), "a\nb")

    def test_block_inside_multiline_option(self):
        text = '{\n  a\n  <? $x = "1" ?>\n  b\n}'
        self.assertEqual(resolve(text, 0), "a\n  b")

    def test_inline_block_keeps_surrounding_text(self):
        self.assertEqual(resolve('a <? $x = "1" ?> b', 0), "a  b")
        self.assertEqual(resolve('a <? $x = "1" ?><? $y = "2" ?>\nb', 0), "a \nb")

    def test_comment_only_line_keeps_newline(self):
        self.assertEqual(resolve("a\n// note\nb", 0), "a\n\nb")


if __name__ == "__main__":
    unittest.main()
