from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Worker da automacao de variantes")
    parser.add_argument("--request", required=True, help="Caminho do JSON de entrada")
    parser.add_argument("--result", required=True, help="Caminho do JSON de saida")
    parser.add_argument("--log", required=True, help="Caminho do arquivo de log")
    return parser.parse_args()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append_log(log_path: Path, message: str) -> None:
    line = f"[{_now()}] {message}"
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def _write_result(result_path: Path, payload: dict) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = result_path.with_suffix(".tmp.json")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(result_path)


def main() -> int:
    args = parse_args()

    request_path = Path(args.request).resolve()
    result_path = Path(args.result).resolve()
    log_path = Path(args.log).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _append_log(log_path, f"Worker iniciado. PID={os.getpid()} python={sys.executable}")
    _append_log(log_path, f"CWD: {os.getcwd()}")
    _append_log(log_path, f"Request path: {request_path}")
    _append_log(log_path, f"Result path: {result_path}")

    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        _append_log(log_path, "Request carregado com sucesso.")

        from rpa.variant_runner import VariantJobInput, run_variant_job

        _append_log(log_path, "Modulo rpa.variant_runner carregado com sucesso.")

        job_input = VariantJobInput(
            draft_url=str(payload["draft_url"]),
            variant_name=str(payload.get("variant_name", "")),
            option_names=list(payload["option_names"]),
            storage_state_path=Path(payload["storage_state_path"]),
            login_url=payload.get("login_url") or None,
            headful=bool(payload.get("headful", True)),
            maximize_window=bool(payload.get("maximize_window", True)),
            keep_browser_open=bool(payload.get("keep_browser_open", True)),
            skip_variant_creation=bool(payload.get("skip_variant_creation", False)),
            option_description_template=payload.get("option_description_template") or None,
            option_price_brl=payload.get("option_price_brl") or None,
            apply_variant_images=bool(payload.get("apply_variant_images", False)),
            action_timeout_ms=int(payload.get("action_timeout_ms", 40000)),
            artifacts_dir=Path(payload.get("artifacts_dir", "artifacts")),
        )

        def on_log(line: str) -> None:
            with log_path.open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")

        def write_result_json(result_obj) -> None:
            _write_result(result_path, json.loads(result_obj.to_json()))

        _append_log(log_path, "Iniciando run_variant_job...")
        result = run_variant_job(
            job_input=job_input,
            log_cb=on_log,
            result_ready_cb=write_result_json,
        )
        _write_result(result_path, json.loads(result.to_json()))
        _append_log(log_path, f"run_variant_job finalizado. success={result.success}")
        return 0 if result.success else 1

    except Exception as exc:
        tb = traceback.format_exc()
        _append_log(log_path, f"Falha no worker: {exc}")
        _append_log(log_path, tb)
        fallback_result = {
            "success": False,
            "created_options": [],
            "skipped_options": [],
            "described_options": [],
            "priced_options": [],
            "media_images_applied": False,
            "error_message": str(exc),
            "screenshot_path": None,
            "final_page_screenshot_path": None,
            "log_lines": [],
        }
        try:
            _write_result(result_path, fallback_result)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
