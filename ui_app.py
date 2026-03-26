from __future__ import annotations

import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from rpa.variant_runner import VariantJobInput, normalize_option_names, run_variant_job


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


def render_summary(success: bool, created: list[str], skipped: list[str], error_message: str | None) -> None:
    if success:
        st.success("Execução concluída com sucesso.")
    else:
        st.error("Execução finalizada com erro.")

    col1, col2 = st.columns(2)
    col1.metric("Opções criadas", len(created))
    col2.metric("Opções ignoradas", len(skipped))

    if created:
        st.write("Criadas:", created)
    if skipped:
        st.write("Ignoradas (duplicadas):", skipped)
    if error_message:
        st.write("Erro:", error_message)


def main() -> None:
    load_dotenv()

    st.set_page_config(page_title="UpSeller RPA", layout="wide")
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

        col1, col2, col3, col4 = st.columns(4)
        headful = col1.checkbox("Headful", value=bool_env("HEADFUL", default=True))
        maximize_window = col2.checkbox("Janela maximizada", value=bool_env("UPSELLER_MAXIMIZE_WINDOW", default=True))
        skip_variant_creation = col3.checkbox(
            "Pular criação da variante",
            value=bool_env("UPSELLER_SKIP_VARIANT_CREATION", default=False),
            help="Use quando a variante já existe e você quer apenas adicionar opções.",
        )
        action_timeout_ms = col4.number_input(
            "Timeout de ação (ms)",
            min_value=5000,
            max_value=120000,
            value=int(os.getenv("UPSELLER_ACTION_TIMEOUT_MS", "30000").strip() or "30000"),
            step=1000,
        )
        keep_browser_open = st.checkbox(
            "Manter navegador aberto após executar",
            value=bool_env("UPSELLER_KEEP_OPEN", default=False),
            help="Na UI, o navegador fica aberto por alguns segundos para inspeção visual.",
        )
        keep_open_seconds = st.number_input(
            "Tempo aberto para inspeção (s)",
            min_value=5,
            max_value=1800,
            value=int(os.getenv("UPSELLER_KEEP_OPEN_SECONDS", "90").strip() or "90"),
            step=5,
            disabled=not keep_browser_open,
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

        submit = st.form_submit_button("Executar RPA", use_container_width=True)

    if not submit:
        return

    options = normalize_option_names(option_names_raw)

    if not draft_url.strip():
        st.error("Preencha a URL do rascunho (DRAFT_URL).")
        return
    if not skip_variant_creation and not variant_name.strip():
        st.error("Preencha o nome da variante (VARIANT_NAME).")
        return
    if not options:
        st.error("Preencha OPTION_NAMES com ao menos 1 opção.")
        return

    logs: list[str] = []
    log_box = st.empty()

    def on_log(line: str) -> None:
        logs.append(line)
        log_box.code("\n".join(logs[-300:]), language="text")

    def wait_before_close(reason: str) -> None:
        if not keep_browser_open:
            return
        on_log(
            f"{reason} Navegador será mantido aberto por {int(keep_open_seconds)}s para inspeção."
        )
        time.sleep(int(keep_open_seconds))

    job_input = VariantJobInput(
        draft_url=draft_url.strip(),
        variant_name=variant_name.strip(),
        option_names=options,
        storage_state_path=storage_state_path,
        login_url=login_url,
        headful=headful,
        maximize_window=maximize_window,
        keep_browser_open=keep_browser_open,
        skip_variant_creation=skip_variant_creation,
        action_timeout_ms=int(action_timeout_ms),
        artifacts_dir=Path("artifacts"),
    )

    with st.spinner("Executando automação..."):
        result = run_variant_job(
            job_input,
            log_cb=on_log,
            wait_before_close_cb=wait_before_close if keep_browser_open else None,
        )

    st.subheader("Resultado")
    render_summary(
        success=result.success,
        created=result.created_options,
        skipped=result.skipped_options,
        error_message=result.error_message,
    )

    if result.screenshot_path:
        screenshot = Path(result.screenshot_path)
        if screenshot.exists():
            st.image(str(screenshot), caption=f"Screenshot de erro: {screenshot.name}")
        st.write("Caminho da screenshot:", result.screenshot_path)

    with st.expander("Detalhes (JSON)"):
        st.json(result.to_dict())


if __name__ == "__main__":
    main()
