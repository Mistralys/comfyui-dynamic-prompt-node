# Synthesis: Prompt Preprocessor

### Outcome Summary

The Dynamic Prompt Text node gained a preprocessor language with code blocks, variables and optional connection-only variable_0 to variable_19 input sockets. The v1 character scanner was replaced by a lexer, parser, tree and evaluator package, and prompts without dollar-word text or code blocks resolve as in v1, proven by a differential test against a frozen oracle. All ten work packages passed every stage with 335 tests passing; the Autogrow min=0 rendering and the README wiring example remain unchecked in a running ComfyUI, and one rare backslash boundary parity deviation was accepted and documented.

### Metrics

- Work packages: 10 of 10 COMPLETE; all pipeline stages passed (0 missing).
- Tests: 335 passed, 0 failed at the final QA runs (32 at baseline; 71, 183, 241, 311, 330 as WPs landed).
- Security audit (WP-006): PASS, 0 Critical/High/Medium findings; 1 Low (deeply nested braces raise RecursionError).
- Code reviews: all PASS, 0 blocking issues.
- Rework: WP-003 had one implementation and one QA fail/rework cycle (strip_standalone_lines dropped BLOCK tokens); fixed and re-verified.
- Coverage percentage: not reported by any pipeline.

### Strategic Recommendations

- Frozen oracle pattern: copying the old resolver into tests/legacy_v1_resolver.py before deleting it turned the parity requirement into a differential test (3000 generated prompts, seeds 0-4). Never edit that file.
- Per-variable seeding via hashlib SHA-256 keyed by name and occurrence keeps body choices stable when headers change, and is stable across PYTHONHASHSEED values.
- Validate-all-then-resolve in the inputs handling gives atomic error behaviour and order-independent input streams (reusable pattern).
- Strict code, lenient text: errors in code blocks are line-numbered and raised, while body text keeps v1 leniency such as the literal unclosed brace.
- Raw output form until one final unescape pass is the invariant that preserves v1 escape quirks; Phase 2 comparisons must unescape both sides.
- The parser's named extension points (_parse_block, _parse_statement, shared container loop) and the evaluator's _eval dispatch are the intended seams for Phase 2 conditions.

### Code Insights

**Developer**
- WP-002: tests/_package_loader.py bridged the window where dynamic_prompt.py shadowed the package; it was meant to be deleted once the package had __init__.py but is still imported by four test modules.
- WP-002: UndefinedVariableError has a different constructor signature, so default pickling would fail; add __reduce__ if errors ever cross processes.
- WP-003: strip_standalone_lines gives approximate offsets to rejoined TEXT tokens that held dropped comments. An unclosed /* makes comment matching quadratic, as in v1.
- WP-004: stack-based unmatched-brace detection avoids exponential backtracking; the strict unclosed-group error position is innermost for some inputs and outermost for others.
- WP-005: tests/test_parity.py derives quirk inputs from ResolverTests via ast, so computed inputs would be missed.

**QA**
- WP-003 bug (fixed): standalone-line stripping lost BLOCK tokens; tests had asserted the wrong behaviour, so passing tests did not prove correctness.
- WP-004: no differential fuzz of parser against oracle for brace/pipe soup beyond WP-005 facade tests.
- WP-007: execute does not coerce non-string variable values; Autogrow min=0 rendering is untestable in unit tests.

**Reviewer**
- WP-006: two gold-nugget observations on the two-pass _resolve_inputs design.
- WP-005: accepted the backslash-lt-question boundary parity deviation as a rare documented edge rather than adding a lexer sentinel.

**Security Auditor**
- WP-006: low-priority RecursionError on deeply nested braces; no other findings.

**Release Engineer**
- WP-010: no git tags exist; 2.0.0 was derived from the newest changelog entry plus a major bump (pyproject previously said 1.1.0). Breaking change: dollar-word text now means a variable; use a backslash-escaped dollar for a literal.

### Deferred & Follow-Up Items

- **Out-of-scope (Phase 2, specified not implemented)**: conditions (if/elseif/else/endif/and/or/not) and helpers; keywords are reserved and raise "not supported yet". Source: plan, WP-004; Planner.
- **Deferred (manual check, high relevance before release)**: verify in a running ComfyUI the Autogrow min=0 rendering, the Mistralys_JsonString wiring example and the Rename Slot tip. Source: WP-007, WP-010; QA, Reviewer, Release Engineer, Documentation. The user tags and publishes; the changelog WIP marker stays until then.
- **Deferred (low)**: hint in the lexer/parser error for unquoted digit values (for example `$a=1`) that values must be quoted. Source: WP-003, WP-006; QA, Reviewer.
- **Deferred (low)**: make the strict unclosed-group error position consistently outermost. Source: WP-004; Developer. Currently recorded as a known inconsistency in the grammar doc.
- **Deferred (low)**: add __reduce__ to UndefinedVariableError if errors cross process boundaries. Source: WP-002; Developer.
- **Deferred (low)**: store per-piece offsets for rejoined TEXT tokens in strip_standalone_lines if later phases report errors at TEXT offsets. Source: WP-003; Developer.
- **Deferred (low)**: RecursionError on deeply nested braces could be turned into a PromptError. Source: WP-006; Security Auditor.
- **Deferred (low)**: broaden test_parity quirk extraction beyond literal ResolverTests inputs; add a test for non-ASCII input values and a double-backslash unescape case. Source: WP-005, WP-006, WP-002; QA.
- **Accepted deviation**: backslash-lt-question formed across a group or comment boundary now decodes to the literal text (pinned by a test, documented in grammar, manifest and changelog). Source: WP-005; Reviewer.
- **Deferred (housekeeping)**: tests/_package_loader.py was flagged temporary until WP-005 but is still imported by four test modules. Source: WP-002; Developer, Reviewer.

### Next Steps

1. Manually verify the Autogrow min=0 socket behaviour, the JsonString wiring example and the Rename Slot tip in a running ComfyUI, then finalize the changelog WIP marker and let the user tag v2.0.0.
2. tests/_package_loader.py was meant to be temporary but is still imported by test_foundation, test_lexer, test_parser and test_seeding; migrate those tests to plain package imports and delete it.
3. Plan Phase 2 (conditions and helpers) against docs/agents/project-manifest/preprocessor-grammar.md, extending _parse_block, _parse_statement and the evaluator dispatch.
4. Pending manual Knowledge Archiver run (the dispatch tool was unavailable): cwd_path = the repository root, project_storage_path = this plan folder.
5. Triage the low-priority error-message and robustness items above into a small hardening WP.
