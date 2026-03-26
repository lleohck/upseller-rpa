from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

ARTIFACTS_DIR = Path("artifacts")


def log(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Variavel obrigatoria ausente: {name}")
    return value


def first_matching_page(context: BrowserContext, domain_hint: str) -> Optional[Page]:
    hint = domain_hint.lower().strip()
    for page in context.pages:
        try:
            if hint and hint in page.url.lower():
                return page
        except Exception:
            continue
    return context.pages[0] if context.pages else None


def save_error_screenshot(page: Optional[Page]) -> None:
    if not page:
        return
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = ARTIFACTS_DIR / f"extract_state_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(file_path), full_page=True)
        log(f"Screenshot salva em: {file_path}")
    except Exception as exc:
        log(f"Falha ao salvar screenshot: {exc}")


def main() -> int:
    load_dotenv()

    cdp_url = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222").strip()
    storage_state_path = Path(os.getenv("STORAGE_STATE_PATH", "storage_state.json").strip() or "storage_state.json")

    try:
        base_url = required_env("UPSELLER_BASE_URL")
    except ValueError as exc:
        log(str(exc))
        return 1

    target_url = os.getenv("UPSELLER_PROTECTED_URL", "").strip() or base_url
    auth_marker_selector = os.getenv("UPSELLER_AUTH_SUCCESS_SELECTOR", "").strip() or None

    log("Iniciando extracao de storage_state via Chrome CDP...")
    log(f"CDP URL: {cdp_url}")
    log(f"Target URL: {target_url}")
    log(f"Arquivo de saida: {storage_state_path}")

    with sync_playwright() as playwright:
        page: Optional[Page] = None

        try:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            if not browser.contexts:
                raise RuntimeError(
                    "Nenhum contexto encontrado no Chrome remoto. "
                    "Abra o Chrome com --remote-debugging-port=9222 e carregue pelo menos uma aba."
                )

            context = browser.contexts[0]
            page = first_matching_page(context, "upseller.com")
            if not page:
                page = context.new_page()

            log(f"Pagina selecionada: {page.url or 'about:blank'}")
            if not page.url or "upseller.com" not in page.url.lower():
                log("Navegando para URL alvo para garantir escopo da sessao...")
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                log("Aviso: timeout em networkidle; seguindo com a pagina carregada.")

            if auth_marker_selector:
                marker_visible = False
                try:
                    marker_visible = page.locator(auth_marker_selector).first.is_visible(timeout=3000)
                except Exception:
                    marker_visible = False

                if marker_visible:
                    log(f"Marcador de area logada detectado: {auth_marker_selector}")
                else:
                    log(
                        "Aviso: marcador de area logada nao encontrado nesta aba. "
                        "Ainda assim, o storage_state sera exportado."
                    )

            context.storage_state(path=str(storage_state_path))
            log("storage_state exportado com sucesso.")
            return 0

        except Exception as exc:
            log(f"Falha na extracao: {exc}")
            save_error_screenshot(page)
            return 1


if __name__ == "__main__":
    sys.exit(main())
