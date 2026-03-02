import os
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import gmail_reader

# Load environment variables
load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
POKEMON_CENTER_EMAIL = os.getenv("POKEMON_CENTER_EMAIL")
POKEMON_CENTER_PASSWORD = os.getenv("POKEMON_CENTER_PASSWORD")

LOGIN_URL = "https://www.pokemoncenter-online.com/?p=login"
TOP_URL = "https://www.pokemoncenter-online.com/"

def run(playwright):
    print("Starting browser...")
    
    # Force a fresh incognito session every time (do not use storage state)
    context_options = {
        "viewport": {"width": 1280, "height": 720},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    browser = playwright.chromium.launch(headless=False) # Keep visible to watch the process
    context = browser.new_context(**context_options)
    page = context.new_page()
    
    # === STEP 1 & 2: Navigate directly to Login Page ===
    print(f"Navigating to login page: {LOGIN_URL}")
    # Set the top page as referer to avoid being redirected back to top
    page.set_extra_http_headers({"Referer": TOP_URL})
    page.goto(LOGIN_URL)
    
    try:
        page.wait_for_selector('input[type="email"]', state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        print("Could not find the login form on the login page directly. Trying to click from top page as fallback...")
        page.goto(TOP_URL)
        page.wait_for_load_state("networkidle")
        # Try a very generic click on anything that says "ログイン"
        locators = page.locator("text=ログイン")
        if locators.count() > 0:
            locators.first.click()
            page.wait_for_selector('input[type="email"]', state="visible", timeout=15000)
        else:
            print("Fallback failed.")
            browser.close()
            return

    print("Entering credentials...")
    page.fill('input[type="email"]', POKEMON_CENTER_EMAIL)
    page.fill('input[type="password"]', POKEMON_CENTER_PASSWORD)
    
    print("Submitting login form...")
    page.keyboard.press("Enter") # Safest way to submit the form blindly
        
    # === STEP 3: Handle 2-Factor Authentication ===
    print("Checking for 2FA (パスコード) screen...")
    
    # Debug: see what happens after submit
    page.wait_for_timeout(3000)
    page.screenshot(path="post_login.png")
    
    try:
        # Wait for the passcode input field to appear. 
        # If it doesn't appear within 10 seconds, we might have bypassed it or failed login
        passcode_input = page.wait_for_selector('input[name="auth_code"]', state="visible", timeout=10000)
        
        if passcode_input:
            print("2FA Passcode screen detected!")
            print("Connecting to Gmail to fetch the passcode (this might take a few minutes)...")
            
            # We need the app password for this
            if not GMAIL_APP_PASSWORD or GMAIL_APP_PASSWORD == "your_16_character_app_password_here":
                print("ERROR: Gmail App Password is not set in .env!")
                print("Please set it to allow the bot to read your emails.")
                browser.close()
                return
            
            # Use a longer timeout as the user mentioned the email takes time to arrive
            passcode = gmail_reader.get_passcode_from_email(GMAIL_ADDRESS, GMAIL_APP_PASSWORD, max_retries=60, retry_delay=5)
            
            if passcode:
                print(f"Entering passcode: {passcode}")
                # Type the code slowly just in case
                page.fill('input[name="auth_code"]', passcode)
                time.sleep(1)
                
                print("Submitting passcode...")
                # Click the submit button for the passcode form
                page.click('input[alt="送信する"]')
                
                # Wait for login to complete (e.g. navigation back to top page or my page)
                page.wait_for_load_state("networkidle", timeout=10000)
                print("Login request sent.")
            else:
                print("Failed to retrieve the passcode from email. Stopping.")
                browser.close()
                return
    except PlaywrightTimeoutError:
        print("No 2FA screen detected. Checking if login was successful anyway...")
            
    # Save Verification / State
    print("Verifying final login state...")
    time.sleep(3) # Give it a moment to fully load the post-login screen
    
    # As the user requested incognito, we don't save the state to a file.
    # The session will be destroyed when the browser closes.
    
    print("=== Automation Complete ===")
    print("The browser will remain open for 10 seconds so you can verify.")
    time.sleep(10)
    
    browser.close()

if __name__ == "__main__":
    if not POKEMON_CENTER_EMAIL or not POKEMON_CENTER_PASSWORD:
        print("Missing basic credentials in .env file.")
        exit(1)
        
    with sync_playwright() as playwright:
        run(playwright)
