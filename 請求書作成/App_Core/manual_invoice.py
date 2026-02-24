import os
import re
from datetime import datetime, timedelta
import sys
import math
from playwright.sync_api import sync_playwright

# Get the directory of the current script (App_Core)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Base directory is one level up from App_Core
BASE_DIR = os.path.dirname(SCRIPT_DIR)

# Output directory requested by the user: C:\Users\Owner\OneDrive\デスクトップ\deveropment\請求書作成\作成済み請求書
OUT_DIR = os.path.join(BASE_DIR, "作成済み請求書")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "テンプレート.html")
SEAL_PATH = os.path.join(SCRIPT_DIR, "seal_b64.txt")

def generate_pdf(destination_name, content_name, unit_price, qty, tax_type):
    today = datetime.now()
    deadline = today + timedelta(days=7)
    
    # tax_type: '1' = 税込み, '2' = 税抜き
    if tax_type == '1':
        # 税込み価格が入力された場合、そのまま合計
        total = unit_price * qty
    else:
        # 税抜き価格が入力された場合、消費税(10%)を加算
        total = math.floor(unit_price * qty * 1.1)

    items = [{
        'name': content_name,
        'unit': unit_price,
        'qty': qty,
        'total': total
    }]

    today_str = today.strftime('%Y%m%d')
    today_mmdd = today.strftime('%m月%d日')
    today_jp = today.strftime('%Y年%m月%d日')
    deadline_jp = deadline.strftime('%Y年%m月%d日')

    daily_folder_name = today.strftime('%Y-%m-%d')
    daily_out_dir = os.path.join(OUT_DIR, daily_folder_name)
    os.makedirs(daily_out_dir, exist_ok=True)

    # 既存の同日ファイルを探索して連番を付与
    count = 1
    safe_dest_name = re.sub(r'[\\/:*?"<>|]', '_', destination_name) # ファイル名に使えない文字をエスケープ
    file_prefix = f"{safe_dest_name}御中_{today_str}_"
    for fname in os.listdir(daily_out_dir):
        if fname.startswith(file_prefix) and fname.endswith(".pdf"):
            count += 1
            
    file_no = f"{count:02}"
    invoice_no = f"{today_str}-M{file_no}"
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

    # Replace company name (テンプレートのミナミトランスポートレーションを置換)
    html_content = re.sub(
        r'<div class=\"to-company\"[^>]*>.*?株式会社ミナミトランスポートレーション.*?御\s*中.*?</div>',
        f'<div class="to-company" style="font-size: 16px; white-space: nowrap;">\n                    <span>{destination_name}</span>\n                    <span style="margin-left: 10px;">御 中</span>\n                </div>',
        html_content,
        flags=re.DOTALL
    )

    html_content = re.sub(r'id=\"invoice-no\">.*?<', f'id="invoice-no">{invoice_no}<', html_content)
    html_content = re.sub(r'<th>請求 日 :</th>.*?<td>.*?<', f'<th>請求 日 :</th><td>{today_jp}<', html_content, flags=re.DOTALL)
    html_content = re.sub(r'\(\s*お支払い期限\s*\)</span>\s*<span>.*?</span>', f'( お支払い期限 )</span>\n                    <span>{deadline_jp}</span>', html_content, flags=re.DOTALL)

    # Generate rows HTML (pad up to 7 rows)
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
    html_content = re.sub(r'<div class=\"amount-value\">\s*¥[0-9,]+\s*-\s*</div>', f'<div class="amount-value">¥{total:,}-</div>', html_content)
    html_content = re.sub(r'<div class=\"t-val\">\s*¥[0-9,]+\s*</div>', f'<div class="t-val">¥{total:,}</div>', html_content)

    temp_html = os.path.join(daily_out_dir, f"temp_{today_str}_m{file_no}.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Convert HTML to PDF using Playwright
    with sync_playwright() as p:
        # Check if we are in a Linux environment (like Render) or Windows
        executable_path = None
        if os.name != 'nt':
            import glob
            # First, check if PLAYWRIGHT_BROWSERS_PATH is set (Render custom cache)
            pw_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
            if pw_path and os.path.exists(pw_path):
                # Look for chrome inside chromium-xxxx/chrome-linux/chrome
                search_pattern = os.path.join(pw_path, 'chromium-*', 'chrome-linux', 'chrome')
                matches = glob.glob(search_pattern)
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
        page.goto(f"file:///{temp_html.replace(chr(92), '/')}")
        page.wait_for_load_state("networkidle")
        # Ensure all web fonts (like Noto Sans JP) are fully loaded and applied
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1000) # Give 1 extra second for layout recalculation
        
        # A4 portrait without headers/footers
        page.pdf(path=out_pdf_path, format="A4", display_header_footer=False, print_background=True)
        browser.close()

    if os.path.exists(temp_html):
        os.remove(temp_html)
    return out_pdf_path

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("エラー: 必要な引数が不足しています。(宛先, 内容, 単価, 数量, 税区分)")
        sys.exit(1)

    dest_choice = sys.argv[1].strip()
    content_name = sys.argv[2].strip()
    unit_price = int(sys.argv[3].strip())
    qty = int(sys.argv[4].strip())
    tax_type = sys.argv[5].strip()

    try:
        out_path = generate_pdf(dest_choice, content_name, unit_price, qty, tax_type)
        print(f"\n生成完了: {out_path}")
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        sys.exit(1)
