"""Extension registration for ComfyUI Dynamic Prompt Node."""

from typing_extensions import override
from comfy_api.latest import ComfyExtension, io

from .nodes import DynamicPromptTextNode


class DynamicPromptExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [DynamicPromptTextNode]


async def comfy_entrypoint() -> DynamicPromptExtension:
    return DynamicPromptExtension()
