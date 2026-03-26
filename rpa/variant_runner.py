from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

LogCallback = Callable[[str], None]
WaitBeforeCloseCallback = Callable[[str], None]
ResultReadyCallback = Callable[["VariantJobResult"], None]

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
DESCRIPTION_TABLE_ROW_SELECTORS = [
    "div.sales_table_wrap tbody tr.vxe-body--row",
    "div.sales_table_wrap .vxe-table--body tbody tr",
]
ROW_DESCRIPTION_ADD_SELECTORS = [
    "span.my_txt_btn:has-text('Adicionar')",
    "i.edit_btn.anticon-edit",
    "i.anticon-edit",
]
ROW_DESCRIPTION_INPUT_SELECTORS = [
    "textarea",
    "div[contenteditable='true']",
    "input.ant-input",
]
DESCRIPTION_EDITOR_INPUT_SELECTORS = [
    "div.descript_modal textarea",
    "div.descript_modal input.ant-input",
    ".descript_modal textarea",
    ".descript_modal input.ant-input",
    ".ant-modal-root textarea",
    ".ant-modal-root input.ant-input",
    ".ant-popover textarea",
    ".ant-popover input.ant-input",
]
GLOBAL_DESCRIPTION_INPUT_SELECTORS = [
    "div.sales_table_wrap textarea",
    "div.sales_table_wrap div[contenteditable='true']",
    "div.sales_table_wrap input.ant-input",
]
DESCRIPTION_SAVE_SELECTORS = [
    ".ant-modal-root button:has-text('Salvar')",
    ".ant-popover button:has-text('Salvar')",
    ".ant-drawer button:has-text('Salvar')",
    "div.sales_table_wrap button:has-text('Salvar')",
]
DESCRIPTION_BLUR_SELECTORS = [
    "#description .ant-card-head",
    "#description .ant-card-head-title",
    "div#description",
]
SALES_TABLE_ROW_SELECTORS = [
    "table.vxe-table--body tbody tr.vxe-body--row:has(td[colid='col_12'])",
    "table.vxe-table--body tbody tr:has(td[colid='col_12'])",
]
ROW_PRICE_INPUT_SELECTORS = [
    "td[colid='col_12'] input.ant-input-number-input",
    "input.ant-input-number-input",
]
PRICE_BLUR_SELECTORS = [
    "#salesInfo .ant-card-head",
    "#salesInfo",
    "body",
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
    option_description_template: Optional[str] = None
    option_price_brl: Optional[str] = None
    action_timeout_ms: int = 30000
    artifacts_dir: Path = Path("artifacts")


@dataclass
class VariantJobResult:
    success: bool
    created_options: list[str] = field(default_factory=list)
    skipped_options: list[str] = field(default_factory=list)
    described_options: list[str] = field(default_factory=list)
    priced_options: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    final_page_screenshot_path: Optional[str] = None
    log_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "created_options": self.created_options,
            "skipped_options": self.skipped_options,
            "described_options": self.described_options,
            "priced_options": self.priced_options,
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "final_page_screenshot_path": self.final_page_screenshot_path,
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


def normalize_price_brl(raw: str) -> str:
    clean = raw.strip().replace("R$", "").replace("r$", "").replace(" ", "")
    clean = clean.replace("\u00a0", "")
    if not clean:
        raise ValueError("Preco(R$) invalido. Informe um valor como 99,90 ou 99.90.")

    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    else:
        clean = clean.replace(",", ".")

    if not re.fullmatch(r"\d+(\.\d{1,2})?", clean):
        raise ValueError("Preco(R$) invalido. Use formato como 99,90 ou 99.90.")

    return clean


def run_variant_job(
    job_input: VariantJobInput,
    log_cb: Optional[LogCallback] = None,
    wait_before_close_cb: Optional[WaitBeforeCloseCallback] = None,
    result_ready_cb: Optional[ResultReadyCallback] = None,
) -> VariantJobResult:
    result = VariantJobResult(success=False)
    page: Optional[Page] = None
    browser = None

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
            if page is None:
                log("Aviso: navegador aberto, mas sem pagina ativa para aguardar fechamento manual.")
                return
            log(f"{reason} Navegador permanecera aberto. Feche manualmente a janela para encerrar.")
            while True:
                try:
                    if page.is_closed():
                        log("Janela fechada manualmente. Encerrando processo.")
                        return
                    if browser is not None and not browser.is_connected():
                        log("Browser desconectado. Encerrando processo.")
                        return
                    page.wait_for_timeout(500)
                except Exception:
                    return
            return
        try:
            wait_before_close_cb(reason)
        except Exception as exc:
            log(f"Aviso: falha na espera antes de fechar navegador: {exc}")

    def publish_result_ready() -> None:
        if not result_ready_cb:
            return
        try:
            result_ready_cb(result)
        except Exception as exc:
            log(f"Aviso: falha ao publicar resultado parcial/final: {exc}")

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
    if job_input.option_description_template:
        log("Template de descricao detectado. Apos criar opcoes, sera preenchida a descricao por linha.")
    if job_input.option_price_brl:
        log(f"Preco por opcao detectado: R$ {job_input.option_price_brl}")

    with sync_playwright() as playwright:
        context = None

        try:
            launch_args: list[str] = []
            context_kwargs: dict = {"storage_state": str(job_input.storage_state_path)}

            if job_input.headful and job_input.maximize_window:
                launch_args.append("--start-maximized")
                context_kwargs["no_viewport"] = True

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
                publish_result_ready()
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
                log(f"Variacao criada com sucesso: {job_input.variant_name}")

            for option_name in job_input.option_names:
                if _option_already_exists(page, option_name):
                    result.skipped_options.append(option_name)
                    log(f"Opcao ja existente, ignorando: {option_name}")
                    continue

                _add_option(page, option_name, job_input.action_timeout_ms, log)
                result.created_options.append(option_name)

            if job_input.option_description_template:
                if not result.created_options:
                    log(
                        "Template de descricao informado, mas nenhuma opcao nova foi criada. "
                        "Etapa de descricao ignorada."
                    )
                else:
                    described = _fill_descriptions_for_options(
                        page=page,
                        option_names=result.created_options,
                        template=job_input.option_description_template,
                        timeout_ms=job_input.action_timeout_ms,
                        log=log,
                    )
                    result.described_options.extend(described)

            if job_input.option_price_brl:
                priced = _fill_prices_for_options(
                    page=page,
                    option_names=list(dict.fromkeys(job_input.option_names)),
                    price_value=job_input.option_price_brl,
                    timeout_ms=job_input.action_timeout_ms,
                    log=log,
                )
                result.priced_options.extend(priced)

            context.storage_state(path=str(job_input.storage_state_path))
            log(f"storage_state atualizado em: {job_input.storage_state_path}")

            final_screenshot = _save_page_screenshot(page, job_input.artifacts_dir, "variant_final")
            if final_screenshot:
                result.final_page_screenshot_path = str(final_screenshot)
                log(f"Print final salvo em: {final_screenshot}")

            result.success = True
            log(
                "Execucao concluida. "
                f"Criadas: {len(result.created_options)} | "
                f"Ignoradas: {len(result.skipped_options)} | "
                f"Descritas: {len(result.described_options)} | "
                f"Precificadas: {len(result.priced_options)}"
            )
            publish_result_ready()
            maybe_wait_before_close("Execucao concluida com sucesso.")
            return result

        except Exception as exc:
            result.error_message = str(exc)
            log(f"Falha na execucao: {exc}")
            screenshot_path = _save_error_screenshot(page, job_input.artifacts_dir)
            if screenshot_path:
                result.screenshot_path = str(screenshot_path)
                result.final_page_screenshot_path = str(screenshot_path)
                log(f"Screenshot salva em: {screenshot_path}")
            publish_result_ready()
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
    if job_input.option_description_template is not None:
        cleaned = job_input.option_description_template.strip()
        job_input.option_description_template = cleaned or None
    if job_input.option_price_brl is not None:
        cleaned_price = str(job_input.option_price_brl).strip()
        job_input.option_price_brl = normalize_price_brl(cleaned_price) if cleaned_price else None


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


def _fill_descriptions_for_options(
    page: Page,
    option_names: list[str],
    template: str,
    timeout_ms: int,
    log: LogCallback,
) -> list[str]:
    if "{{OPTION_NAME}}" not in template:
        log(
            "Aviso: template de descricao sem {{OPTION_NAME}}. "
            "O mesmo texto sera aplicado para todas as opcoes."
        )

    _wait_for_table_rows(page, minimum_rows=1, timeout_ms=timeout_ms)
    described_options: list[str] = []

    for option_name in option_names:
        description_text = template.replace("{{OPTION_NAME}}", option_name)
        row = _find_row_for_option_description(page, option_name, timeout_ms=timeout_ms)
        _fill_single_row_description(page, row, option_name, description_text, timeout_ms, log)
        described_options.append(option_name)

    return described_options


def _wait_for_table_rows(page: Page, minimum_rows: int, timeout_ms: int) -> None:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < timeout_ms:
        rows = _description_rows(page)
        try:
            if rows.count() >= minimum_rows:
                return
        except Exception:
            pass
        page.wait_for_timeout(250)

    raise RuntimeError(
        "Tabela de descricao nao encontrada/insuficiente. "
        "Ajuste os seletores de DESCRIPTION_TABLE_ROW_SELECTORS."
    )


def _description_rows(page: Page) -> Locator:
    # Prioriza o primeiro seletor que encontrar ao menos uma linha.
    for selector in DESCRIPTION_TABLE_ROW_SELECTORS:
        locator = page.locator(selector)
        try:
            if locator.count() > 0:
                return locator
        except Exception:
            continue
    return page.locator(DESCRIPTION_TABLE_ROW_SELECTORS[0])


def _find_row_for_option_description(
    page: Page,
    option_name: str,
    timeout_ms: int,
) -> Locator:
    started = time.monotonic()
    option_key = _normalize_text(option_name)
    while (time.monotonic() - started) * 1000 < timeout_ms:
        rows = _description_rows(page)
        try:
            count = rows.count()
        except Exception:
            count = 0

        contains_match: Optional[Locator] = None
        for idx in range(count):
            row = rows.nth(idx)
            try:
                if not row.is_visible():
                    continue
                product_cell = row.locator("td[colid='col_18'] .d_ib").first
                raw_text = product_cell.inner_text() if product_cell.count() > 0 else row.inner_text()
                cell_key = _normalize_text(raw_text)
                if not cell_key:
                    continue
                if cell_key == option_key:
                    return row
                if option_key in cell_key:
                    contains_match = row
            except Exception:
                continue

        if contains_match is not None:
            return contains_match

        page.wait_for_timeout(250)

    raise RuntimeError(f"Nao encontrei linha de descricao para opcao: {option_name}")


def _fill_single_row_description(
    page: Page,
    row: Locator,
    option_name: str,
    description_text: str,
    timeout_ms: int,
    log: LogCallback,
) -> None:
    clicked = _click_first_visible_in_scope(
        scope=row,
        page=page,
        selectors=ROW_DESCRIPTION_ADD_SELECTORS,
        timeout_ms=min(timeout_ms, 4000),
    )
    if not clicked:
        # Fallback: abre editor clicando na celula de descricao da linha.
        row.locator("td[colid='col_20'] .h_60").first.click()

    input_locator = _first_visible_locator_in_scope(
        scope=row,
        page=page,
        selectors=ROW_DESCRIPTION_INPUT_SELECTORS,
        timeout_ms=2000,
    )
    if input_locator is None:
        input_locator = _first_visible_locator(
            page,
            DESCRIPTION_EDITOR_INPUT_SELECTORS + GLOBAL_DESCRIPTION_INPUT_SELECTORS,
            timeout_ms,
        )[1]

    _fill_locator_value(input_locator, description_text)
    if not _click_first_visible_optional(page, DESCRIPTION_SAVE_SELECTORS, timeout_ms=1500):
        if not _click_first_visible_optional(page, DESCRIPTION_BLUR_SELECTORS, timeout_ms=1000):
            page.mouse.click(8, 8)
    page.wait_for_timeout(300)

    log(f"Descricao preenchida para opcao: {option_name}")


def _fill_prices_for_options(
    page: Page,
    option_names: list[str],
    price_value: str,
    timeout_ms: int,
    log: LogCallback,
) -> list[str]:
    _wait_for_sales_rows(page, minimum_rows=1, timeout_ms=timeout_ms)
    priced_options: list[str] = []

    for option_name in option_names:
        row = _find_row_for_option_sale(page, option_name, timeout_ms=timeout_ms)
        _fill_single_row_price(page, row, option_name, price_value, timeout_ms, log)
        priced_options.append(option_name)

    return priced_options


def _wait_for_sales_rows(page: Page, minimum_rows: int, timeout_ms: int) -> None:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < timeout_ms:
        rows = _sales_rows(page)
        try:
            if rows.count() >= minimum_rows:
                return
        except Exception:
            pass
        page.wait_for_timeout(250)

    raise RuntimeError(
        "Tabela de Informacoes de Venda nao encontrada/insuficiente. "
        "Ajuste os seletores de SALES_TABLE_ROW_SELECTORS."
    )


def _sales_rows(page: Page) -> Locator:
    for selector in SALES_TABLE_ROW_SELECTORS:
        locator = page.locator(selector)
        try:
            if locator.count() > 0:
                return locator
        except Exception:
            continue
    return page.locator(SALES_TABLE_ROW_SELECTORS[0])


def _find_row_for_option_sale(page: Page, option_name: str, timeout_ms: int) -> Locator:
    started = time.monotonic()
    option_key = _normalize_text(option_name)
    while (time.monotonic() - started) * 1000 < timeout_ms:
        rows = _sales_rows(page)
        try:
            count = rows.count()
        except Exception:
            count = 0

        contains_match: Optional[Locator] = None
        for idx in range(count):
            row = rows.nth(idx)
            try:
                if not row.is_visible():
                    continue
                product_cell = row.locator("td[colid='col_9'] .d_ib").first
                raw_text = product_cell.inner_text() if product_cell.count() > 0 else row.inner_text()
                cell_key = _normalize_text(raw_text)
                if not cell_key:
                    continue
                if cell_key == option_key:
                    return row
                if option_key in cell_key:
                    contains_match = row
            except Exception:
                continue

        if contains_match is not None:
            return contains_match

        page.wait_for_timeout(250)

    raise RuntimeError(f"Nao encontrei linha de venda para opcao: {option_name}")


def _fill_single_row_price(
    page: Page,
    row: Locator,
    option_name: str,
    price_value: str,
    timeout_ms: int,
    log: LogCallback,
) -> None:
    price_input = _first_visible_locator_in_scope(
        scope=row,
        page=page,
        selectors=ROW_PRICE_INPUT_SELECTORS,
        timeout_ms=min(timeout_ms, 4000),
    )
    if price_input is None:
        row.locator("td[colid='col_12']").first.click()
        price_input = _first_visible_locator_in_scope(
            scope=row,
            page=page,
            selectors=ROW_PRICE_INPUT_SELECTORS,
            timeout_ms=min(timeout_ms, 4000),
        )
    if price_input is None:
        raise RuntimeError(f"Nao encontrei campo de preco para opcao: {option_name}")

    price_input.click()
    price_input.press("ControlOrMeta+A")
    price_input.fill(price_value)
    price_input.press("Enter")

    if not _click_first_visible_optional(page, PRICE_BLUR_SELECTORS, timeout_ms=1000):
        page.mouse.click(8, 8)

    page.wait_for_timeout(200)
    log(f"Preco aplicado com sucesso: {option_name} -> R$ {price_value}")


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _save_error_screenshot(page: Optional[Page], artifacts_dir: Path) -> Optional[Path]:
    return _save_page_screenshot(page, artifacts_dir, "variant_error")


def _save_page_screenshot(page: Optional[Page], artifacts_dir: Path, prefix: str) -> Optional[Path]:
    if not page:
        return None
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        file_path = artifacts_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
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


def _first_visible_locator_in_scope(
    scope: Locator,
    page: Page,
    selectors: Iterable[str],
    timeout_ms: int,
) -> Optional[Locator]:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < timeout_ms:
        for selector in selectors:
            locator = scope.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue

            for idx in range(count):
                item = locator.nth(idx)
                try:
                    if item.is_visible():
                        return item
                except Exception:
                    continue
        page.wait_for_timeout(200)
    return None


def _click_first_visible_in_scope(
    scope: Locator,
    page: Page,
    selectors: Iterable[str],
    timeout_ms: int,
) -> bool:
    locator = _first_visible_locator_in_scope(scope, page, selectors, timeout_ms)
    if locator is None:
        return False
    locator.click()
    return True


def _click_first_visible_optional(page: Page, selectors: Iterable[str], timeout_ms: int) -> bool:
    try:
        _, locator = _first_visible_locator(page, selectors, timeout_ms)
        locator.click()
        return True
    except Exception:
        return False


def _fill_locator_value(locator: Locator, value: str) -> None:
    tag_name = locator.evaluate("el => el.tagName.toLowerCase()")
    if tag_name in {"input", "textarea"}:
        locator.fill(value)
        return

    locator.click()
    locator.press("ControlOrMeta+A")
    locator.press("Backspace")
    locator.type(value)


def _click_first_visible(
    page: Page,
    selectors: list[str],
    timeout_ms: int,
    label: str,
    log: LogCallback,
) -> None:
    _, locator = _first_visible_locator(page, selectors, timeout_ms)
    locator.click()


def _fill_first_visible(
    page: Page,
    selectors: list[str],
    value: str,
    timeout_ms: int,
    label: str,
    log: LogCallback,
) -> None:
    _, locator = _first_visible_locator(page, selectors, timeout_ms)
    locator.fill(value)


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
