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

# TODO: ajuste estes seletores com os seletores reais do login da UpSeller.
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
DEFAULT_SUBMIT_SELECTORS = [
    "button[type='submit']",
    "button:has-text('Entrar')",
    "button:has-text('Login')",
    "input[type='submit']",
]
DEFAULT_CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[title*='captcha']",
    ".g-recaptcha",
    "#captcha",
    "[data-sitekey]",
    "span.inp_placeholder:has-text('CAPTCHA')",
    "button.code_btn.send_code_btn",
    "button.code_btn img[alt='CAPTCHA']",
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


def env_list(name: str, fallback: list[str]) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or fallback


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def first_visible_selector(page: Page, selectors: Iterable[str], timeout_ms: int = 2000) -> Optional[str]:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return selector
        except PlaywrightTimeoutError:
            continue
    return None


def fill_field(page: Page, selectors: list[str], value: str, label: str) -> str:
    selector = first_visible_selector(page, selectors)
    if not selector:
        raise RuntimeError(
            f"Nao foi possivel localizar campo de {label}. Ajuste os seletores no .env ou no codigo."
        )

    page.locator(selector).first.fill(value)
    log(f"Campo de {label} preenchido com seletor: {selector}")
    return selector


def click_submit(page: Page, selectors: list[str]) -> str:
    selector = first_visible_selector(page, selectors)
    if not selector:
        raise RuntimeError(
            "Nao foi possivel localizar botao de submit/login. Ajuste os seletores no .env ou no codigo."
        )

    page.locator(selector).first.click()
    log(f"Clique no submit usando seletor: {selector}")
    return selector


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


def captcha_present(page: Page, selectors: list[str]) -> bool:
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


def wait_for_login_success(
    page: Page,
    login_url: str,
    auth_marker_selector: Optional[str],
    username_selector: Optional[str],
    password_selector: Optional[str],
    captcha_selectors: list[str],
    post_login_blocking_selectors: list[str],
    post_login_blocking_url_keywords: list[str],
    timeout_ms: int = 120000,
) -> tuple[bool, str]:
    start = time.monotonic()
    manual_captcha_wait_done = False
    manual_blocking_wait_count = 0

    while (time.monotonic() - start) * 1000 < timeout_ms:
        current_url = page.url

        # CAPTCHA: nao burlar, apenas aguardar intervencao manual.
        if captcha_present(page, captcha_selectors) and not manual_captcha_wait_done:
            log("CAPTCHA detectado. Resolva manualmente no navegador.")
            input("Pressione ENTER aqui no terminal apos concluir o CAPTCHA e o login...")
            manual_captcha_wait_done = True

        blocking_reason = post_login_blocking_step_reason(
            page=page,
            blocking_selectors=post_login_blocking_selectors,
            blocking_url_keywords=post_login_blocking_url_keywords,
        )
        if blocking_reason:
            manual_blocking_wait_count += 1
            log(f"Etapa adicional apos login detectada ({blocking_reason}).")
            input("Conclua manualmente essa etapa no navegador e pressione ENTER para continuar...")
            page.wait_for_timeout(500)
            continue

        # 1) Presenca de elemento de area autenticada
        if auth_marker_selector and is_visible(page, auth_marker_selector):
            return True, f"Elemento autenticado visivel: {auth_marker_selector}"

        # 2) Mudanca de URL
        if current_url.rstrip("/") != login_url.rstrip("/"):
            return True, f"URL mudou de login para: {current_url}"

        # 3) Desaparecimento dos campos de login
        user_visible = is_visible(page, username_selector)
        pass_visible = is_visible(page, password_selector)
        if username_selector and password_selector and not user_visible and not pass_visible:
            return True, "Campos de login nao estao mais visiveis"

        page.wait_for_timeout(1000)

    if manual_blocking_wait_count > 0:
        return False, "Timeout aguardando concluir etapa adicional apos login (ex.: confirmacao de email)"
    return False, "Timeout aguardando confirmacao de login"


def save_error_screenshot(page: Page) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = ARTIFACTS_DIR / f"login_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    page.screenshot(path=str(file_path), full_page=True)
    return file_path


def main() -> int:
    load_dotenv()

    try:
        base_url = required_env("UPSELLER_BASE_URL")
        login_url = required_env("UPSELLER_LOGIN_URL")
        username = required_env("UPSELLER_USERNAME")
        password = required_env("UPSELLER_PASSWORD")
    except ValueError as exc:
        log(str(exc))
        return 1

    headful = bool_env("HEADFUL", default=True)
    auth_marker_selector = os.getenv("UPSELLER_AUTH_SUCCESS_SELECTOR", "").strip() or None
    captcha_selectors = env_list("UPSELLER_CAPTCHA_SELECTORS", DEFAULT_CAPTCHA_SELECTORS)
    post_login_blocking_selectors = env_list("UPSELLER_POST_LOGIN_BLOCKING_SELECTORS", [])
    post_login_blocking_url_keywords = env_list(
        "UPSELLER_POST_LOGIN_BLOCKING_URL_KEYWORDS",
        DEFAULT_POST_LOGIN_BLOCKING_URL_KEYWORDS,
    )

    username_selectors = env_list("UPSELLER_USERNAME_SELECTORS", DEFAULT_USERNAME_SELECTORS)
    password_selectors = env_list("UPSELLER_PASSWORD_SELECTORS", DEFAULT_PASSWORD_SELECTORS)
    submit_selectors = env_list("UPSELLER_SUBMIT_SELECTORS", DEFAULT_SUBMIT_SELECTORS)

    log("Iniciando POC de login UpSeller...")
    log(f"Base URL: {base_url}")
    log(f"Login URL: {login_url}")
    log(f"Modo headful: {headful}")
    if not auth_marker_selector:
        log(
            "Aviso: UPSELLER_AUTH_SUCCESS_SELECTOR nao definido; "
            "a validacao de sucesso usara sinais genericos (menos precisa)."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headful)
        context = browser.new_context()
        page = context.new_page()

        selected_username = None
        selected_password = None

        try:
            log("Abrindo pagina de login...")
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                log("Aviso: timeout em networkidle; seguindo com a pagina carregada.")

            selected_username = fill_field(page, username_selectors, username, "usuario")
            selected_password = fill_field(page, password_selectors, password, "senha")
            click_submit(page, submit_selectors)

            success, reason = wait_for_login_success(
                page=page,
                login_url=login_url,
                auth_marker_selector=auth_marker_selector,
                username_selector=selected_username,
                password_selector=selected_password,
                captcha_selectors=captcha_selectors,
                post_login_blocking_selectors=post_login_blocking_selectors,
                post_login_blocking_url_keywords=post_login_blocking_url_keywords,
                timeout_ms=180000,
            )

            if not success:
                raise RuntimeError(reason)

            context.storage_state(path=str(STORAGE_STATE_PATH))
            log(f"Login concluido com sucesso. Sessao salva em: {STORAGE_STATE_PATH}")
            return 0

        except Exception as exc:
            screenshot_path = save_error_screenshot(page)
            log(f"Falha no login: {exc}")
            log(f"Screenshot salva em: {screenshot_path}")
            return 1

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
