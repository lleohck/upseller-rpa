from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

ARTIFACTS_DIR = Path("artifacts")
STORAGE_STATE_PATH = Path("storage_state.json")

DEFAULT_USERNAME_SELECTORS = [
    "input[name='username']",
    "input[name='email']",
    "input[type='email']",
    "input[autocomplete='username']",
]
DEFAULT_PASSWORD_SELECTORS = [
    "input[name='password']",
    "input[type='password']",
    "input[autocomplete='current-password']",
]
DEFAULT_POST_LOGIN_BLOCKING_URL_KEYWORDS = [
    "verification",
    "verify-email",
    "confirm-email",
    "email-confirm",
    "confirmacao-email",
    "validar-email",
]


def log(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Variavel obrigatoria ausente: {name}")
    return value


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_list(name: str, fallback: list[str]) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or fallback


def is_visible(page: Page, selector: Optional[str]) -> bool:
    if not selector:
        return False
    locator = page.locator(selector).first
    try:
        if locator.count() == 0:
            return False
        return locator.is_visible()
    except Exception:
        return False


def any_visible(page: Page, selectors: Iterable[str]) -> bool:
    for selector in selectors:
        if is_visible(page, selector):
            return True
    return False


def url_contains_keyword(url: str, keywords: Iterable[str]) -> Optional[str]:
    normalized = url.lower()
    for keyword in keywords:
        clean = keyword.strip().lower()
        if clean and clean in normalized:
            return clean
    return None


def post_login_blocking_step_reason(
    page: Page,
    blocking_selectors: list[str],
    blocking_url_keywords: list[str],
) -> Optional[str]:
    for selector in blocking_selectors:
        if is_visible(page, selector):
            return f"elemento bloqueante visivel: {selector}"

    keyword = url_contains_keyword(page.url, blocking_url_keywords)
    if keyword:
        return f"url contem palavra de etapa pendente: {keyword}"

    return None


def wait_for_session_validation(
    page: Page,
    login_url: str,
    auth_marker_selector: Optional[str],
    username_selectors: list[str],
    password_selectors: list[str],
    blocking_selectors: list[str],
    blocking_url_keywords: list[str],
    timeout_ms: int = 90000,
) -> tuple[bool, str]:
    start = time.monotonic()

    while (time.monotonic() - start) * 1000 < timeout_ms:
        current_url = page.url

        blocking_reason = post_login_blocking_step_reason(
            page=page,
            blocking_selectors=blocking_selectors,
            blocking_url_keywords=blocking_url_keywords,
        )
        if blocking_reason:
            log(f"Etapa adicional detectada ({blocking_reason}).")
            input("Conclua manualmente essa etapa no navegador e pressione ENTER para continuar...")
            page.wait_for_timeout(500)
            continue

        if auth_marker_selector and is_visible(page, auth_marker_selector):
            return True, f"Elemento autenticado visivel: {auth_marker_selector}"

        login_fields_visible = any_visible(page, username_selectors) or any_visible(page, password_selectors)
        if current_url.rstrip("/") == login_url.rstrip("/") and login_fields_visible:
            return False, "Sessao invalida/expirada: voltou para tela de login"

        if current_url.rstrip("/") != login_url.rstrip("/") and not login_fields_visible:
            return True, f"Sessao reutilizada com sucesso em: {current_url}"

        page.wait_for_timeout(1000)

    return False, "Timeout validando sessao autenticada"


def save_error_screenshot(page: Page) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = ARTIFACTS_DIR / f"session_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    page.screenshot(path=str(file_path), full_page=True)
    return file_path


def main() -> int:
    load_dotenv()

    try:
        base_url = required_env("UPSELLER_BASE_URL")
        login_url = required_env("UPSELLER_LOGIN_URL")
    except ValueError as exc:
        log(str(exc))
        return 1

    protected_url = os.getenv("UPSELLER_PROTECTED_URL", "").strip() or base_url
    headful = bool_env("HEADFUL", default=True)
    auth_marker_selector = os.getenv("UPSELLER_AUTH_SUCCESS_SELECTOR", "").strip() or None

    username_selectors = env_list("UPSELLER_USERNAME_SELECTORS", DEFAULT_USERNAME_SELECTORS)
    password_selectors = env_list("UPSELLER_PASSWORD_SELECTORS", DEFAULT_PASSWORD_SELECTORS)
    blocking_selectors = env_list("UPSELLER_POST_LOGIN_BLOCKING_SELECTORS", [])
    blocking_url_keywords = env_list(
        "UPSELLER_POST_LOGIN_BLOCKING_URL_KEYWORDS",
        DEFAULT_POST_LOGIN_BLOCKING_URL_KEYWORDS,
    )

    if not STORAGE_STATE_PATH.exists():
        log(f"Arquivo de sessao nao encontrado: {STORAGE_STATE_PATH}")
        log("Execute primeiro o login.py para gerar o storage_state.json")
        return 1

    log("Iniciando POC de reuso de sessao...")
    log(f"Storage state: {STORAGE_STATE_PATH}")
    log(f"Protected URL: {protected_url}")
    log(f"Modo headful: {headful}")
    if not auth_marker_selector:
        log(
            "Aviso: UPSELLER_AUTH_SUCCESS_SELECTOR nao definido; "
            "a validacao de sucesso usara sinais genericos (menos precisa)."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headful)
        context = browser.new_context(storage_state=str(STORAGE_STATE_PATH))
        page = context.new_page()

        try:
            log("Abrindo pagina protegida com sessao salva...")
            page.goto(protected_url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                log("Aviso: timeout em networkidle; seguindo com a pagina carregada.")

            success, reason = wait_for_session_validation(
                page=page,
                login_url=login_url,
                auth_marker_selector=auth_marker_selector,
                username_selectors=username_selectors,
                password_selectors=password_selectors,
                blocking_selectors=blocking_selectors,
                blocking_url_keywords=blocking_url_keywords,
                timeout_ms=90000,
            )

            if not success:
                raise RuntimeError(reason)

            # Salva novamente para manter cookies/estado atualizados.
            context.storage_state(path=str(STORAGE_STATE_PATH))
            log(f"Sessao valida. storage_state atualizado em: {STORAGE_STATE_PATH}")
            return 0

        except Exception as exc:
            screenshot_path = save_error_screenshot(page)
            log(f"Falha na validacao de sessao: {exc}")
            log(f"Screenshot salva em: {screenshot_path}")
            return 1

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
