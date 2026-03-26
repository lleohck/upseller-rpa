from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Worker para salvar storage_state via CDP")
    parser.add_argument("--cdp-url", required=True, help="URL CDP, ex.: http://127.0.0.1:9222")
    parser.add_argument("--output", required=True, help="Arquivo de saida do storage_state.json")
    parser.add_argument("--domain-hint", default="upseller.com", help="Dominio para priorizar cookies/origins")
    return parser.parse_args()


def score_state_for_domain(state: dict, domain_hint: str) -> int:
    cookies = list(state.get("cookies", []))
    origins = list(state.get("origins", []))
    if not domain_hint:
        return len(cookies) + len(origins)

    hint = domain_hint.lower().strip()
    cookie_hits = 0
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lower()
        if hint in domain:
            cookie_hits += 1

    origin_hits = 0
    for origin in origins:
        origin_url = str(origin.get("origin", "")).lower()
        if hint in origin_url:
            origin_hits += 1

    return (cookie_hits * 10) + origin_hits


def run() -> dict:
    args = parse_args()
    output_path = Path(args.output)
    domain_hint = args.domain_hint.strip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        try:
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("Nenhum contexto ativo encontrado no navegador de login.")

            selected_url = ""
            best_state: Optional[dict] = None
            best_score = -1

            for context in contexts:
                try:
                    state = context.storage_state()
                except Exception:
                    continue

                score = score_state_for_domain(state, domain_hint)
                if score > best_score:
                    best_state = state
                    best_score = score
                    for page in context.pages:
                        current_url = (page.url or "").strip()
                        if current_url and current_url != "about:blank":
                            selected_url = current_url
                            if domain_hint and domain_hint.lower() in current_url.lower():
                                break

            if not best_state:
                raise RuntimeError("Nao foi possivel obter dados de sessao via CDP.")

            cookies_count = len(list(best_state.get("cookies", [])))
            origins_count = len(list(best_state.get("origins", [])))
            if cookies_count == 0 and origins_count == 0:
                raise RuntimeError(
                    "Sessao vazia detectada. Finalize o login no UpSeller e clique em OK novamente."
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(best_state, ensure_ascii=False, indent=2), encoding="utf-8")

            return {
                "ok": True,
                "selected_url": selected_url,
                "cookies_count": cookies_count,
                "origins_count": origins_count,
            }
        finally:
            browser.close()


def main() -> int:
    try:
        result = run()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
