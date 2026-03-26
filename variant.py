from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

ARTIFACTS_DIR = Path("artifacts")

VARIANT_TAB_SELECTORS = [
    "label.ant-radio-wrapper:has-text('Variantes')",
    "label:has-text('Variantes')",
]
ADD_VARIANT_SELECTORS = [
    "button:has-text('Adicionar Variante')",
]
VARIANT_INPUT_SELECTORS = [
    "input[placeholder='eg: Cor']",
]
ADD_OPTION_SELECTORS = [
    "button:has-text('Adicionar Opções')",
    "button:has-text('Adicionar Opcoes')",
]
OPTION_INPUT_SELECTORS = [
    "input[placeholder='eg: Vermelho']",
]
SAVE_BUTTON_SELECTORS = [
    "button.my_ant_btn_primary:has-text('Salvar')",
    "button.ant-btn-link.ant-btn-sm.my_ant_btn_primary:has-text('Salvar')",
    "button:has-text('Salvar')",
]


def log(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def wait_before_close_if_needed(keep_open: bool, message: str) -> None:
    if not keep_open:
        return
    log(message)
    input("Pressione ENTER para encerrar o navegador...")


def parse_option_names() -> list[str]:
    raw_list = os.getenv("UPSELLER_OPTION_NAMES", "").strip()
    if raw_list:
        normalized = raw_list.replace("\n", ",").replace(";", ",")
        values = [item.strip() for item in normalized.split(",") if item.strip()]
        if values:
            return values

    fallback = os.getenv("UPSELLER_OPTION_NAME", "teste2").strip() or "teste2"
    return [fallback]


def any_visible(page: Page, selectors: Iterable[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            continue

        for idx in range(count):
            try:
                if locator.nth(idx).is_visible():
                    return True
            except Exception:
                continue
    return False


def wait_until_none_visible(page: Page, selectors: Iterable[str], timeout_ms: int) -> bool:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < timeout_ms:
        if not any_visible(page, selectors):
            return True
        page.wait_for_timeout(200)
    return False


def first_visible_locator(page: Page, selectors: Iterable[str], timeout_ms: int) -> tuple[str, Locator]:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < timeout_ms:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue

            for idx in range(count):
                item: Locator = locator.nth(idx)
                try:
                    if item.is_visible():
                        return selector, item
                except Exception:
                    continue

        page.wait_for_timeout(300)

    raise RuntimeError(f"Nao encontrei elemento visivel para seletores: {list(selectors)}")


def click_first_visible(page: Page, selectors: list[str], timeout_ms: int, label: str) -> None:
    selector, locator = first_visible_locator(page, selectors, timeout_ms)
    locator.click()
    log(f"Clique em '{label}' usando seletor: {selector}")


def fill_first_visible(page: Page, selectors: list[str], value: str, timeout_ms: int, label: str) -> None:
    selector, locator = first_visible_locator(page, selectors, timeout_ms)
    locator.fill(value)
    log(f"Preenchido '{label}' com seletor: {selector}")


def ensure_variantes_selected(page: Page, timeout_ms: int) -> None:
    selector, wrapper = first_visible_locator(page, VARIANT_TAB_SELECTORS, timeout_ms)
    already_selected = False

    try:
        radio_input = wrapper.locator("input.ant-radio-input[value='1']").first
        if radio_input.count() > 0:
            already_selected = radio_input.is_checked()
    except Exception:
        already_selected = False

    if not already_selected:
        wrapper.click()
        log(f"Selecionada opcao 'Variantes' com seletor: {selector}")
    else:
        log("Opcao 'Variantes' ja estava selecionada.")

    # Aguarda o botao de adicionar variante ficar disponivel na secao correta.
    page.locator(ADD_VARIANT_SELECTORS[0]).first.wait_for(state="visible", timeout=timeout_ms)


def add_option(page: Page, option_name: str, timeout_ms: int) -> None:
    # Reabre o mini-modal para cada opcao, evitando corrida de estado entre um save e outro.
    click_first_visible(page, ADD_OPTION_SELECTORS, timeout_ms, "Adicionar Opcoes")
    fill_first_visible(page, OPTION_INPUT_SELECTORS, option_name, timeout_ms, "Nome da Opcao")
    click_first_visible(page, SAVE_BUTTON_SELECTORS, timeout_ms, "Salvar Opcao")
    page.locator(f"text={option_name}").first.wait_for(state="visible", timeout=timeout_ms)
    wait_until_none_visible(page, OPTION_INPUT_SELECTORS, timeout_ms=5000)
    log(f"Opcao adicionada com sucesso: {option_name}")


def save_error_screenshot(page: Optional[Page]) -> None:
    if not page:
        return
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = ARTIFACTS_DIR / f"variant_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(file_path), full_page=True)
        log(f"Screenshot salva em: {file_path}")
    except Exception as exc:
        log(f"Falha ao salvar screenshot: {exc}")


def main() -> int:
    load_dotenv()

    storage_state_path = Path(os.getenv("STORAGE_STATE_PATH", "storage_state.json").strip() or "storage_state.json")
    draft_url = os.getenv("UPSELLER_DRAFT_URL", "").strip() or os.getenv("rascunho_url", "").strip()
    if not draft_url:
        log("Defina UPSELLER_DRAFT_URL no .env (ou rascunho_url).")
        return 1

    if not storage_state_path.exists():
        log(f"Arquivo de sessao nao encontrado: {storage_state_path}")
        return 1

    variant_name = os.getenv("UPSELLER_VARIANT_NAME", "Cor").strip() or "Cor"
    option_names = parse_option_names()
    headful = bool_env("HEADFUL", default=True)
    keep_open = bool_env("UPSELLER_KEEP_OPEN", default=False)
    maximize_window = bool_env("UPSELLER_MAXIMIZE_WINDOW", default=True)
    action_timeout_ms = int(os.getenv("UPSELLER_ACTION_TIMEOUT_MS", "30000").strip() or "30000")

    log("Iniciando POC de variante...")
    log(f"Draft URL: {draft_url}")
    log(f"Modo headful: {headful}")
    log(f"Manter navegador aberto no fim: {keep_open}")
    log(f"Abrir janela maximizada: {maximize_window}")
    log(f"Opcoes para cadastrar: {option_names}")

    with sync_playwright() as playwright:
        page: Optional[Page] = None
        browser = None
        context = None

        try:
            launch_args: list[str] = []
            context_kwargs: dict = {"storage_state": str(storage_state_path)}

            if headful and maximize_window:
                launch_args.append("--start-maximized")
                context_kwargs["viewport"] = None

            browser = playwright.chromium.launch(headless=not headful, args=launch_args)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            page.goto(draft_url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                log("Aviso: timeout em networkidle; seguindo com a pagina carregada.")

            ensure_variantes_selected(page, action_timeout_ms)
            click_first_visible(page, ADD_VARIANT_SELECTORS, action_timeout_ms, "Adicionar Variante")
            fill_first_visible(page, VARIANT_INPUT_SELECTORS, variant_name, action_timeout_ms, "Nome da Variante")
            click_first_visible(page, SAVE_BUTTON_SELECTORS, action_timeout_ms, "Salvar Variante")

            for option_name in option_names:
                add_option(page, option_name, action_timeout_ms)

            log(f"POC concluida com sucesso. {len(option_names)} opcao(oes) cadastrada(s).")

            context.storage_state(path=str(storage_state_path))
            log(f"storage_state atualizado em: {storage_state_path}")
            wait_before_close_if_needed(
                keep_open=keep_open,
                message="Processo concluido. Navegador mantido aberto para inspecao.",
            )
            return 0

        except Exception as exc:
            log(f"Falha na POC de variante: {exc}")
            save_error_screenshot(page)
            wait_before_close_if_needed(
                keep_open=keep_open,
                message="Execucao com erro. Navegador mantido aberto para inspecao.",
            )
            return 1

        finally:
            if context:
                context.close()
            if browser:
                browser.close()


if __name__ == "__main__":
    sys.exit(main())
