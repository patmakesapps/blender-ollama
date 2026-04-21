try:
    import ollama
except ImportError:
    ollama = None


SYSTEM_PROMPT = (
    "You are a Blender expert helping a 3D artist. "
    "Provide concise, technical, step-by-step guidance when useful."
)


def ask_ollama(prompt: str, scene_context: str, model_name: str) -> str:
    if ollama is None:
        raise RuntimeError(
            "The Python 'ollama' package is not available in Blender's Python "
            "environment. Install it before using this addon."
        )

    full_prompt = (
        f"Blender Scene Context:\n{scene_context}\n\n"
        f"User Question:\n{prompt}"
    )

    response = ollama.chat(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt},
        ],
    )

    if isinstance(response, dict):
        message = response.get("message", {})
        content = message.get("content")
        if content:
            return content

    raise RuntimeError("Ollama returned an unexpected response payload.")
