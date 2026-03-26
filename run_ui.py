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


def configure_playwright_browsers_path() -> None:
    if os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        return
    root = project_root()
    bundled = root / "ms-playwright"
    if bundled.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)


def configure_streamlit_runtime() -> None:
    defaults = {
        "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "false",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        "STREAMLIT_SERVER_PORT": "8501",
        "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def maybe_run_worker_mode(argv: list[str]) -> int | None:
    if not argv:
        return None

    worker_name: str | None = None
    worker_args: list[str] = []

    if argv[0] == "--worker" and len(argv) >= 2:
        worker_name = argv[1].strip().lower()
        worker_args = argv[2:]
    elif argv[0].startswith("--worker="):
        worker_name = argv[0].split("=", 1)[1].strip().lower()
        worker_args = argv[1:]
    else:
        return None

    if worker_name == "variant_job":
        from variant_job_worker import main as worker_main
    elif worker_name == "login_manual":
        from login_manual_worker import main as worker_main
    else:
        print(f"Worker invalido: {worker_name}")
        return 2

    sys.argv = [worker_name, *worker_args]
    return int(worker_main() or 0)


def run_frozen_streamlit(argv: list[str]) -> int:
    from streamlit.web import cli as stcli

    app_path = bundled_ui_app_path()
    if not app_path.exists():
        print(f"Erro: ui_app.py nao encontrado no bundle: {app_path}")
        return 1

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
        "--server.port=8501",
        "--server.address=127.0.0.1",
        *argv,
    ]
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
    configure_playwright_browsers_path()
    configure_streamlit_runtime()
    extra_args = sys.argv[1:]
    worker_exit = maybe_run_worker_mode(extra_args)
    if worker_exit is not None:
        return worker_exit
    if getattr(sys, "frozen", False):
        return run_frozen_streamlit(extra_args)
    return run_dev_streamlit(extra_args)


if __name__ == "__main__":
    raise SystemExit(main())
