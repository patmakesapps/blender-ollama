bl_info = {
    "name": "Ollama Chat Assistant",
    "author": "Patrick Kearney",
    "version": (0, 7, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Ollama",
    "description": "Launch a companion assistant app from inside Blender",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

from . import chat_panel


def register():
    chat_panel.register()


def unregister():
    chat_panel.unregister()


if __name__ == "__main__":
    register()
