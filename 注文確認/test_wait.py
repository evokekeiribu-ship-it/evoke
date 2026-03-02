from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import time

email = 'sanot060@proton.me'
order_number = 'W1333227795'
URL = 'https://www.apple.com/jp/shop/order/list'

with Stealth().use_sync(sync_playwright()) as p:
    browser = p.chromium.launch(
        channel='chrome',
        headless=False,
        args=[
            '--incognito',
        ]
    )
    
    context = browser.new_context()
    page = context.new_page()
    
    page.goto(URL, wait_until='domcontentloaded')
    time.sleep(2)
    page.wait_for_selector('#signIn\\.orderLookUp\\.orderNumber', timeout=15000)
    
    page.fill('#signIn\\.orderLookUp\\.emailAddress', email)
    page.fill('#signIn\\.orderLookUp\\.orderNumber', order_number)
    page.click('#signIn\\.orderLookUp\\.guestUserOrderLookUp')
    
    print("Clicked login, waiting...")
    
    try:
        # Wait for either the order details to appear or the error message
        page.wait_for_selector('h1, .rs-guest-order-details, .as-l-container, .rs-alert', timeout=15000)
        print("A container appeared")
        page.wait_for_load_state("networkidle", timeout=10000)
        print("Network idle")
        time.sleep(2)
    except Exception as e:
        print("Wait failed:", e)
        
    text = page.locator('body').inner_text().replace('\xa0', ' ')
    with open('w_test.txt', 'w', encoding='utf-8') as f:
        f.write(text)
    
    browser.close()
    print('Dumped successfully.')
