from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

LogCallback = Callable[[str], None]
WaitBeforeCloseCallback = Callable[[str], None]

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
LOGIN_USERNAME_SELECTORS = [
    "input[name='username']",
    "input[name='email']",
    "input[type='email']",
    "input[autocomplete='username']",
]
LOGIN_PASSWORD_SELECTORS = [
    "input[name='password']",
    "input[type='password']",
    "input[autocomplete='current-password']",
]


@dataclass
class VariantJobInput:
    draft_url: str
    variant_name: str
    option_names: list[str]
    storage_state_path: Path = Path("storage_state.json")
    login_url: Optional[str] = None
    headful: bool = True
    maximize_window: bool = True
    keep_browser_open: bool = False
    skip_variant_creation: bool = False
    action_timeout_ms: int = 30000
    artifacts_dir: Path = Path("artifacts")


@dataclass
class VariantJobResult:
    success: bool
    created_options: list[str] = field(default_factory=list)
    skipped_options: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    log_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "created_options": self.created_options,
            "skipped_options": self.skipped_options,
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "log_lines": self.log_lines,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def normalize_option_names(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        normalized = raw.replace("\n", ",").replace(";", ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]

    values: list[str] = []
    for item in raw:
        clean = str(item).strip()
        if clean:
            values.append(clean)
    return values


def run_variant_job(
    job_input: VariantJobInput,
    log_cb: Optional[LogCallback] = None,
    wait_before_close_cb: Optional[WaitBeforeCloseCallback] = None,
) -> VariantJobResult:
    result = VariantJobResult(success=False)

    def log(message: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{now}] {message}"
        result.log_lines.append(line)
        if log_cb:
            log_cb(line)

    def maybe_wait_before_close(reason: str) -> None:
        if not job_input.keep_browser_open or not job_input.headful:
            return
        if not wait_before_close_cb:
            log(
                "Aviso: UPSELLER_KEEP_OPEN=true, mas sem callback de espera. "
                "O navegador sera fechado automaticamente."
            )
            return
        try:
            wait_before_close_cb(reason)
        except Exception as exc:
            log(f"Aviso: falha na espera antes de fechar navegador: {exc}")

    try:
        _validate_input(job_input)
    except ValueError as exc:
        result.error_message = str(exc)
        log(result.error_message)
        return result

    if not job_input.storage_state_path.exists():
        result.error_message = (
            f"Arquivo de sessao nao encontrado: {job_input.storage_state_path}. "
            "Renove a sessao executando login.py e session.py."
        )
        log(result.error_message)
        return result

    log("Iniciando execucao de variante...")
    log(f"Draft URL: {job_input.draft_url}")
    log(f"Opcoes solicitadas: {job_input.option_names}")

    with sync_playwright() as playwright:
        page: Optional[Page] = None
        browser = None
        context = None

        try:
            launch_args: list[str] = []
            context_kwargs: dict = {"storage_state": str(job_input.storage_state_path)}

            if job_input.headful and job_input.maximize_window:
                launch_args.append("--start-maximized")
                context_kwargs["viewport"] = None

            browser = playwright.chromium.launch(headless=not job_input.headful, args=launch_args)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            if job_input.headful and job_input.maximize_window:
                _maximize_browser_window(page, log)

            page.goto(job_input.draft_url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                log("Aviso: timeout em networkidle; seguindo com a pagina carregada.")

            if _session_invalid(page, job_input.login_url):
                result.error_message = (
                    "Sessao invalida/expirada. Renove o storage_state executando login.py e session.py."
                )
                log(result.error_message)
                maybe_wait_before_close("Sessao invalida detectada.")
                return result

            _ensure_variantes_selected(page, job_input.action_timeout_ms, log)

            if job_input.skip_variant_creation:
                log("Configurado para pular criacao da variante e seguir direto para opcoes.")
            else:
                _click_first_visible(page, ADD_VARIANT_SELECTORS, job_input.action_timeout_ms, "Adicionar Variante", log)
                _fill_first_visible(
                    page,
                    VARIANT_INPUT_SELECTORS,
                    job_input.variant_name,
                    job_input.action_timeout_ms,
                    "Nome da Variante",
                    log,
                )
                _click_first_visible(page, SAVE_BUTTON_SELECTORS, job_input.action_timeout_ms, "Salvar Variante", log)

            for option_name in job_input.option_names:
                if _option_already_exists(page, option_name):
                    result.skipped_options.append(option_name)
                    log(f"Opcao ja existente, ignorando: {option_name}")
                    continue

                _add_option(page, option_name, job_input.action_timeout_ms, log)
                result.created_options.append(option_name)

            context.storage_state(path=str(job_input.storage_state_path))
            log(f"storage_state atualizado em: {job_input.storage_state_path}")

            result.success = True
            log(
                "Execucao concluida. "
                f"Criadas: {len(result.created_options)} | Ignoradas: {len(result.skipped_options)}"
            )
            maybe_wait_before_close("Execucao concluida com sucesso.")
            return result

        except Exception as exc:
            result.error_message = str(exc)
            log(f"Falha na execucao: {exc}")
            screenshot_path = _save_error_screenshot(page, job_input.artifacts_dir)
            if screenshot_path:
                result.screenshot_path = str(screenshot_path)
                log(f"Screenshot salva em: {screenshot_path}")
            maybe_wait_before_close("Execucao finalizada com erro.")
            return result

        finally:
            if context:
                context.close()
            if browser:
                browser.close()


def _validate_input(job_input: VariantJobInput) -> None:
    if not job_input.draft_url.strip():
        raise ValueError("DRAFT_URL obrigatoria.")
    if not job_input.draft_url.startswith("http"):
        raise ValueError("DRAFT_URL deve iniciar com http/https.")
    if not job_input.skip_variant_creation and not job_input.variant_name.strip():
        raise ValueError("VARIANT_NAME obrigatoria.")

    normalized = normalize_option_names(job_input.option_names)
    if not normalized:
        raise ValueError("OPTION_NAMES obrigatoria (ao menos 1 opcao).")

    job_input.option_names = normalized


def _session_invalid(page: Page, login_url: Optional[str]) -> bool:
    user_visible = _any_visible(page, LOGIN_USERNAME_SELECTORS)
    pass_visible = _any_visible(page, LOGIN_PASSWORD_SELECTORS)

    if login_url:
        if page.url.rstrip("/") == login_url.rstrip("/") and user_visible and pass_visible:
            return True

    return user_visible and pass_visible


def _option_already_exists(page: Page, option_name: str) -> bool:
    locator = page.get_by_text(option_name, exact=True)
    try:
        count = locator.count()
    except Exception:
        return False

    for idx in range(count):
        item = locator.nth(idx)
        try:
            if item.is_visible():
                return True
        except Exception:
            continue
    return False


def _add_option(page: Page, option_name: str, timeout_ms: int, log: LogCallback) -> None:
    _click_first_visible(page, ADD_OPTION_SELECTORS, timeout_ms, "Adicionar Opcoes", log)
    _fill_first_visible(page, OPTION_INPUT_SELECTORS, option_name, timeout_ms, "Nome da Opcao", log)
    _click_first_visible(page, SAVE_BUTTON_SELECTORS, timeout_ms, "Salvar Opcao", log)
    page.get_by_text(option_name, exact=True).first.wait_for(state="visible", timeout=timeout_ms)
    _wait_until_none_visible(page, OPTION_INPUT_SELECTORS, timeout_ms=5000)
    log(f"Opcao adicionada com sucesso: {option_name}")


def _save_error_screenshot(page: Optional[Page], artifacts_dir: Path) -> Optional[Path]:
    if not page:
        return None
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        file_path = artifacts_dir / f"variant_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(file_path), full_page=True)
        return file_path
    except Exception:
        return None


def _wait_until_none_visible(page: Page, selectors: Iterable[str], timeout_ms: int) -> bool:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < timeout_ms:
        if not _any_visible(page, selectors):
            return True
        page.wait_for_timeout(200)
    return False


def _any_visible(page: Page, selectors: Iterable[str]) -> bool:
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


def _first_visible_locator(page: Page, selectors: Iterable[str], timeout_ms: int) -> tuple[str, Locator]:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < timeout_ms:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue

            for idx in range(count):
                item = locator.nth(idx)
                try:
                    if item.is_visible():
                        return selector, item
                except Exception:
                    continue

        page.wait_for_timeout(300)

    raise RuntimeError(f"Nao encontrei elemento visivel para seletores: {list(selectors)}")


def _click_first_visible(
    page: Page,
    selectors: list[str],
    timeout_ms: int,
    label: str,
    log: LogCallback,
) -> None:
    selector, locator = _first_visible_locator(page, selectors, timeout_ms)
    locator.click()
    log(f"Clique em '{label}' usando seletor: {selector}")


def _fill_first_visible(
    page: Page,
    selectors: list[str],
    value: str,
    timeout_ms: int,
    label: str,
    log: LogCallback,
) -> None:
    selector, locator = _first_visible_locator(page, selectors, timeout_ms)
    locator.fill(value)
    log(f"Preenchido '{label}' com seletor: {selector}")


def _ensure_variantes_selected(page: Page, timeout_ms: int, log: LogCallback) -> None:
    selector, wrapper = _first_visible_locator(page, VARIANT_TAB_SELECTORS, timeout_ms)
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

    page.locator(ADD_VARIANT_SELECTORS[0]).first.wait_for(state="visible", timeout=timeout_ms)


def _maximize_browser_window(page: Page, log: LogCallback) -> None:
    # Em alguns ambientes Windows, --start-maximized nao aplica sempre.
    # Forca o estado maximizado via CDP para maior confiabilidade.
    try:
        cdp = page.context.new_cdp_session(page)
        window_info = cdp.send("Browser.getWindowForTarget")
        window_id = window_info.get("windowId")
        if window_id is not None:
            cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {"windowState": "maximized"},
                },
            )
            return
    except Exception as exc:
        log(f"Aviso: falha ao maximizar via CDP: {exc}")

    # Fallback best effort.
    try:
        page.evaluate(
            """() => {
                try {
                    window.moveTo(0, 0);
                    window.resizeTo(screen.availWidth, screen.availHeight);
                } catch (e) {}
            }"""
        )
    except Exception as exc:
        log(f"Aviso: falha no fallback de maximizacao: {exc}")
