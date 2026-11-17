"""Static checks on the dynamic_prompt package source."""
import ast
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.join(REPO, "dynamic_prompt")


def package_trees():
    for name in sorted(os.listdir(PACKAGE_DIR)):
        if name.endswith(".py"):
            with open(os.path.join(PACKAGE_DIR, name), encoding="utf-8") as handle:
                yield name, ast.parse(handle.read())


class HygieneTests(unittest.TestCase):
    def test_old_module_removed(self):
        self.assertFalse(os.path.exists(os.path.join(REPO, "dynamic_prompt.py")))
        self.assertTrue(os.path.isfile(os.path.join(PACKAGE_DIR, "__init__.py")))

    def test_stdlib_only_imports(self):
        seen = 0
        for name, tree in package_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:
                        continue
                    modules = [node.module]
                else:
                    continue
                for module in modules:
                    seen += 1
                    self.assertIn(module.split(".")[0], sys.stdlib_module_names, f"{name}: {module}")
        self.assertGreater(seen, 0)

    def test_no_dynamic_code_execution(self):
        banned = {"eval", "exec", "compile"}
        for name, tree in package_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Only the builtins: re.compile() is a method call and is fine.
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, banned, f"{name}:{node.lineno}")

    def test_facade_exports(self):
        sys.path.insert(0, REPO)
        import dynamic_prompt

        self.assertEqual(
            dynamic_prompt.__all__,
            ["resolve_dynamic_prompt", "PromptError", "PromptSyntaxError", "UndefinedVariableError", "INPUT_VARIABLE"],
        )
        for name in dynamic_prompt.__all__:
            self.assertTrue(hasattr(dynamic_prompt, name), name)
        self.assertIn("raw output form", dynamic_prompt.__doc__.lower())
        self.assertIn("pipeline", dynamic_prompt.__doc__.lower())


if __name__ == "__main__":
    unittest.main()
