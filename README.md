# Blender Ollama Chat

Blender addon that adds an `Ollama` panel to the 3D View sidebar so you can ask Blender questions with scene context included.

## What It Does

- Sends your prompt to an Ollama model from inside Blender.
- Includes the active object and selected object names in the prompt.
- Shows the latest response directly in the sidebar panel.
- Keeps a short in-session chat history.
- Lets you copy the latest response to the clipboard.

## Setup

1. Install Ollama from `https://ollama.com/`.
2. Pull at least one model, for example:

```bash
ollama pull llama3.2
```

3. Make sure the Ollama server is running.
4. Install the Python `ollama` package into Blender's Python environment.

Example on Windows:

```powershell
"C:\Program Files\Blender Foundation\Blender 3.6\3.6\python\bin\python.exe" -m pip install ollama
```

5. Install this folder as a Blender addon or place it in Blender's addons directory.
6. In Blender, open `View3D > Sidebar > Ollama`.

## Usage

1. Enter an Ollama model name, such as `llama3.2`.
2. Type a prompt. Longer prompts are supported.
3. Click `Send`.
4. Use `Copy Response` if you want the latest answer on your clipboard.

The addon passes a small amount of scene context with your question:

- Active object name
- Selected object names

## Notes

- Cloud or local models both work as long as the model name is valid for your Ollama setup.
- If Blender shows an import error for `ollama`, the Python package was installed into the wrong Python environment.
- This is currently a text-only assistant. It does not execute Blender actions or generate geometry.

## Packaging For Users

For the first public version, the simplest distribution path is:

1. Zip the addon folder so the zip contains `__init__.py` at the top level.
2. Publish the zip on GitHub Releases.
3. Tell users to install Ollama, pull a supported model, then use Blender's `Edit > Preferences > Add-ons > Install...` flow to select the zip.

If you want this to be easier for non-technical users later, the next improvements should be:

1. Add an addon Preferences panel for default model and Ollama host settings.
2. Add a connection test button.
3. Bundle a short first-run setup guide directly inside the panel.
