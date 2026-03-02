import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import yaml

with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

email = config['login']['email']
password = config['login']['password']

chrome_options = Options()
# chrome_options.add_argument("--headless")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    driver.get("https://buygift.app/users/signin")
    time.sleep(2)
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys(email)
    driver.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys(password)
    driver.find_element(By.XPATH, "//button[.//span[text()='ログイン']]").click()
    time.sleep(3)
    
    driver.get("https://buygift.app/exhibitions/2")
    time.sleep(3)
    
    items = driver.find_elements(By.CSS_SELECTOR, "div[class*='styles_gift_table__']")
    if items:
        with open('button_html.txt', 'w', encoding='utf-8') as out:
            out.write(items[0].get_attribute('innerHTML'))
        print("Scraped to button_html.txt")
        
        # let's also take a look at buttons specifically
        buttons = items[0].find_elements(By.TAG_NAME, "button")
        for i, b in enumerate(buttons):
            print(f"Button {i} classes: {b.get_attribute('class')} text: {b.text} outer: {b.get_attribute('outerHTML')}")
    else:
        print("No items found.")
finally:
    driver.quit()
