from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from rpa.variant_runner import normalize_option_names

FORCED_HEADFUL = True
FORCED_MAXIMIZE_WINDOW = True
FORCED_KEEP_BROWSER_OPEN = True
FORCED_ACTION_TIMEOUT_MS = 40000


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def default_option_text() -> str:
    raw = os.getenv("UPSELLER_OPTION_NAMES", "").strip()
    if raw:
        return "\n".join(normalize_option_names(raw))

    fallback = os.getenv("UPSELLER_OPTION_NAME", "teste2").strip() or "teste2"
    return fallback


def render_summary(
    success: bool,
    created: list[str],
    skipped: list[str],
    described: list[str],
    error_message: str | None,
) -> None:
    if success:
        st.success("Execução concluída com sucesso.")
    else:
        st.error("Execução finalizada com erro.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Opções criadas", len(created))
    col2.metric("Opções ignoradas", len(skipped))
    col3.metric("Descrições aplicadas", len(described))

    if created:
        st.write("Criadas:", created)
    if skipped:
        st.write("Ignoradas (duplicadas):", skipped)
    if described:
        st.write("Com descrição aplicada:", described)
    if error_message:
        st.write("Erro:", error_message)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append_login_log(message: str) -> None:
    if "login_logs" not in st.session_state:
        st.session_state["login_logs"] = []
    st.session_state["login_logs"].append(f"[{_now()}] {message}")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return

    for _ in range(20):
        if not _is_pid_running(pid):
            return
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _wait_cdp_ready(cdp_url: str, timeout_seconds: int = 20) -> bool:
    deadline = time.monotonic() + timeout_seconds
    health_url = f"{cdp_url.rstrip('/')}/json/version"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.25)
            continue
    return False


def _current_login_worker() -> Optional[dict]:
    worker = st.session_state.get("login_worker")
    if not worker:
        return None

    pid = int(worker.get("pid", 0))
    if _is_pid_running(pid):
        return worker

    st.session_state["login_worker"] = None
    _append_login_log("Processo de login manual nao esta mais ativo.")
    return None


def _start_manual_login_worker(login_url: str, maximize_window: bool) -> None:
    login_url = login_url.strip()
    if not login_url:
        raise ValueError("Preencha a URL de login.")

    if _current_login_worker() is not None:
        raise RuntimeError("Ja existe um login assistido em andamento.")

    worker_script = Path(__file__).resolve().parent / "login_manual_worker.py"
    if not worker_script.exists():
        raise RuntimeError(f"Script de worker nao encontrado: {worker_script}")

    port = _find_free_port()
    cdp_url = f"http://127.0.0.1:{port}"

    cmd = [
        sys.executable,
        str(worker_script),
        "--login-url",
        login_url,
        "--cdp-port",
        str(port),
    ]
    if maximize_window:
        cmd.append("--maximize")

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    process = subprocess.Popen(
        cmd,
        cwd=str(worker_script.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    if not _wait_cdp_ready(cdp_url, timeout_seconds=20):
        _terminate_pid(process.pid)
        raise RuntimeError("Nao foi possivel iniciar o navegador de login (CDP indisponivel).")

    st.session_state["login_worker"] = {
        "pid": process.pid,
        "port": port,
        "cdp_url": cdp_url,
        "login_url": login_url,
        "maximize_window": maximize_window,
        "started_at": _now(),
    }
    _append_login_log(f"Login manual iniciado (PID={process.pid}, CDP={cdp_url}).")


def _save_storage_state_via_cdp(cdp_url: str, storage_state_path: Path) -> str:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        try:
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("Nenhum contexto ativo encontrado no navegador de login.")

            selected_context = contexts[0]
            selected_url = ""

            for context in contexts:
                for page in context.pages:
                    current_url = (page.url or "").strip()
                    if current_url and current_url != "about:blank":
                        selected_context = context
                        selected_url = current_url
                        break
                if selected_url:
                    break

            storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            selected_context.storage_state(path=str(storage_state_path))
            return selected_url
        finally:
            browser.close()


def _close_login_worker(log_message: Optional[str] = None) -> None:
    worker = st.session_state.get("login_worker")
    if worker:
        _terminate_pid(int(worker.get("pid", 0)))
    st.session_state["login_worker"] = None
    if log_message:
        _append_login_log(log_message)


def _start_variant_worker(payload: dict) -> None:
    worker_script = Path(__file__).resolve().parent / "variant_job_worker.py"
    if not worker_script.exists():
        raise RuntimeError(f"Script de worker nao encontrado: {worker_script}")

    artifacts_dir = Path(payload.get("artifacts_dir", "artifacts"))
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    request_path = artifacts_dir / f"variant_job_{job_id}_request.json"
    result_path = artifacts_dir / f"variant_job_{job_id}_result.json"
    log_path = artifacts_dir / f"variant_job_{job_id}.log"
    request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        str(worker_script),
        "--request",
        str(request_path),
        "--result",
        str(result_path),
        "--log",
        str(log_path),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    process = subprocess.Popen(
        cmd,
        cwd=str(worker_script.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    st.session_state["variant_worker"] = {
        "pid": process.pid,
        "request_path": str(request_path),
        "result_path": str(result_path),
        "log_path": str(log_path),
        "started_at": _now(),
        "cancelled": False,
    }


def _read_log_tail(log_path: Path, max_lines: int = 300) -> str:
    if not log_path.exists():
        return ""
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-max_lines:])


def _render_variant_worker_panel() -> None:
    worker = st.session_state.get("variant_worker")
    if not worker:
        return

    pid = int(worker.get("pid", 0))
    running = _is_pid_running(pid)
    log_path = Path(worker["log_path"])
    result_path = Path(worker["result_path"])

    st.subheader("Execução da Automação")
    if running:
        st.info(f"Automação em execução (PID {pid}).")
        auto_refresh = st.checkbox(
            "Atualizar logs automaticamente",
            value=True,
            key="variant_worker_auto_refresh",
        )
    elif worker.get("cancelled"):
        st.warning("Automação cancelada.")
        auto_refresh = False
    else:
        st.info("Automação finalizada.")
        auto_refresh = False

    log_text = _read_log_tail(log_path)
    if log_text:
        st.code(log_text, language="text")

    col1, col2 = st.columns(2)
    with col1:
        if running and st.button("Cancelar automação e fechar janela", key="cancel_variant_btn"):
            _terminate_pid(pid)
            worker["cancelled"] = True
            st.warning("Sinal de cancelamento enviado. A janela será fechada.")
            st.rerun()
    with col2:
        if st.button("Limpar status da automação", key="clear_variant_status_btn"):
            st.session_state["variant_worker"] = None
            st.rerun()

    if not running and result_path.exists() and not worker.get("cancelled"):
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            render_summary(
                success=bool(result.get("success")),
                created=list(result.get("created_options", [])),
                skipped=list(result.get("skipped_options", [])),
                described=list(result.get("described_options", [])),
                error_message=result.get("error_message"),
            )
            screenshot_path = result.get("screenshot_path")
            if screenshot_path:
                screenshot = Path(str(screenshot_path))
                if screenshot.exists():
                    st.image(str(screenshot), caption=f"Screenshot de erro: {screenshot.name}")
                st.write("Caminho da screenshot:", str(screenshot_path))
            with st.expander("Detalhes (JSON)"):
                st.json(result)
        except Exception as exc:
            st.error(f"Falha ao ler resultado da automação: {exc}")

    if running and auto_refresh:
        time.sleep(1)
        st.rerun()


def render_login_section(storage_state_path: Path, default_login_url: Optional[str]) -> None:
    if "login_worker" not in st.session_state:
        st.session_state["login_worker"] = None
    if "login_logs" not in st.session_state:
        st.session_state["login_logs"] = []

    st.subheader("Renovar Sessão (Login Manual)")
    st.caption("A UI abre o navegador. Você faz todo o login manualmente e clica em OK para salvar a sessão.")

    worker = _current_login_worker()

    with st.form("login_manual_form"):
        login_url = st.text_input(
            "URL de Login",
            value=(default_login_url or "").strip(),
            placeholder="https://app.upseller.com/login",
        )
        maximize_window = st.checkbox(
            "Abrir maximizado",
            value=bool_env("UPSELLER_MAXIMIZE_WINDOW", default=True),
        )

        start_login = st.form_submit_button(
            "Abrir navegador para login manual",
            use_container_width=True,
            disabled=worker is not None,
        )

    if start_login:
        try:
            _start_manual_login_worker(login_url=login_url, maximize_window=maximize_window)
            st.success("Navegador aberto. Faça o login manualmente e clique em OK para salvar a sessão.")
        except Exception as exc:
            _append_login_log(f"Falha ao iniciar login manual: {exc}")
            st.error(f"Falha ao iniciar login manual: {exc}")

    worker = _current_login_worker()
    if worker:
        st.info(
            f"Login manual em andamento (PID {worker['pid']}). "
            "Após autenticar no navegador, clique em OK."
        )
        btn_col1, btn_col2 = st.columns(2)
        confirm_ok = btn_col1.button(
            "OK, salvar sessão",
            type="primary",
            use_container_width=True,
        )
        cancel_login = btn_col2.button(
            "Cancelar e fechar navegador",
            use_container_width=True,
        )

        if confirm_ok:
            try:
                current_url = _save_storage_state_via_cdp(
                    cdp_url=str(worker["cdp_url"]),
                    storage_state_path=storage_state_path,
                )
                if current_url:
                    _append_login_log(f"Sessao salva com sucesso. URL atual: {current_url}")
                else:
                    _append_login_log("Sessao salva com sucesso.")
                st.success(f"Sessão salva com sucesso em {storage_state_path}")
                _close_login_worker("Processo de login manual finalizado e navegador encerrado.")
            except Exception as exc:
                _append_login_log(f"Falha ao salvar sessao: {exc}")
                st.error(f"Falha ao salvar sessão: {exc}")

        if cancel_login:
            _close_login_worker("Login manual cancelado pelo usuario. Navegador encerrado.")
            st.warning("Login manual cancelado.")

    logs = st.session_state.get("login_logs", [])
    if logs:
        st.code("\n".join(logs[-300:]), language="text")


def main() -> None:
    load_dotenv()

    st.set_page_config(page_title="UpSeller RPA", layout="wide")
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] > button[kind="primary"] {
            background-color: #16a34a;
            border-color: #16a34a;
            color: #ffffff;
        }
        div[data-testid="stButton"] > button[kind="primary"]:hover {
            background-color: #15803d;
            border-color: #15803d;
            color: #ffffff;
        }
        div[data-testid="stButton"] > button[kind="secondary"] {
            background-color: #dc2626;
            border-color: #dc2626;
            color: #ffffff;
        }
        div[data-testid="stButton"] > button[kind="secondary"]:hover {
            background-color: #b91c1c;
            border-color: #b91c1c;
            color: #ffffff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("UpSeller RPA - Variantes")
    st.caption("Fase 2: interface para executar automação de variações com sessão salva.")

    storage_state_path = Path(os.getenv("STORAGE_STATE_PATH", "storage_state.json").strip() or "storage_state.json")
    login_url = os.getenv("UPSELLER_LOGIN_URL", "").strip() or None

    st.info(f"Storage state em uso: {storage_state_path}")
    if not storage_state_path.exists():
        st.warning("storage_state.json não encontrado. Renove a sessão com login.py e session.py.")

    with st.form("variant_form"):
        draft_url = st.text_input(
            "URL do Rascunho",
            value=os.getenv("UPSELLER_DRAFT_URL", "").strip() or os.getenv("rascunho_url", "").strip(),
            placeholder="https://app.upseller.com/.../up-edit/...",
        )

        st.caption("Execução fixa: navegador visível, janela maximizada, timeout de ação 40000ms.")

        if "_skip_variant_creation_ui_initialized_v2" not in st.session_state:
            st.session_state["skip_variant_creation_ui"] = True
            st.session_state["_skip_variant_creation_ui_initialized_v2"] = True

        skip_variant_creation = st.checkbox(
            "Pular criação da variante",
            key="skip_variant_creation_ui",
            help="Marcado por padrão. Desmarque apenas se quiser criar a variante antes das opções.",
        )

        variant_name = st.text_input(
            "Nome da Variante",
            value=os.getenv("UPSELLER_VARIANT_NAME", "Cor").strip() or "Cor",
            help="Se 'Pular criação da variante' estiver ativo, este campo será ignorado.",
        )
        option_names_raw = st.text_area(
            "Opções",
            value=default_option_text(),
            height=120,
            help="Uma opção por linha (também aceita vírgula e ponto e vírgula).",
        )
        option_description_template = st.text_area(
            "Template da descrição das opções (opcional)",
            value=os.getenv("UPSELLER_OPTION_DESCRIPTION_TEMPLATE", "").strip(),
            height=90,
            placeholder="Descrição da opção {{OPTION_NAME}} xxxxxxxx",
            help="Use {{OPTION_NAME}} para injetar automaticamente o nome de cada opção.",
        )

        submit = st.form_submit_button("Executar RPA", use_container_width=True)

    if submit:
        running_worker = st.session_state.get("variant_worker")
        if running_worker and _is_pid_running(int(running_worker.get("pid", 0))):
            st.warning("Ja existe uma automação em execução. Cancele ou aguarde finalizar.")
            _render_variant_worker_panel()
            st.divider()
            render_login_section(storage_state_path=storage_state_path, default_login_url=login_url)
            return

        options = normalize_option_names(option_names_raw)

        if not draft_url.strip():
            st.error("Preencha a URL do rascunho (DRAFT_URL).")
        elif not skip_variant_creation and not variant_name.strip():
            st.error("Preencha o nome da variante (VARIANT_NAME).")
        elif not options:
            st.error("Preencha OPTION_NAMES com ao menos 1 opção.")
        else:
            payload = {
                "draft_url": draft_url.strip(),
                "variant_name": variant_name.strip(),
                "option_names": options,
                "storage_state_path": str(storage_state_path),
                "login_url": login_url,
                "headful": FORCED_HEADFUL,
                "maximize_window": FORCED_MAXIMIZE_WINDOW,
                "keep_browser_open": FORCED_KEEP_BROWSER_OPEN,
                "skip_variant_creation": skip_variant_creation,
                "option_description_template": option_description_template.strip() or None,
                "action_timeout_ms": FORCED_ACTION_TIMEOUT_MS,
                "artifacts_dir": "artifacts",
            }
            try:
                _start_variant_worker(payload)
                st.success("Automação iniciada. Use o botão vermelho para cancelar quando necessário.")
            except Exception as exc:
                st.error(f"Falha ao iniciar automação: {exc}")

    _render_variant_worker_panel()

    st.divider()
    render_login_section(storage_state_path=storage_state_path, default_login_url=login_url)


if __name__ == "__main__":
    main()
