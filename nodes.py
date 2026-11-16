from comfy_api.latest import io

from .dynamic_prompt import resolve_dynamic_prompt


class DynamicPromptTextNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Mistralys_DynamicPromptText",
            display_name="Dynamic Prompt Text",
            category="utils",
            description="Resolves {a|b|c} choices on the server and outputs the final prompt text.",
            search_aliases=["dynamic prompt", "wildcard", "random prompt", "prompt variation"],
            inputs=[
                io.String.Input("text", multiline=True, default="",
                    # Off on purpose: the browser must not resolve the text before the server does.
                    dynamic_prompts=False,
                    tooltip="Prompt text. Use {a|b|c} to pick one option per run. Groups can be nested.",
                ),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for the choices. The same text and seed always give the same result.",
                ),
            ],
            outputs=[
                io.String.Output("PROMPT",
                    tooltip="The prompt text with all choices resolved.",
                ),
            ],
        )

    @classmethod
    def execute(cls, text, seed):
        return io.NodeOutput(resolve_dynamic_prompt(text, seed))
