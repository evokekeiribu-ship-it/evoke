import imaplib
import email
import re
from email.header import decode_header
import time
import datetime

# IMAP server settings
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993

def get_passcode_from_email(username, app_password, max_retries=10, retry_delay=5):
    """
    Connects to Gmail, finds the latest Pokemon Center 2FA email, and extracts the code.
    Retries multiple times as the email might take a few seconds to arrive.
    """
    print(f"Connecting to {IMAP_SERVER}...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(username, app_password)
    except imaplib.IMAP4.error as e:
        print(f"Login failed: {e}")
        print("Please check if your App Password is correct and IMAP is enabled in your Gmail settings.")
        return None

    mail.select("inbox")

    # The sender is usually exactly this, or we can just search subject
    # 'FROM "ポケモンセンターオンライン" SUBJECT "パスコード"' is often tricky with encoding in IMAP search
    # Instead, we pull recent emails and check them.
    
    # Let's define the window of time to look for (e.g., since today)
    date_str = datetime.date.today().strftime("%d-%b-%Y")
    search_criteria = f'(SINCE "{date_str}")'
    
    print("Waiting for the pass-code email to arrive...")
    for attempt in range(max_retries):
        status, messages = mail.search(None, search_criteria)
        if status != "OK":
            print("Failed to search emails.")
            break
            
        email_ids = messages[0].split()
        if not email_ids:
            print(f"[{attempt+1}/{max_retries}] No emails found today yet. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            continue
            
        # Check emails starting from the newest
        for e_id in reversed(email_ids):
            status, data = mail.fetch(e_id, '(RFC822)')
            if status != "OK":
                continue
                
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = decode_subject(msg["Subject"])
                    sender = msg.get("From")
                    
                    # Debug print to see what we are catching
                    # print(f"Checking email: Subject='{subject}', From='{sender}'")
                    
                    if "パスコード" in subject and "ポケモンセンターオンライン" in str(sender):
                        print("Found Pokemon Center 2FA email!")
                        body = get_email_body(msg)
                        code = extract_code(body)
                        
                        if code:
                            print(f"Successfully extracted code: {code}")
                            mail.logout()
                            return code
        
        print(f"[{attempt+1}/{max_retries}] Pokemon Center email not found yet. Retrying in {retry_delay}s...")
        time.sleep(retry_delay)

    print("Timeout: Could not find the pass-code email within the given time.")
    mail.logout()
    return None

def decode_subject(subject):
    if not subject:
        return ""
    decoded_list = decode_header(subject)
    decoded_subject = ""
    for decoded_string, charset in decoded_list:
        if isinstance(decoded_string, bytes):
            charset = charset or "utf-8"
            try:
                decoded_subject += decoded_string.decode(charset)
            except Exception:
                decoded_subject += decoded_string.decode("utf-8", errors="ignore")
        else:
            decoded_subject += decoded_string
    return decoded_subject

def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            try:
                body = part.get_payload(decode=True).decode()
                # Prefer plain text if available
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    return body
            except:
                pass
    else:
        try:
            return msg.get_payload(decode=True).decode()
        except:
            pass
    return ""

def extract_code(body):
    """
    Looks for a 6 digit number in the email body.
    Usually the email says something like "パスコード：123456"
    """
    if not body:
         return None
    # Look for 6 consecutive digits
    match = re.search(r'(?<!\d)(\d{6})(?!\d)', body)
    if match:
        return match.group(1)
    return None

# Simple manual test if run directly
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    username = os.getenv("EMAIL_ADDRESS")
    app_pw = os.getenv("GMAIL_APP_PASSWORD")
    
    if username and app_pw and app_pw != "your_16_character_app_password_here":
        print(f"Testing IMAP connection for {username}...")
        code = get_passcode_from_email(username, app_pw, max_retries=1)
        if code:
            print(f"Test Result: Found code {code}")
        else:
            print("Test Result: No code found in recent emails.")
    else:
        print("Please configure your .env file with GMAIL_APP_PASSWORD to test the IMAP connection.")
