import re

from playwright.sync_api import Page, expect


def test_checkout_shows_final_success_status(page: Page, demo_url: str) -> None:
    page.goto(f"{demo_url}/checkout.html")

    page.get_by_label("Имя плательщика").fill("Тестовый плательщик")
    page.get_by_label("Номер тестовой карты").fill("4242424242424242")
    page.get_by_label("Сумма").fill("1250")
    page.get_by_label("Валюта").select_option("RUB")
    page.get_by_role("button", name="Перейти к подтверждению").click()

    expect(page).to_have_url(re.compile(r"/confirmation\.html$"))
    expect(page.get_by_role("heading", name="Подтверждение платежа")).to_be_visible()
    expect(page.locator("#payer")).to_have_text("Тестовый плательщик")
    expect(page.locator("#amount")).to_have_text("1250 RUB")
    expect(page.locator("#card")).to_have_text("**** 4242")

    page.get_by_role("button", name="Подтвердить оплату").click()

    expect(page).to_have_url(re.compile(r"/result\.html$"))
    expect(page.get_by_role("heading", name="Результат платежа")).to_be_visible()
    expect(page.get_by_role("status")).to_have_text("Успешно")
    expect(page.locator("#payment-summary")).to_have_text(
        "Тестовый плательщик: 1250 RUB"
    )
