import os
import re
from datetime import datetime, timedelta

from google.cloud import vision
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# load environment variables for Google Cloud credentials
load_dotenv()

# Get the directory of the current script (App_Core)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Base directory is one level up from App_Core
BASE_DIR = os.path.dirname(SCRIPT_DIR)

IN_DIR = os.path.join(BASE_DIR, "請求書作成依頼")
OUT_DIR = os.path.join(BASE_DIR, "作成済み請求書")

TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "テンプレート.html")
SEAL_PATH = os.path.join(SCRIPT_DIR, "seal_b64.txt")

def generate_pdf(invoice_data):
    today = invoice_data['today']
    deadline = invoice_data['deadline']
    items = invoice_data['items']

    today_str = today.strftime('%Y%m%d')
    today_mmdd = today.strftime('%m月%d日')
    today_jp = today.strftime('%Y年%m月%d日')
    deadline_jp = deadline.strftime('%Y年%m月%d日')

    # 日付ごとのフォルダを作成
    daily_folder_name = today.strftime('%Y-%m-%d')
    daily_out_dir = os.path.join(OUT_DIR, daily_folder_name)
    os.makedirs(daily_out_dir, exist_ok=True)

    count = 1
    file_prefix = f"株式会社ミナミトランスポートレーション御中{today_mmdd}-"
    for fname in os.listdir(daily_out_dir):
        if fname.startswith(file_prefix) and fname.endswith(".pdf"):
            count += 1
            
    file_no = f"{count:02}"
    invoice_no = f"{today_str}-{file_no}"
    out_pdf_name = f"{file_prefix}{file_no}.pdf"
    out_pdf_path = os.path.join(daily_out_dir, out_pdf_name)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    try:
        with open(SEAL_PATH, "r", encoding="utf-8") as f:
            full_b64_string = f.read().strip()
        html_content = re.sub(r'src=\"data:image/png;base64,[^\"]*\"', f'src="{full_b64_string}"', html_content)
    except Exception as e:
        print("Base64 injection error: ", e)

    html_content = re.sub(r'id=\"invoice-no\">.*?<', f'id="invoice-no">{invoice_no}<', html_content)
    html_content = re.sub(r'<th>請求 日 :</th>.*?<td>.*?<', f'<th>請求 日 :</th><td>{today_jp}<', html_content, flags=re.DOTALL)
    html_content = re.sub(r'\(\s*お支払い期限\s*\)</span>\s*<span>.*?</span>', f'( お支払い期限 )</span>\n                    <span>{deadline_jp}</span>', html_content, flags=re.DOTALL)

    total_sum = sum(it['total'] for it in items)
    
    # Generate rows HTML
    rows_html = ""
    total_rows = max(7, len(items))
    for i in range(total_rows):
        cls = "even" if i % 2 == 0 else "odd"
        if i < len(items):
            it = items[i]
            rows_html += f'''
                <tr class="{cls}">
                    <td>{it["name"]}</td>
                    <td>{it["unit"]:,}</td>
                    <td>{it["qty"]}</td>
                    <td>{it["total"]:,}</td>
                </tr>'''
        else:
            rows_html += f'''
                <tr class="{cls}">
                    <td>&nbsp;</td>
                    <td></td>
                    <td></td>
                    <td></td>
                </tr>'''
    
    html_content = html_content.replace('<!-- ITEM_ROWS -->', rows_html)

    # Replace total block
    # Note: need to capture existing total accurately
    html_content = re.sub(r'<div class=\"amount-value\">\s*¥[0-9,]+\s*-\s*</div>', f'<div class="amount-value">¥{total_sum:,}-</div>', html_content)
    html_content = re.sub(r'<div class=\"t-val\">\s*¥[0-9,]+\s*</div>', f'<div class="t-val">¥{total_sum:,}</div>', html_content)

    html_content = html_content.replace('font-size: 13px;', 'font-size: 11px;')
    html_content = html_content.replace('font-size: 14px;', 'font-size: 12px;')
    html_content = html_content.replace('margin-top: 40px;', 'margin-top: 20px;')
    html_content = html_content.replace('margin-bottom: 30px;', 'margin-bottom: 20px;')
    html_content = html_content.replace('padding: 12px;', 'padding: 8px;')
    html_content = html_content.replace('height: 297mm;', 'height: 293mm;')
    html_content = html_content.replace('width: 52%;', 'width: 58%;')
    html_content = html_content.replace('width: 18%;', 'width: 15%;')
    html_content = html_content.replace('width: 10%;', 'width: 6%;')
    html_content = html_content.replace('width: 20%;', 'width: 21%;')

    temp_html = os.path.join(BASE_DIR, "temp_render.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Creating PDF: {out_pdf_name}")
    with sync_playwright() as p:
        # Check if we are in a Linux environment (like Render) or Windows
        executable_path = None
        if os.name != 'nt':
            import glob
            # First, check if PLAYWRIGHT_BROWSERS_PATH is set (Render custom cache)
            pw_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
            if pw_path and os.path.exists(pw_path):
                # Look for chrome inside chromium-xxxx/chrome-linux/chrome
                search_pattern = os.path.join(pw_path, '**', 'chrome')
                matches = glob.glob(search_pattern, recursive=True)
                if matches:
                    executable_path = matches[0]
            
            # Fallback to standard system paths
            if not executable_path:
                linux_paths = [
                    "/usr/bin/chromium", 
                    "/usr/bin/chromium-browser",
                    "/usr/bin/google-chrome"
                ]
                for path_choice in linux_paths:
                    if os.path.exists(path_choice):
                        executable_path = path_choice
                        break
        if executable_path:
            print(f"[DEBUG] Launching Playwright with explicit chromium path: {executable_path}")
            browser = p.chromium.launch(headless=True, executable_path=executable_path, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote'])
        else:
            print("[DEBUG] Launching Playwright with default bundled chromium")
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote'])
            
        page = browser.new_page()
        import pathlib
        uri = pathlib.Path(temp_html).resolve().as_uri()
        page.goto(uri, wait_until="load")
        # Ensure all web fonts (like Noto Sans JP) are fully loaded and applied
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1000) # Give 1 extra second for layout recalculation
        page.pdf(path=out_pdf_path, format="A4", display_header_footer=False, print_background=True)
        browser.close()

    if os.path.exists(temp_html):
        os.remove(temp_html)
    return out_pdf_path

def run_ocr_on_all():
    files = [f for f in os.listdir(IN_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf'))]
    if not files: return
    
    from google.oauth2 import service_account
    
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    fallback_path = os.path.join(os.path.dirname(BASE_DIR), "google-credentials.json")
    render_secret_path = "/etc/secrets/google-credentials.json"
    
    print(f"[DEBUG] creds_path from env: {creds_path} (exists: {os.path.exists(creds_path) if creds_path else False})")
    print(f"[DEBUG] fallback_path: {fallback_path} (exists: {os.path.exists(fallback_path)})")
    print(f"[DEBUG] render_secret_path: {render_secret_path} (exists: {os.path.exists(render_secret_path)})")
    
    try:
        if creds_path and os.path.exists(creds_path):
            print("[DEBUG] Using creds_path")
            creds = service_account.Credentials.from_service_account_file(creds_path)
            client = vision.ImageAnnotatorClient(credentials=creds)
        elif os.path.exists(fallback_path):
            print("[DEBUG] Using fallback_path")
            creds = service_account.Credentials.from_service_account_file(fallback_path)
            client = vision.ImageAnnotatorClient(credentials=creds)
        elif os.path.exists(render_secret_path):
            print("[DEBUG] Using render_secret_path")
            creds = service_account.Credentials.from_service_account_file(render_secret_path)
            client = vision.ImageAnnotatorClient(credentials=creds)
        else:
            print("[DEBUG] Using default ADC")
            client = vision.ImageAnnotatorClient()
    except Exception as e:
        print(f"[ERROR] Failed to initialize Vision client: {e}")
        raise e
    
    for filename in files:
        print(f"Processing image: {filename}")
        img_path = os.path.join(IN_DIR, filename)
        try:
            with open(img_path, 'rb') as image_file:
                content = image_file.read()
            image = vision.Image(content=content)
            response = client.document_text_detection(image=image)
            
            if response.error.message:
                raise Exception(f"{response.error.message}")

            full_text = response.full_text_annotation.text

            # Find date
            match_date = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', full_text)
            today = datetime.now()
            if match_date:
                y, m, d = int(match_date.group(1)), int(match_date.group(2)), int(match_date.group(3))
                today = datetime(y, m, d)
            deadline = today + timedelta(days=7)

            words_info = []
            for page in response.full_text_annotation.pages:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            word_text = ''.join([symbol.text for symbol in word.symbols])
                            # Google Vision returns bounding boxes with vertices. We compute a simple bounding rect.
                            vertices = word.bounding_box.vertices
                            min_x = min([v.x for v in vertices])
                            min_y = min([v.y for v in vertices])
                            words_info.append((min_y, min_x, word_text))

            words_info.sort(key=lambda w: w[0])
            
            rows = []
            current_row = []
            last_y = -100
            for y, x, text in words_info:
                if abs(y - last_y) > 15 and current_row:
                    current_row.sort(key=lambda w: w[1])
                    rows.append(" ".join([w[2] for w in current_row]))
                    current_row = []
                current_row.append((y, x, text))
                if len(current_row) == 1:
                    last_y = y
            if current_row:
                current_row.sort(key=lambda w: w[1])
                rows.append(" ".join([w[2] for w in current_row]))
                
            target_subtotal = 0
            for row in rows:
                if '計' in row and '消費' not in row:
                    nums = re.findall(r'\b\d{1,3}(?:[ ,\s]*\d{3})+\b', row)
                    if not nums:
                        # Fallback for completely unformatted large numbers
                        clean_row = row.replace(' ', '').replace(',', '')
                        nums = re.findall(r'\b\d{4,}\b', clean_row)
                    if nums:
                        try:
                            val = int(nums[-1].replace(' ', '').replace(',', ''))
                            if val > 1000:
                                target_subtotal = val
                        except: pass

            items = []
            items = []
                
            items = []
            for row in rows:
                if '計' in row:
                    print(f"  [RAW SUBTOTAL ROW] {row}")
                k = row.lower()
                if 'iphone' in k or 'apple' in k or 'sim' in k or '未開封' in k or 'playstation' in k or 'piaystation' in k or 'station' in k or 'switch' in k or 'instax' in k or 'コントローラー' in k or 'チェキ' in k or 'phone' in k or 'stax' in k or 'ps5' in k or 'ディスク' in k or 'ワンピース' in k or '一番くじ' in k or 'フィギュア' in k or 'カード' in k or 'box' in k or 'パック' in k or 'ポケモン' in k or 'デッキ' in k or 'スタート' in k:
                    name_clean = row
                    name_clean = re.sub(r'\bPhone\b', 'iPhone', name_clean, flags=re.I)
                    name_clean = re.sub(r'(?<!SI)M FREE', 'SIM FREE', name_clean, flags=re.I)
                    name_clean = re.sub(r'\bnstax\b', 'instax', name_clean, flags=re.I)
                    name_clean = re.sub(r'PIayStation', 'PlayStation', name_clean, flags=re.I)
                    name_clean = re.sub(r'SIi\s*m|Sli\s*m', 'Slim', name_clean, flags=re.I)
                    name_clean = re.sub(r'F\s*ト|CF\s*ト', 'CFI-', name_clean, flags=re.I)
                    name_clean = re.sub(r'Ni\s*ntendo|Nintend0', 'Nintendo', name_clean, flags=re.I)
                    name_clean = name_clean.replace('  ', ' ')
                    
                    row_clean = re.sub(r'\b\d{13}\b', '', name_clean)
                    row_clean = re.sub(r'\s*,\s*', ',', row_clean)
                    row_clean = re.sub(r'\s+([¥円])', r'\1', row_clean)
                    
                    prices_str = re.findall(r'\b\d{1,3}(?:,\d{3})+\b', row_clean)
                    
                    unit, qty, total = 0, 0, 0
                    valid = False
                    
                    if len(prices_str) >= 2:
                        p1 = int(prices_str[0].replace(',', ''))
                        p2 = int(prices_str[-1].replace(',', ''))
                        if p1 > 1000 and p2 >= p1 and p2 % p1 == 0 and p2 // p1 < 100:
                            unit, total, qty = p1, p2, p2 // p1
                            valid = True
                            
                    if not valid and len(prices_str) == 1:
                        p_str = prices_str[0]
                        parts = p_str.split(',')
                        if len(parts) >= 2:
                            unit = int(parts[0] + parts[1])
                            qty = 1
                            total = unit
                            valid = True
                            
                    if not valid:
                        digits = re.sub(r'[^\d]', '', row_clean)
                        for lt in range(3, 8):
                            if lt > len(digits): break
                            total_str = digits[-lt:]
                            if not total_str.isdigit() or int(total_str) == 0: continue
                            tot = int(total_str)
                            
                            for lu in range(3, 8):
                                if lt + lu > len(digits): break
                                unit_str = digits[-(lt+lu):-lt]
                                if not unit_str.isdigit() or int(unit_str) == 0: continue
                                un = int(unit_str)
                                
                                rem = digits[:-(lt+lu)]
                                q = int(rem) if rem.isdigit() and int(rem) > 0 else 0
                                
                                if 0 < q < 100 and q * un == tot:
                                    unit, qty, total = un, q, tot
                                    valid = True
                                    break
                                elif q == 0 and un > 0 and tot % un == 0 and tot // un < 100:
                                    unit, qty, total = un, tot // un, tot
                                    valid = True
                                    break
                            if valid: break
                    if unit == 0:
                        continue
                        
                    name = re.sub(r'[\d\s,¥円]+$', '', name_clean).strip()
                    name = re.sub(r'^(?:品番・品名|単価|小計|金額|数量)+', '', name).strip()
                    items.append({'name': name, 'unit': unit, 'qty': qty, 'total': unit * qty})

            print(f"DEBUG EARLY: filename {filename} len(items)={len(items)}")

            if target_subtotal > 0:
                current_subtotal = sum(it['total'] for it in items)
                if current_subtotal < target_subtotal:
                    diff = target_subtotal - current_subtotal
                    for it in items:
                        if it['unit'] > 0 and diff % it['unit'] == 0:
                            missing_qty = diff // it['unit']
                            if 0 < missing_qty < 50:
                                print(f"Auto-correcting {it['name']} qty from {it['qty']} to {it['qty'] + missing_qty} based on subtotal diff {diff}")
                                it['qty'] += missing_qty
                                it['total'] = it['unit'] * it['qty']
                                current_subtotal += missing_qty * it['unit']
                                diff = target_subtotal - current_subtotal
                                if diff == 0:
                                    break

            for it in items:
                name = it['name']
                unit = it['unit']
                if 'iphone' in name.lower() or unit >= 20000:
                    unit -= 100
                else:
                    unit -= 20
                it['unit'] = unit
                it['total'] = unit * it['qty']

            if not items:
                print(f"No items found for {filename}")
                continue

            print(f"DEBUG: filename {filename} len(items)={len(items)}")
            for idx, debug_it in enumerate(items):
                print(f"DEBUG item {idx}: {debug_it['name']}")
            
            invoice_data = {
                'today': today,
                'deadline': deadline,
                'items': items
            }
            pdf_path = generate_pdf(invoice_data)
            print(f" -> Generated {os.path.basename(pdf_path)}")
            
        except Exception as e:
            import sys
            print(f"Failed {filename}: {e}".encode('cp932', errors='replace').decode('cp932'))
            sys.exit(1)

if __name__ == "__main__":
    try:
        print("[DEBUG] batch_gen.py execution started.")
        run_ocr_on_all()
        print("[DEBUG] batch_gen.py execution finished successfully.")
    except Exception as e:
        import traceback
        print(f"[FATAL_ERROR] batch_gen.py crashed with exception: {e}")
        traceback.print_exc()
        raise e
