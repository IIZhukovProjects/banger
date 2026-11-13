import argparse
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

import httpx
from playwright.sync_api import sync_playwright, expect


def run(base, output):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=os.environ.get("CHROME_PATH")
            or (
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                if Path(
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                ).exists()
                else None
            ),
        )
        try:
            television = browser.new_context(viewport={"width": 1440, "height": 1000})
            tv = television.new_page()
            tv.on("pageerror", lambda error: errors.append(str(error)))
            tv.goto(base + "/tv", wait_until="networkidle")
            tv.get_by_label("Как назовём комнату?").fill("Браузерная компания")
            tv.get_by_role("button", name="Создать комнату", exact=True).click()
            tv.wait_for_url(re.compile(r".*/tv\?room=[A-Z0-9]{6}$"))
            code = parse_qs(urlsplit(tv.url).query)["room"][0]
            expect(
                tv.get_by_text("Браузерная компания", exact=True).first
            ).to_be_visible()
            mobile = browser.new_context(
                viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
            )
            phone = mobile.new_page()
            phone.on("pageerror", lambda error: errors.append(str(error)))
            phone.goto(base + "/play?room=" + code, wait_until="networkidle")
            phone.get_by_label("Твоё имя", exact=True).fill("Игрок браузера")
            phone.get_by_role("button", name="Войти", exact=True).click()
            expect(
                phone.get_by_role("button", name=re.compile("Начать игру"))
            ).to_be_visible()
            with httpx.Client(base_url=base, trust_env=False) as api:
                response = api.post(
                    "/api/join",
                    headers={"X-Room-Code": code},
                    json={"name": "Друг браузера"},
                )
                assert response.status_code == 200
            start = phone.get_by_role("button", name=re.compile("Начать игру"))
            expect(start).to_be_enabled(timeout=10000)
            start.click()
            expect(phone.locator("textarea").first).to_be_visible(timeout=10000)
            phone.locator("textarea").first.fill("Бенгер из браузера")
            phone.get_by_role("button", name="Отправить бенгер", exact=True).click()
            expect(
                phone.get_by_role("heading", name="Ответ принят", exact=True)
            ).to_be_visible()
            expect(
                tv.get_by_role("heading", name="Делаем бенгер.", exact=True)
            ).to_be_visible(timeout=10000)
            tv.screenshot(path=str(output / "television.png"), full_page=True)
            phone.screenshot(path=str(output / "controller.png"), full_page=True)
            assert not errors, "Browser script errors: " + repr(errors)
            return {
                "roomCreation": True,
                "controllerJoin": True,
                "leaderStart": True,
                "answerSubmission": True,
                "tvUpdates": True,
                "scriptErrors": False,
            }
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.output)))
