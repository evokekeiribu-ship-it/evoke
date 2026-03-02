from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://www.pokemoncenter-online.com/', timeout=60000)
    page.wait_for_timeout(5000)
    html = page.evaluate('() => document.querySelector("#header") ? document.querySelector("#header").outerHTML : "No header"')
    with open('header.html', 'w', encoding='utf-8') as f:
        f.write(html)
    browser.close()
