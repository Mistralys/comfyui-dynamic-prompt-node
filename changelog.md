# ComfyUI Dynamic Prompt Node - Changelog

## v2.0.0 - **WIP; UNRELEASED**
- New `<? ... ?>` code blocks with assignment: `<? $name = "..." ?>` and `<? $name = {a|b} ?>` define variables, resolved once.
- New `$name` interpolation inserts a variable anywhere in the prompt.
- New optional `variables` input: string sockets `variable_0` to `variable_19` that appear as you connect them, read as `$variable_N`. Unconnected sockets are empty; connected text is resolved with the plain `{a|b|c}` syntax.
- Per-variable seeding: each variable draws from its own stream derived from the seed and its name, so adding a variable does not change other picks.
- New escapes `\$` and `\<?` for a literal `$` and `<?`.
- Strict errors: an undefined variable or malformed block raises an error with line and column.
- Resolver rebuilt as the `dynamic_prompt/` package (lexer, parser, evaluator) replacing the v1 scanner. Prompts without `$` or `<?` resolve exactly as in v1, with one rare exception: a `\<?` formed across a group or comment boundary now decodes to `<?`.
- In-app help page lives in `js/docs/` (served through `WEB_DIRECTORY = "./js"`), where ComfyUI looks for it.
- **Breaking:** `$word` in existing prompts now means a variable. Write `\$word` for a literal dollar sign.

## v1.0.0
- Initial working release including tests and docs.
