import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

chrome_options = Options()
# chrome_options.add_argument("--headless")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    driver.get("https://buygift.app/exhibitions/2")
    time.sleep(3)
    items = driver.find_elements(By.CSS_SELECTOR, "div[class*='styles_gift_table__']")
    for i, item in enumerate(items[:5]):
        print(f"--- Item {i} text ---")
        lines = item.text.split('\n')
        for j, line in enumerate(lines):
            print(f"[{j}]: {repr(line)}")
        print("-------------------")
finally:
    driver.quit()
