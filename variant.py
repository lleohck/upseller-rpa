from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from rpa.variant_runner import VariantJobInput, normalize_option_names, run_variant_job


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_option_names_from_env() -> list[str]:
    raw_list = os.getenv("UPSELLER_OPTION_NAMES", "").strip()
    if raw_list:
        values = normalize_option_names(raw_list)
        if values:
            return values

    fallback = os.getenv("UPSELLER_OPTION_NAME", "teste2").strip() or "teste2"
    return [fallback]


def main() -> int:
    load_dotenv()

    storage_state_path = Path(os.getenv("STORAGE_STATE_PATH", "storage_state.json").strip() or "storage_state.json")
    draft_url = os.getenv("UPSELLER_DRAFT_URL", "").strip() or os.getenv("rascunho_url", "").strip()
    variant_name = os.getenv("UPSELLER_VARIANT_NAME", "Cor").strip() or "Cor"
    option_names = parse_option_names_from_env()

    keep_open = bool_env("UPSELLER_KEEP_OPEN", default=False)
    skip_variant_creation = bool_env("UPSELLER_SKIP_VARIANT_CREATION", default=False)

    job_input = VariantJobInput(
        draft_url=draft_url,
        variant_name=variant_name,
        option_names=option_names,
        storage_state_path=storage_state_path,
        login_url=os.getenv("UPSELLER_LOGIN_URL", "").strip() or None,
        headful=bool_env("HEADFUL", default=True),
        maximize_window=bool_env("UPSELLER_MAXIMIZE_WINDOW", default=True),
        keep_browser_open=keep_open,
        skip_variant_creation=skip_variant_creation,
        action_timeout_ms=int(os.getenv("UPSELLER_ACTION_TIMEOUT_MS", "30000").strip() or "30000"),
        artifacts_dir=Path("artifacts"),
    )

    def wait_before_close(reason: str) -> None:
        print(f"\n{reason}")
        input("Pressione ENTER para encerrar o navegador...")

    result = run_variant_job(
        job_input,
        log_cb=print,
        wait_before_close_cb=wait_before_close if keep_open else None,
    )

    if result.success:
        print("\nResumo:")
        print(f"- Criadas: {result.created_options}")
        print(f"- Ignoradas: {result.skipped_options}")
    else:
        print("\nResumo:")
        print(f"- Erro: {result.error_message}")
        if result.screenshot_path:
            print(f"- Screenshot: {result.screenshot_path}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
