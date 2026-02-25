import os
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

OUT_DIR = os.path.join(BASE_DIR, "作成済み請求書")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "テンプレート.html")
SEAL_PATH = os.path.join(SCRIPT_DIR, "seal_b64.txt")

def generate_pdf(destination_name, qty, custom_date_str=None):
    if custom_date_str:
        today = datetime.strptime(custom_date_str, '%Y/%m/%d')
    else:
        today = datetime.now()
    deadline = today + timedelta(days=7)
    
    total = qty * 200
    items = [{
        'name': 'ピック依頼',
        'unit': 200,
        'qty': qty,
        'total': total
    }]

    today_str = today.strftime('%Y%m%d')
    today_mmdd = today.strftime('%m月%d日')
    today_jp = today.strftime('%Y年%m月%d日')
    deadline_jp = deadline.strftime('%Y年%m月%d日')

    # 日付ごとのフォルダを作成
    daily_folder_name = today.strftime('%Y-%m-%d')
    daily_out_dir = os.path.join(OUT_DIR, daily_folder_name)
    os.makedirs(daily_out_dir, exist_ok=True)

    count = 1
    file_prefix = f"{destination_name}御中{today_mmdd}-P"
    for fname in os.listdir(daily_out_dir):
        if fname.startswith(file_prefix) and fname.endswith(".pdf"):
            count += 1
            
    file_no = f"{count:02}"
    invoice_no = f"{today_str}-P{file_no}"
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

    # Replace company name
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

    temp_html = os.path.join(BASE_DIR, "pick_temp_render.html")
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

if __name__ == "__main__":
    destination_name = None
    qty = None
    custom_date_str = None

    if len(sys.argv) > 1:
        # CLI execution: python pick_invoice.py <dest_choice> <qty> [custom_date]
        if len(sys.argv) >= 3:
            dest_choice = sys.argv[1].strip()
            qty_input = sys.argv[2].strip()
            if dest_choice == '1':
                destination_name = "株式会社ミナミトランスポートレーション"
            elif dest_choice == '2':
                destination_name = "株式会社TUYOSHI"
            
            if qty_input.isdigit() and int(qty_input) > 0:
                qty = int(qty_input)

            if len(sys.argv) >= 4:
                date_input = sys.argv[3].strip()
                try:
                    datetime.strptime(date_input, '%Y/%m/%d')
                    custom_date_str = date_input
                except ValueError:
                    pass

    if destination_name is None or qty is None:
        print("========================================")
        print(" ピック依頼 請求書作成ツール")
        print("========================================")
        print("宛先を選択してください：")
        print("1: 株式会社ミナミトランスポートレーション")
        print("2: 株式会社TUYOSHI")
        
        while True:
            dest_choice = input("入力 (1 または 2): ").strip()
            if dest_choice == '1':
                destination_name = "株式会社ミナミトランスポートレーション"
                break
            elif dest_choice == '2':
                destination_name = "株式会社TUYOSHI"
                break
            else:
                print("エラー: 1 または 2 を入力してください。")
                
        while True:
            qty_input = input("ピック依頼の個数を入力してください: ").strip()
            if qty_input.isdigit() and int(qty_input) > 0:
                qty = int(qty_input)
                break
            else:
                print("エラー: 有効な数字（1以上の整数）を入力してください。")
                
        while True:
            date_input = input("請求日を指定しますか？ (例: 2026/02/22) ※本日の場合はそのままEnter: ").strip()
            if not date_input:
                break
            try:
                datetime.strptime(date_input, '%Y/%m/%d')
                custom_date_str = date_input
                break
            except ValueError:
                print("エラー: 正しい日付形式 (YYYY/MM/DD) で入力してください。")
            
    if destination_name is None or qty is None:
        print("エラー: 宛先または個数の指定が不完全です。プログラムを終了します。")
        sys.exit(1)

    date_display = custom_date_str if custom_date_str else "本日"
    print(f"\n[{destination_name}] 宛てに ピック依頼 (200円 x {qty}個 = {qty*200}円) 日付:{date_display} で請求書を作成します。")
    try:
        out_path = generate_pdf(destination_name, qty, custom_date_str)
        print(f"\n生成完了: {out_path}")
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        
    if len(sys.argv) <= 1:
        input("\nEnterキーを押して終了します...")
