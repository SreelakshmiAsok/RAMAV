import os
import sys

# Ensure local tools (semgrep, node, ollama, pytest) are discovered in PATH
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_extra_paths = [
    os.path.dirname(sys.executable),
    os.path.join(_REPO_ROOT, ".venv", "bin"),
    os.path.expanduser("~/.local/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]
_current_path = os.environ.get("PATH", "")
_to_add = [p for p in _extra_paths if os.path.isdir(p) and p not in _current_path]
if _to_add:
    os.environ["PATH"] = ":".join(_to_add) + ":" + _current_path
