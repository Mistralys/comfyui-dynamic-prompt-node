"""Loads the dynamic_prompt/ package directory under another name.

While the v1 module dynamic_prompt.py still exists next to the package directory,
`import dynamic_prompt.errors` resolves to the module and fails. Registering the directory
as a package called `dynamic_prompt_new` makes its relative imports work regardless.
"""
import importlib
import os
import sys
from types import ModuleType

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_NAME = "dynamic_prompt_new"


def load_submodule(name):
    """Import dynamic_prompt/<name>.py as dynamic_prompt_new.<name>."""
    if PACKAGE_NAME not in sys.modules:
        package = ModuleType(PACKAGE_NAME)
        package.__path__ = [os.path.join(REPO, "dynamic_prompt")]
        sys.modules[PACKAGE_NAME] = package
    return importlib.import_module(f"{PACKAGE_NAME}.{name}")
