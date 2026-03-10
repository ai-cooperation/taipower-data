"""Take a screenshot of TaiPower's daily load curve chart.

Runs daily at 22:00 Taiwan time via acmacmini2 cron.
Saves to data/screenshots/YYYY-MM-DD.png
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.taipower.com.tw/d006/loadGraph/loadGraph/load_fueltype_.html"
SCREENSHOT_DIR = Path("data/screenshots")
TW_TZ = timezone(timedelta(hours=8))


def take_screenshot() -> Path:
    today = datetime.now(TW_TZ).strftime("%Y-%m-%d")
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    output = SCREENSHOT_DIR / f"{today}.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="networkidle", timeout=30000)
        # Wait for chart to render
        page.wait_for_timeout(3000)
        page.screenshot(path=str(output), full_page=False)
        browser.close()

    print(f"  saved: {output} ({output.stat().st_size:,} bytes)")
    return output


def main():
    print("Taking TaiPower load curve screenshot...")
    try:
        take_screenshot()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
