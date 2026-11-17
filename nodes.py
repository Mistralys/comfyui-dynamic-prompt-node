from comfy_api.latest import io

from .dynamic_prompt import resolve_dynamic_prompt

# Number of "variable_N" sockets the node offers. Also the bound for the names the resolver knows,
# so a higher number such as $variable_20 is reported as an undefined variable, not silently empty.
MAX_INPUT_VARIABLES = 20
INPUT_VARIABLE_PREFIX = "variable_"


class DynamicPromptTextNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Mistralys_DynamicPromptText",
            display_name="Dynamic Prompt Text",
            category="utils",
            description=(
                "Resolves {a|b|c} choices on the server and outputs the final prompt text. "
                "Supports variables: set them with <? $name = ... ?>, use them as $name, "
                "and wire text into the variable sockets to read it as $variable_0, $variable_1, ..."
            ),
            search_aliases=["dynamic prompt", "wildcard", "random prompt", "prompt variation"],
            inputs=[
                io.String.Input("text", multiline=True, default="",
                    # Off on purpose: the browser must not resolve the text before the server does.
                    dynamic_prompts=False,
                    tooltip=(
                        "Prompt text. Use {a|b|c} to pick one option per run. Groups can be nested. "
                        "Define variables with <? $name = ... ?> and insert them with $name. "
                        "Connected variable sockets are available as $variable_N (N starts at 0)."
                    ),
                ),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for the choices. The same text and seed always give the same result.",
                ),
                io.Autogrow.Input("variables", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.String.Input("variable",
                            tooltip="Text made available to the prompt as $variable_N.",
                        ),
                        prefix=INPUT_VARIABLE_PREFIX,
                        min=0,
                        max=MAX_INPUT_VARIABLES,
                    ),
                    tooltip="Optional text inputs, available in the prompt as $variable_0, $variable_1, ...",
                ),
            ],
            outputs=[
                io.String.Output("PROMPT",
                    tooltip="The prompt text with all choices resolved.",
                ),
            ],
        )

    @classmethod
    def execute(cls, text, seed, variables=None):
        # ComfyUI passes only the connected slots (or nothing at all); the resolver gets every slot.
        connected = variables or {}
        inputs = {
            f"{INPUT_VARIABLE_PREFIX}{index}": connected.get(f"{INPUT_VARIABLE_PREFIX}{index}", "")
            for index in range(MAX_INPUT_VARIABLES)
        }
        return io.NodeOutput(resolve_dynamic_prompt(text, seed, inputs=inputs))
