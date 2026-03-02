import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

chrome_options = Options()
chrome_options.add_argument("--headless")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    driver.get("https://buygift.app/exhibitions/2")
    time.sleep(3)
    btns = driver.find_elements(By.CSS_SELECTOR, "button[class*='styles_globalbuttonpurchase_']")
    if btns:
        row = btns[0].find_element(By.XPATH, "../../../..")
        print("--- Ancestor 4 HTML ---")
        print(row.get_attribute('outerHTML')[:2000])
        print("--- Ancestor 4 Text ---")
        print(repr(row.text))
finally:
    driver.quit()
