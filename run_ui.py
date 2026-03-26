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
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_ui_app_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", project_root()))
    return base / "ui_app.py"


def find_python_for_dev(root: Path) -> Path | None:
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


def run_frozen_streamlit(argv: list[str]) -> int:
    from streamlit.web import cli as stcli

    app_path = bundled_ui_app_path()
    if not app_path.exists():
        print(f"Erro: ui_app.py nao encontrado no bundle: {app_path}")
        return 1

    sys.argv = ["streamlit", "run", str(app_path), *argv]
    exit_code = stcli.main()
    return int(exit_code or 0)


def run_dev_streamlit(argv: list[str]) -> int:
    root = project_root()
    ui_app = root / "ui_app.py"
    python_exe = find_python_for_dev(root)

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

    cmd = [str(python_exe), "-m", "streamlit", "run", str(ui_app), *argv]
    return subprocess.call(cmd, cwd=str(root))


def main() -> int:
    extra_args = sys.argv[1:]
    if getattr(sys, "frozen", False):
        return run_frozen_streamlit(extra_args)
    return run_dev_streamlit(extra_args)


if __name__ == "__main__":
    raise SystemExit(main())
