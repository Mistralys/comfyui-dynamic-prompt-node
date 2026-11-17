"""Token-level tests for the lexer: dialects, v1 comment quirks, code blocks, errors, standalone lines."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _package_loader import load_submodule  # noqa: E402

lexer = load_submodule("lexer")
errors = load_submodule("errors")
rules = load_submodule("text_rules")

lex = lexer.lex
Dialect = lexer.Dialect
Token = lexer.Token
K = lexer.TokenKind
strip = lexer.strip_standalone_lines


def kv(tokens):
    """(kind name, value) pairs for compact assertions."""
    return [(t.kind.name, t.value) for t in tokens]


def stripped_text(source):
    """The text of the tokens after the standalone pass, blocks shown as '<B>'."""
    return "".join("<B>" if t.kind is K.BLOCK else t.value for t in strip(lex(source)))


class BodyTokenTests(unittest.TestCase):
    def test_plain_text_is_one_token(self):
        self.assertEqual(kv(lex("a red cat")), [("TEXT", "a red cat")])

    def test_empty_source_has_no_tokens(self):
        self.assertEqual(lex(""), [])

    def test_group_tokens_with_offsets(self):
        tokens = lex("x{a|b}y")
        self.assertEqual(
            kv(tokens),
            [("TEXT", "x"), ("GROUP_OPEN", "{"), ("TEXT", "a"), ("PIPE", "|"),
             ("TEXT", "b"), ("GROUP_CLOSE", "}"), ("TEXT", "y")],
        )
        self.assertEqual([(t.offset, t.end) for t in tokens],
                         [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)])

    def test_escapes_stay_raw(self):
        self.assertEqual(kv(lex(r"\{a\|b\}")), [("TEXT", r"\{a\|b\}")])

    def test_double_backslash_pairs_before_structure(self):
        self.assertEqual(kv(lex(r"\\|")), [("TEXT", "\\\\"), ("PIPE", "|")])

    def test_escaped_dollar_is_text(self):
        self.assertEqual(kv(lex(r"\$name")), [("TEXT", r"\$name")])

    def test_escaped_block_opener_is_raw_three_characters(self):
        self.assertEqual(kv(lex(r"a\<?b")), [("TEXT", r"a\<?b")])

    def test_backslash_before_other_character_is_a_raw_pair(self):
        self.assertEqual(kv(lex(r"\n\"")), [("TEXT", r"\n\"")])

    def test_lone_trailing_backslash_is_text(self):
        self.assertEqual(kv(lex("a\\")), [("TEXT", "a\\")])

    def test_variable_token(self):
        tokens = lex("a $hair_2 b")
        self.assertEqual(kv(tokens), [("TEXT", "a "), ("VARIABLE", "hair_2"), ("TEXT", " b")])
        self.assertEqual((tokens[1].offset, tokens[1].end), (2, 9))

    def test_dollar_without_identifier_is_text(self):
        self.assertEqual(kv(lex("$5 $ cost $")), [("TEXT", "$5 $ cost $")])

    def test_block_token_offsets(self):
        tokens = lex("a<? $x = {b} ?>c")
        self.assertEqual([t.kind for t in tokens], [K.TEXT, K.BLOCK, K.TEXT])
        block = tokens[1]
        self.assertEqual((block.offset, block.end), (1, 15))
        self.assertEqual(block.value, "<? $x = {b} ?>")

    def test_close_marker_in_body_is_text(self):
        self.assertEqual(kv(lex("a ?> b")), [("TEXT", "a ?> b")])

    def test_group_inside_group_tokens(self):
        self.assertEqual(
            [t.kind.name for t in lex("{a{b|c}|d}")],
            ["GROUP_OPEN", "TEXT", "GROUP_OPEN", "TEXT", "PIPE", "TEXT", "GROUP_CLOSE",
             "PIPE", "TEXT", "GROUP_CLOSE"],
        )

    def test_text_merges_across_dropped_comments(self):
        tokens = lex("a/* x */b // note\nc")
        self.assertEqual(kv(tokens), [("TEXT", "ab \nc")])
        self.assertEqual((tokens[0].offset, tokens[0].end), (0, 19))

    def test_block_inside_group_option(self):
        kinds = [t.kind.name for t in lex("{a<? $x = {b} ?>|c}")]
        self.assertEqual(kinds, ["GROUP_OPEN", "TEXT", "BLOCK", "PIPE", "TEXT", "GROUP_CLOSE"])


class CommentQuirkTests(unittest.TestCase):
    def test_comment_between_backslash_and_brace_keeps_raw_pair(self):
        self.assertEqual(kv(lex("\\/* c */{")), [("TEXT", "\\{")])

    def test_two_comments_after_backslash(self):
        self.assertEqual(kv(lex("\\/* a *//* b */|")), [("TEXT", "\\|")])

    def test_backslash_then_comment_then_open_marker(self):
        self.assertEqual(kv(lex("\\/* c */<?")), [("TEXT", "\\<?")])

    def test_trailing_backslash_then_comment_is_lone_backslash(self):
        self.assertEqual(kv(lex("a\\/* c */")), [("TEXT", "a\\")])

    def test_comment_inside_option_after_backslash(self):
        # The escaped pipe stays text, so the group has a single option: v1 gives x|y.
        self.assertEqual([t.kind.name for t in lex("{x\\/**/|y}")],
                         ["GROUP_OPEN", "TEXT", "GROUP_CLOSE"])
        self.assertEqual(lex("{x\\/**/|y}")[1].value, "x\\|y")

    def test_line_comment_lookbehind_sees_original_character(self):
        # The block comment is dropped, but the "//" after it still follows a "/" in the original.
        self.assertEqual(kv(lex("/*x*///y")), [("TEXT", "//y")])

    def test_line_comment_after_dropped_block_comment_and_space(self):
        self.assertEqual(kv(lex("a/*x*/ //y\nb")), [("TEXT", "a \nb")])

    def test_line_comment_eats_carriage_return(self):
        self.assertEqual(kv(lex("a //x\r\nb")), [("TEXT", "a \nb")])

    def test_url_is_not_a_comment(self):
        self.assertEqual(kv(lex("see https://x.y/z")), [("TEXT", "see https://x.y/z")])

    def test_line_comment_at_start(self):
        self.assertEqual(kv(lex("//note\nb")), [("TEXT", "\nb")])

    def test_unclosed_block_comment_stays_literal(self):
        self.assertEqual(kv(lex("a /* b")), [("TEXT", "a /* b")])

    def test_unclosed_block_comment_with_group_after(self):
        self.assertEqual(kv(lex("/* {a|b}"))[0], ("TEXT", "/* "))

    def test_comment_swallows_structure(self):
        self.assertEqual(kv(lex("a/* {|} */b")), [("TEXT", "ab")])


class BlockChildrenTests(unittest.TestCase):
    def children(self, source):
        (block,) = [t for t in lex(source) if t.kind is K.BLOCK]
        return block.children

    def test_assignment_with_string(self):
        children = self.children('<? $a = "red" ?>')
        self.assertEqual(
            [(t.kind.name, t.value) for t in children],
            [("VARIABLE", "a"), ("ASSIGN", "="), ("STRING", '"red"')],
        )
        string = children[2]
        self.assertEqual((string.offset, string.end), (8, 13))
        self.assertEqual(kv(string.children), [("TEXT", "red")])

    def test_empty_block(self):
        self.assertEqual(self.children("<??>"), ())
        self.assertEqual(self.children("<?  ?>"), ())

    def test_separators_semicolon_and_line_break(self):
        children = self.children('<? $a = "x"; $b = "y"\n$c = "z" ?>')
        self.assertEqual(
            [t.kind.name for t in children],
            ["VARIABLE", "ASSIGN", "STRING", "SEPARATOR", "VARIABLE", "ASSIGN", "STRING",
             "SEPARATOR", "VARIABLE", "ASSIGN", "STRING"],
        )
        self.assertEqual([t.value for t in children if t.kind is K.SEPARATOR], [";", "\n"])

    def test_crlf_is_one_separator(self):
        children = self.children('<? $a = "x"\r\n$b = "y" ?>')
        self.assertEqual([t.value for t in children if t.kind is K.SEPARATOR], ["\n"])

    def test_word_token(self):
        children = self.children("<? if ?>")
        self.assertEqual(kv(children), [("WORD", "if")])

    def test_word_and_variable_tokens_distinguish_dollar(self):
        children = self.children("<? red $red ?>")
        self.assertEqual(kv(children), [("WORD", "red"), ("VARIABLE", "red")])

    def test_string_escaped_quote_is_decoded(self):
        children = self.children(r'<? $a = "say \"hi\"" ?>')
        self.assertEqual(kv(children[2].children), [("TEXT", 'say "hi"')])

    def test_string_keeps_other_escapes_raw(self):
        children = self.children(r'<? $a = "\{x\} \\ \$y \<?" ?>')
        self.assertEqual(kv(children[2].children), [("TEXT", r"\{x\} \\ \$y \<?")])

    def test_string_double_backslash_before_quote_ends_string(self):
        children = self.children('<? $a = "x\\\\" ?>')
        self.assertEqual(kv(children[2].children), [("TEXT", "x\\\\")])

    def test_string_has_no_comments(self):
        children = self.children('<? $a = "a // b /* c */ d" ?>')
        self.assertEqual(kv(children[2].children), [("TEXT", "a // b /* c */ d")])

    def test_string_children_include_groups_and_variables(self):
        children = self.children('<? $a = "x {b|c} $d" ?>')
        self.assertEqual(
            kv(children[2].children),
            [("TEXT", "x "), ("GROUP_OPEN", "{"), ("TEXT", "b"), ("PIPE", "|"), ("TEXT", "c"),
             ("GROUP_CLOSE", "}"), ("TEXT", " "), ("VARIABLE", "d")],
        )

    def test_string_may_span_lines(self):
        children = self.children('<? $a = "x\ny" ?>')
        self.assertEqual(kv(children[2].children), [("TEXT", "x\ny")])

    def test_string_dollar_without_name_is_text(self):
        children = self.children('<? $a = "5$ $" ?>')
        self.assertEqual(kv(children[2].children), [("TEXT", "5$ $")])

    def test_close_marker_text_in_string_via_escape_of_open_marker(self):
        children = self.children(r'<? $a = "a\<?b" ?>')
        self.assertEqual(kv(children[2].children), [("TEXT", r"a\<?b")])

    def test_value_group_is_flat(self):
        children = self.children("<? $a = {red|dark {blue|green}} ?>")
        self.assertEqual(
            [(t.kind.name, t.value) for t in children],
            [("VARIABLE", "a"), ("ASSIGN", "="), ("GROUP_OPEN", "{"), ("TEXT", "red"),
             ("PIPE", "|"), ("TEXT", "dark "), ("GROUP_OPEN", "{"), ("TEXT", "blue"),
             ("PIPE", "|"), ("TEXT", "green"), ("GROUP_CLOSE", "}"), ("GROUP_CLOSE", "}")],
        )

    def test_value_group_variable_and_comments(self):
        children = self.children("<? $a = {$b/* x */|c // y\n} ?>")
        self.assertEqual(
            [t.kind.name for t in children[2:]],
            ["GROUP_OPEN", "VARIABLE", "PIPE", "TEXT", "GROUP_CLOSE"],
        )
        self.assertEqual(children[5].value, "c \n")

    def test_value_group_keeps_quote_escape_raw(self):
        children = self.children(r'<? $a = {x\"y} ?>')
        self.assertEqual(children[3].value, r'x\"y')

    def test_value_group_text_quote_is_literal(self):
        children = self.children('<? $a = {say "x"} ?>')
        self.assertEqual(children[3].value, 'say "x"')

    def test_code_line_comment_ends_at_line_break(self):
        children = self.children('<? $a = "x" // note\n$b = "y" ?>')
        self.assertEqual(
            [t.kind.name for t in children],
            ["VARIABLE", "ASSIGN", "STRING", "SEPARATOR", "VARIABLE", "ASSIGN", "STRING"],
        )

    def test_code_line_comment_ends_before_close_marker(self):
        tokens = lex('<? $a = "x" // note ?>tail')
        self.assertEqual([t.kind.name for t in tokens], ["BLOCK", "TEXT"])
        self.assertEqual(tokens[1].value, "tail")
        self.assertEqual([t.kind.name for t in tokens[0].children], ["VARIABLE", "ASSIGN", "STRING"])

    def test_code_line_comment_without_lookbehind(self):
        # In code, "//" is a comment anywhere, even directly after a token.
        children = self.children('<? $a = "x"// note\n ?>')
        self.assertEqual([t.kind.name for t in children], ["VARIABLE", "ASSIGN", "STRING", "SEPARATOR"])

    def test_code_block_comment_may_contain_close_marker(self):
        tokens = lex('<? /* ?> */ $a = "x" ?>after')
        self.assertEqual([t.kind.name for t in tokens], ["BLOCK", "TEXT"])
        self.assertEqual([t.kind.name for t in tokens[0].children], ["VARIABLE", "ASSIGN", "STRING"])

    def test_code_block_comment_spans_lines(self):
        children = self.children('<? /* a\nb */ $a = "x" ?>')
        self.assertEqual([t.kind.name for t in children], ["VARIABLE", "ASSIGN", "STRING"])

    def test_close_marker_inside_string_is_an_error_not_a_close(self):
        with self.assertRaises(errors.PromptSyntaxError):
            lex('<? $a = "x ?>" ?>')


class LexerErrorTests(unittest.TestCase):
    def assertError(self, source, line, column, fragment=None):
        with self.assertRaises(errors.PromptSyntaxError) as ctx:
            lex(source)
        self.assertEqual((ctx.exception.line, ctx.exception.column), (line, column), str(ctx.exception))
        self.assertIsInstance(ctx.exception, ValueError)
        self.assertTrue(str(ctx.exception).startswith(f"Line {line}, column {column}:"))
        if fragment:
            self.assertIn(fragment, str(ctx.exception))

    def test_unclosed_block_points_at_open_marker(self):
        self.assertError("ab\n  <? $a = \"x\"", 2, 3, "Unclosed code block")

    def test_unclosed_empty_block(self):
        self.assertError("<?", 1, 1, "Unclosed code block")

    def test_unclosed_string_points_at_opening_quote(self):
        self.assertError('a\n<? $a = "x', 2, 9, "Unclosed string")

    def test_close_marker_inside_string(self):
        self.assertError('<? $a = "x ?>', 1, 9, "Unclosed string")

    def test_open_marker_inside_string(self):
        self.assertError('<? $a = "x <? y" ?>', 1, 9, "Unclosed string")

    def test_unclosed_value_group_points_at_brace(self):
        self.assertError("<? $a = {x|y ", 1, 9, "Unclosed choice group")

    def test_close_marker_inside_value_group(self):
        self.assertError("<? $a = {x ?>", 1, 9, "Unclosed choice group")

    def test_open_marker_inside_value_group(self):
        self.assertError("<? $a = {x <? y} ?>", 1, 9, "Unclosed choice group")

    def test_nested_unclosed_value_group_points_at_outer_brace(self):
        self.assertError("<? $a = {x {y} ?>", 1, 9, "Unclosed choice group")

    def test_unclosed_comment_in_code(self):
        self.assertError("<?\n  /* never closed\n$a", 2, 3, "Unclosed comment")

    def test_bare_dollar_in_code(self):
        self.assertError("<? $ = 1 ?>", 1, 4, "variable name")

    def test_dollar_followed_by_digit_in_code(self):
        self.assertError("<? $5 ?>", 1, 4, "variable name")

    def test_single_quote(self):
        self.assertError("<? $a = 'x' ?>", 1, 9, "double quotes")

    def test_unexpected_character(self):
        self.assertError("<? $a = 5 ?>", 1, 9, "Unexpected character")

    def test_unexpected_character_on_later_line(self):
        self.assertError('<?\n$a = "x"\n  #\n?>', 3, 3, "Unexpected character")

    def test_lone_slash_in_code(self):
        self.assertError("<? / ?>", 1, 4, "Unexpected character")

    def test_value_group_error_inside_option(self):
        self.assertError('{a|<? $x = "y ?>}', 1, 12, "Unclosed string")

    def test_unclosed_brace_in_body_is_not_a_lexer_error(self):
        self.assertEqual([t.kind.name for t in lex("a {b")], ["TEXT", "GROUP_OPEN", "TEXT"])

    def test_error_class_is_syntax_error(self):
        with self.assertRaises(errors.PromptError):
            lex("<?")


class InputDialectTests(unittest.TestCase):
    def test_variable_syntax_is_text(self):
        self.assertEqual(kv(lex("a $name $variable_0 b", Dialect.INPUT)),
                         [("TEXT", "a $name $variable_0 b")])

    def test_block_opener_is_text(self):
        self.assertEqual(kv(lex("a <? $x = 1 ?> b", Dialect.INPUT)), [("TEXT", "a <? $x = 1 ?> b")])

    def test_unclosed_block_opener_does_not_raise(self):
        self.assertEqual(kv(lex("<?", Dialect.INPUT)), [("TEXT", "<?")])

    def test_escaped_open_marker_is_a_raw_escape(self):
        self.assertEqual(kv(lex(r"x\<?y", Dialect.INPUT)), [("TEXT", r"x\<?y")])

    def test_groups_comments_and_escapes_as_in_body(self):
        source = r"{a\|b|c} /* x */ d // e" + "\nf"
        self.assertEqual(
            kv(lex(source, Dialect.INPUT)),
            [("GROUP_OPEN", "{"), ("TEXT", r"a\|b"), ("PIPE", "|"), ("TEXT", "c"),
             ("GROUP_CLOSE", "}"), ("TEXT", "  d \nf")],
        )

    def test_input_matches_body_when_no_dollar_or_block(self):
        source = "{a|{b|c}} \\{ x /* c */ y // z\n \\\\| tail \\"
        self.assertEqual(lex(source, Dialect.INPUT), lex(source, Dialect.BODY))

    def test_never_emits_variable_or_block(self):
        tokens = lex("$a <? $b = {c} ?> {$d|<?}", Dialect.INPUT)
        self.assertFalse({t.kind for t in tokens} & {K.VARIABLE, K.BLOCK})

    def test_never_raises_for_random_input(self):
        rng = random.Random(7)
        alphabet = ["\\", "/", "*", "{", "}", "|", "$", "<", "?", ">", '"', "'", "a", " ", "\n", "=", ";"]
        for _ in range(2000):
            source = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
            lex(source, Dialect.INPUT)

    def test_no_standalone_stripping_is_needed(self):
        tokens = lex("a\n<? x ?>\nb", Dialect.INPUT)
        self.assertEqual(strip(tokens), tokens)


class EntryDialectTests(unittest.TestCase):
    def test_string_dialect_rejected(self):
        with self.assertRaises(ValueError):
            lex("abc", Dialect.STRING)

    def test_value_group_dialect_rejected(self):
        with self.assertRaises(ValueError):
            lex("{a}", Dialect.VALUE_GROUP)

    def test_non_dialect_rejected(self):
        with self.assertRaises(ValueError):
            lex("abc", "body")

    def test_default_dialect_is_body(self):
        self.assertEqual(lex("$a"), lex("$a", Dialect.BODY))


class TokenModelTests(unittest.TestCase):
    def test_token_is_frozen_and_slotted(self):
        token = Token(K.TEXT, "a", 0, 1)
        with self.assertRaises(Exception):
            token.value = "b"
        self.assertFalse(hasattr(token, "__dict__"))
        self.assertEqual(token.children, ())

    def test_token_kinds_present(self):
        self.assertEqual(
            {k.name for k in K},
            {"TEXT", "GROUP_OPEN", "PIPE", "GROUP_CLOSE", "VARIABLE", "BLOCK", "ASSIGN",
             "SEPARATOR", "WORD", "STRING"},
        )


class StandaloneLineTests(unittest.TestCase):
    """Blocks always survive the pass (they still run); only the layout around them goes."""

    def test_single_line_block_loses_its_line(self):
        self.assertEqual(stripped_text('a\n<? $x = "1" ?>\nb'), "a\n<B>b")

    def test_indented_block_loses_its_indentation(self):
        self.assertEqual(stripped_text('a\n \t<? $x = "1" ?> \t\nb'), "a\n<B>b")

    def test_crlf_line_break_removed(self):
        self.assertEqual(stripped_text('a\r\n<? $x = "1" ?>\r\nb'), "a\r\n<B>b")

    def test_block_at_start_of_text(self):
        self.assertEqual(stripped_text('<? $x = "1" ?>\nb'), "<B>b")

    def test_multi_line_block_is_one_unit(self):
        self.assertEqual(stripped_text('a\n<?\n$x = "1"\n$y = "2"\n?>\nb'), "a\n<B>b")

    def test_two_blocks_on_one_line(self):
        self.assertEqual(stripped_text('a\n<? $x = "1" ?> <? $y = "2" ?>\nb'), "a\n<B><B>b")

    def test_consecutive_block_lines(self):
        self.assertEqual(stripped_text('<? $x = "1" ?>\n<? $y = "2" ?>\nb'), "<B><B>b")

    def test_block_at_end_without_line_break(self):
        self.assertEqual(stripped_text('a\n<? $x = "1" ?>'), "a\n<B>")

    def test_block_alone_in_text(self):
        self.assertEqual(stripped_text('<? $x = "1" ?>'), "<B>")

    def test_block_with_trailing_comment(self):
        self.assertEqual(stripped_text('a\n<? $x = "1" ?> // set x\nb'), "a\n<B>b")

    def test_block_with_leading_block_comment(self):
        self.assertEqual(stripped_text('a\n/* set */ <? $x = "1" ?>\nb'), "a\n<B>b")

    def test_block_inside_multiline_option(self):
        tokens = strip(lex('{\n  <? $x = "1" ?>\n  red\n|blue}'))
        self.assertEqual(
            kv(tokens),
            [("GROUP_OPEN", "{"), ("TEXT", "\n"), ("BLOCK", '<? $x = "1" ?>'), ("TEXT", "  red\n"),
             ("PIPE", "|"), ("TEXT", "blue"), ("GROUP_CLOSE", "}")],
        )

    def test_block_after_group_opener_on_same_line_is_inline(self):
        tokens = strip(lex("{<? $x = {a} ?>\nred|b}"))
        self.assertEqual([t.kind.name for t in tokens][:3], ["GROUP_OPEN", "BLOCK", "TEXT"])
        self.assertEqual(tokens[2].value, "\nred")

    def test_inline_block_keeps_surrounding_text(self):
        self.assertEqual(stripped_text('a <? $x = "1" ?> b\nc'), "a <B> b\nc")

    def test_block_followed_by_text_is_inline(self):
        self.assertEqual(stripped_text('<? $x = "1" ?> b\nc'), "<B> b\nc")

    def test_block_after_variable_on_same_line_is_inline(self):
        tokens = strip(lex('$a <? $x = "1" ?>\nb'))
        self.assertEqual([t.kind.name for t in tokens], ["VARIABLE", "TEXT", "BLOCK", "TEXT"])
        self.assertEqual(tokens[3].value, "\nb")

    def test_comment_only_line_keeps_line_break(self):
        self.assertEqual(stripped_text("a\n// note\nb"), "a\n\nb")

    def test_comment_only_line_next_to_block_line(self):
        self.assertEqual(stripped_text('a\n// note\n<? $x = "1" ?>\nb'), "a\n\n<B>b")

    def test_text_without_blocks_is_unchanged(self):
        tokens = lex("a\n\n  b\n")
        self.assertEqual(strip(tokens), tokens)

    def test_whitespace_only_line_without_block_stays(self):
        self.assertEqual(stripped_text('a\n  \n<? $x = "1" ?>\nb'), "a\n  \n<B>b")

    def test_blank_line_after_block_line_stays(self):
        self.assertEqual(stripped_text('<? $x = "1" ?>\n\nb'), "<B>\nb")

    def test_text_around_removed_lines_is_merged(self):
        tokens = strip(lex('a\n<? $x = "1" ?>\nb'))
        self.assertEqual(kv(tokens), [("TEXT", "a\n"), ("BLOCK", '<? $x = "1" ?>'), ("TEXT", "b")])

    def test_blocks_are_never_lost(self):
        sources = [
            'a\n<? $x = "1" ?>\nb',
            '<? $x = "1" ?>',
            '  <? $x = "1" ?>  <? $y = "2" ?>  \r\n{a|\n <?\n$z = "3"\n?>\nb}',
            'a <? $x = "1" ?> b\n<? $y = "2" ?>',
            '<? $x = "1" ?>\n<? $y = "2" ?>\n<? $z = "3" ?>',
        ]
        for source in sources:
            before = [t for t in lex(source) if t.kind is K.BLOCK]
            after = [t for t in strip(lex(source)) if t.kind is K.BLOCK]
            self.assertEqual(after, before, source)

    def test_untouched_token_offsets_are_exact(self):
        tokens = strip(lex('<? $x = "1" ?>\n{a|b}'))
        self.assertEqual([(t.kind.name, t.offset) for t in tokens][:2], [("BLOCK", 0), ("GROUP_OPEN", 15)])

    def test_input_list_is_not_mutated(self):
        tokens = lex('a\n<? $x = "1" ?>\nb')
        before = list(tokens)
        strip(tokens)
        self.assertEqual(tokens, before)


if __name__ == "__main__":
    unittest.main()
