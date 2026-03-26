from __future__ import annotations

import argparse
import json
from pathlib import Path

from rpa.variant_runner import VariantJobInput, run_variant_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Worker da automacao de variantes")
    parser.add_argument("--request", required=True, help="Caminho do JSON de entrada")
    parser.add_argument("--result", required=True, help="Caminho do JSON de saida")
    parser.add_argument("--log", required=True, help="Caminho do arquivo de log")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    request_path = Path(args.request)
    result_path = Path(args.result)
    log_path = Path(args.log)

    payload = json.loads(request_path.read_text(encoding="utf-8"))

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
        action_timeout_ms=int(payload.get("action_timeout_ms", 40000)),
        artifacts_dir=Path(payload.get("artifacts_dir", "artifacts")),
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)

    def on_log(line: str) -> None:
        with log_path.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")

    result = run_variant_job(job_input=job_input, log_cb=on_log)

    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(result.to_json(), encoding="utf-8")

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
