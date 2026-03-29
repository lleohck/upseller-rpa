from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_virtualenv_active() -> bool:
    if os.getenv("VIRTUAL_ENV"):
        return True
    return getattr(sys, "base_prefix", sys.prefix) != sys.prefix


def project_root() -> Path:
    return Path(__file__).resolve().parent


def find_python(root: Path) -> Path | None:
    if is_virtualenv_active():
        return Path(sys.executable)

    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def configure_streamlit_runtime() -> None:
    defaults = {
        "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "false",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        "STREAMLIT_SERVER_PORT": "8501",
        "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",
        "STREAMLIT_SERVER_HEADLESS": "true",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def run_streamlit(argv: list[str]) -> int:
    root = project_root()
    ui_app = root / "ui_app.py"
    python_exe = find_python(root)

    if not python_exe:
        print("Nenhum Python de projeto encontrado.")
        print("Crie/ative o .venv e instale dependencias:")
        print("  python3 -m venv .venv")
        print("  source .venv/bin/activate  # Linux/mac")
        print("  .venv\\Scripts\\activate   # Windows")
        print("  pip install -r requirements.txt")
        return 1

    if not ui_app.exists():
        print(f"ui_app.py nao encontrado em: {ui_app}")
        return 1

    env = os.environ.copy()
    env["UPSELLER_PYTHON_EXE"] = str(python_exe)

    cmd = [str(python_exe), "-m", "streamlit", "run", str(ui_app), *argv]
    return subprocess.call(cmd, cwd=str(root), env=env)


def main() -> int:
    configure_streamlit_runtime()
    return run_streamlit(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
