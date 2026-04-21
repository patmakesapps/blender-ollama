"""Tiny HTTP listener inside Blender that runs AI-supplied Python on the main thread.

Used by the companion app's tool-calling flow. The companion POSTs to
http://127.0.0.1:8766/exec with {"code": "..."} and gets back
{"ok": bool, "output": "...", "error": "..."}.
"""

import contextlib
import io
import json
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bpy


EXEC_HOST = "127.0.0.1"
EXEC_PORT = 8766
EXEC_TIMEOUT_SECONDS = 45


def _run_on_main_thread(code, result, done):
    """Scheduled via bpy.app.timers. Executes code on Blender's main thread."""
    buf = io.StringIO()
    try:
        try:
            bpy.ops.ed.undo_push(message="AI: code execution")
        except Exception:
            pass
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(code, {"bpy": bpy, "__name__": "__ai_exec__"})
        result["ok"] = True
        result["output"] = buf.getvalue()
    except Exception:
        result["ok"] = False
        result["output"] = buf.getvalue()
        result["error"] = traceback.format_exc()
    finally:
        done.set()
    return None  # do not reschedule


class _ExecHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            return self._respond({"ok": True})
        self.send_error(404)

    def do_POST(self):
        if self.path != "/exec":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception as exc:
            return self._respond({"ok": False, "error": f"Bad JSON: {exc}"}, status=400)

        code = body.get("code", "")
        if not code.strip():
            return self._respond({"ok": False, "error": "Empty code block."})

        result = {}
        done = threading.Event()
        bpy.app.timers.register(
            lambda: _run_on_main_thread(code, result, done),
            first_interval=0.0,
        )
        if not done.wait(timeout=EXEC_TIMEOUT_SECONDS):
            return self._respond({"ok": False, "error": "Timed out waiting for Blender main thread."})
        self._respond(result)

    def _respond(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):
        return


_server = None
_thread = None


def start():
    global _server, _thread
    if _server is not None:
        return
    _server = ThreadingHTTPServer((EXEC_HOST, EXEC_PORT), _ExecHandler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()


def stop():
    global _server, _thread
    if _server is None:
        return
    try:
        _server.shutdown()
        _server.server_close()
    except Exception:
        pass
    _server = None
    _thread = None
