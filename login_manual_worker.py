from __future__ import annotations

import argparse
import time

from playwright.sync_api import Page, sync_playwright


def force_maximize_window(page: Page) -> None:
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
    except Exception:
        pass

    try:
        page.evaluate(
            """() => {
                try {
                    window.moveTo(0, 0);
                    window.resizeTo(screen.availWidth, screen.availHeight);
                } catch (e) {}
            }"""
        )
    except Exception:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Worker de login manual UpSeller")
    parser.add_argument("--login-url", required=True, help="URL de login")
    parser.add_argument("--cdp-port", required=True, type=int, help="Porta CDP")
    parser.add_argument("--maximize", action="store_true", help="Abrir janela maximizada")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    launch_args = [
        f"--remote-debugging-port={args.cdp_port}",
        "--remote-debugging-address=127.0.0.1",
    ]
    context_kwargs: dict = {}

    if args.maximize:
        launch_args.append("--start-maximized")
        context_kwargs["no_viewport"] = True

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=launch_args,
        )
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        if args.maximize:
            force_maximize_window(page)

        page.goto(args.login_url, wait_until="domcontentloaded", timeout=60000)

        if args.maximize:
            force_maximize_window(page)

        try:
            while True:
                if page.is_closed():
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
