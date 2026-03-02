from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import time

email = 'tsano38@outlook.jp'
order_number = 'W1591912520'
URL = 'https://www.apple.com/jp/shop/order/list'

with Stealth().use_sync(sync_playwright()) as p:
    browser = p.chromium.launch(channel='chrome', headless=False)
    
    # Dummy context
    dummy_context = browser.new_context()
    dummy_page = dummy_context.new_page()
    try:
        dummy_page.goto(URL, wait_until='domcontentloaded', timeout=15000)
    except:
        pass
    finally:
        dummy_context.close()
    
    context = browser.new_context()
    page = context.new_page()
    
    page.goto(URL, wait_until='domcontentloaded')
    time.sleep(2)
    page.wait_for_selector('#signIn\\.orderLookUp\\.orderNumber', timeout=15000)
    
    page.fill('#signIn\\.orderLookUp\\.emailAddress', email)
    page.fill('#signIn\\.orderLookUp\\.orderNumber', order_number)
    page.click('#signIn\\.orderLookUp\\.guestUserOrderLookUp')
    
    time.sleep(5)
    page.wait_for_load_state('networkidle', timeout=10000)
    
    text = page.locator('body').inner_text().replace('\xa0', ' ')
    with open('w15_dump.txt', 'w', encoding='utf-8') as f:
        f.write(text)
    
    browser.close()
    print('Dumped successfully.')
