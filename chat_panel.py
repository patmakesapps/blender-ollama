import bpy
from bpy.props import PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from .ollama_integration import ask_ollama


class OllamaChatProperties(PropertyGroup):
    prompt: StringProperty(
        name="Ask Ollama",
        description="Question to send to the Ollama model",
        default="",
        subtype="NONE",
        options={"TEXTEDIT_UPDATE"},
    )
    response: StringProperty(
        name="Response",
        description="Latest response returned by Ollama",
        default="",
    )
    model_name: StringProperty(
        name="Model",
        description="Ollama model name to use for chat requests",
        default="llama3.2",
    )
    history: StringProperty(
        name="History",
        description="Recent prompts and responses for this Blender session",
        default="",
    )


class OllamaChatPanel(Panel):
    bl_label = "Ollama Chat"
    bl_idname = "VIEW3D_PT_ollama_chat"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Ollama"

    def draw(self, context):
        layout = self.layout
        props = context.scene.ollama_chat

        layout.prop(props, "model_name")
        layout.label(text="Prompt:")
        layout.prop(props, "prompt", text="")

        actions = layout.row(align=True)
        actions.operator("ollama.chat_send", icon="PLAY")
        actions.operator("ollama.copy_response", icon="COPYDOWN")

        layout.label(text="Response:")
        response_box = layout.box()
        response_text = props.response or "No response yet."
        for line in response_text.splitlines() or ["No response yet."]:
            response_box.label(text=line)

        layout.label(text="Recent Chat:")
        history_box = layout.box()
        history_text = props.history or "No history yet."
        for line in history_text.splitlines() or ["No history yet."]:
            history_box.label(text=line)


class OllamaChatSend(Operator):
    bl_idname = "ollama.chat_send"
    bl_label = "Send"
    bl_description = "Send the current prompt and scene context to Ollama"

    def execute(self, context):
        props = context.scene.ollama_chat
        scene_context = get_scene_context(context)

        if not props.prompt.strip():
            self.report({"WARNING"}, "Enter a prompt before sending.")
            return {"CANCELLED"}

        try:
            response = ask_ollama(
                prompt=props.prompt,
                scene_context=scene_context,
                model_name=props.model_name,
            )
            append_history(props, props.prompt, response)
            props.response = response
            props.prompt = ""
            return {"FINISHED"}
        except Exception as exc:
            props.response = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class OllamaCopyResponse(Operator):
    bl_idname = "ollama.copy_response"
    bl_label = "Copy Response"
    bl_description = "Copy the latest Ollama response to the clipboard"

    def execute(self, context):
        response = context.scene.ollama_chat.response.strip()
        if not response:
            self.report({"WARNING"}, "There is no response to copy.")
            return {"CANCELLED"}

        context.window_manager.clipboard = response
        self.report({"INFO"}, "Response copied to clipboard.")
        return {"FINISHED"}


def get_scene_context(context):
    selected_names = [obj.name for obj in context.selected_objects]
    active_name = context.active_object.name if context.active_object else "None"
    return f"Active object: {active_name}\nSelected objects: {selected_names}"


def append_history(props, prompt, response):
    new_entry = f"You: {prompt}\nOllama: {response}"
    entries = [entry for entry in props.history.split("\n---\n") if entry.strip()]
    entries.append(new_entry)
    props.history = "\n---\n".join(entries[-5:])


classes = (
    OllamaChatProperties,
    OllamaChatPanel,
    OllamaChatSend,
    OllamaCopyResponse,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ollama_chat = PointerProperty(type=OllamaChatProperties)


def unregister():
    del bpy.types.Scene.ollama_chat
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
