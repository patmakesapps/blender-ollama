import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import bpy
from bpy.types import Operator, Panel


COMPANION_URL = "http://127.0.0.1:8765"
COMPANION_TIMEOUT_SECONDS = 8


class OllamaChatPanel(Panel):
    bl_label = "Ollama Chat"
    bl_idname = "VIEW3D_PT_ollama_chat"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Ollama"

    def draw(self, context):
        layout = self.layout

        intro = layout.box()
        intro.label(text="Launch the companion chat app.")
        intro.label(text="The full chat experience runs outside Blender.")

        layout.operator("ollama.open_companion", icon="URL")

        notes = layout.box()
        notes.label(text="What it does:")
        notes.label(text="- Opens the premium chat UI in your browser")
        notes.label(text="- Sends scene context from Blender")
        notes.label(text="- Supports OpenAI and Ollama in one app")


class OllamaOpenCompanion(Operator):
    bl_idname = "ollama.open_companion"
    bl_label = "Open Assistant"
    bl_description = "Start the local companion app and open it in your browser"

    def execute(self, context):
        try:
            ensure_companion_server()
            push_scene_context(context)
            webbrowser.open(COMPANION_URL)
            self.report({"INFO"}, "Opened the Blender companion app.")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


def ensure_companion_server():
    if is_companion_running():
        return

    script_path = Path(__file__).resolve().parent / "companion" / "server.py"
    if not script_path.exists():
        raise RuntimeError(f"Companion server not found: {script_path}")

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        [sys.executable, str(script_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )

    deadline = time.time() + COMPANION_TIMEOUT_SECONDS
    while time.time() < deadline:
        if is_companion_running():
            return
        time.sleep(0.25)

    raise RuntimeError("The companion app did not start in time.")


def is_companion_running():
    try:
        with urllib.request.urlopen(f"{COMPANION_URL}/api/state", timeout=1):
            return True
    except Exception:
        return False


def push_scene_context(context):
    payload = json.dumps({"scene_context": get_scene_context(context)}).encode("utf-8")
    request = urllib.request.Request(
        f"{COMPANION_URL}/api/scene",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=3):
            return
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not send scene context to the companion app.") from exc


def get_scene_context(context):
    selected_names = [obj.name for obj in context.selected_objects]
    active_name = context.active_object.name if context.active_object else "None"
    object_count = len(context.scene.objects)
    mode = context.mode

    return {
        "scene_name": context.scene.name,
        "active_object": active_name,
        "selected_objects": selected_names,
        "object_count": object_count,
        "mode": mode,
    }


classes = (
    OllamaChatPanel,
    OllamaOpenCompanion,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
