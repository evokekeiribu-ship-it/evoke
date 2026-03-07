import os, re, sys, json, math, glob, pathlib
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
OUT_DIR = os.path.join(BASE_DIR, "作成済み請求書")
SEAL_PATH = os.path.join(SCRIPT_DIR, "seal_b64.txt")
CHINAJUN_TMPL = os.path.join(SCRIPT_DIR, "chinajun_template.html")
OTHER_TMPL = os.path.join(SCRIPT_DIR, "テンプレート.html")  # それ以外は既存テンプレート流用

def generate_pdf(dest_type, dest_name, items):
    """
    dest_type: 'chinajun' or 'other'
    dest_name: 宛先名
    items: [{'name':str, 'unit':int, 'qty':int, 'total':int}, ...]
    """
    today = datetime.now()
    payment_date = today + timedelta(days=3)
    today_jp = today.strftime('%Y年%m月%d日')
    payment_date_jp = payment_date.strftime('%Y年%m月%d日')
    today_str = today.strftime('%Y%m%d')

    # --- 小計計算 ---
    subtotal = sum(it['total'] for it in items)

    # --- ちなじゅん用：手数料行を追加 ---
    if dest_type == 'chinajun':
        fee = -math.floor(subtotal * 0.02)
        items = list(items) + [{
            'name': f'手数料 全体×0.02',
            'unit': fee,
            'qty': 1,
            'total': fee
        }]

    # --- 合計・税抜き ---
    grand_total = sum(it['total'] for it in items)
    tax_excl = math.floor(grand_total / 1.1)

    # --- 出力ディレクトリ ---
    daily_folder = today.strftime('%Y-%m-%d')
    daily_out_dir = os.path.join(OUT_DIR, daily_folder)
    os.makedirs(daily_out_dir, exist_ok=True)

    # --- ファイル連番 ---
    safe_dest = re.sub(r'[\\/:*?"<>|]', '_', dest_name)
    prefix = f"{safe_dest}御中_{today_str}_"
    count = sum(1 for f in os.listdir(daily_out_dir) if f.startswith(prefix) and f.endswith('.pdf')) + 1
    file_no = f"{count:02}"
    invoice_no = f"{today_str}-P{file_no}"
    out_pdf_name = f"{prefix}{file_no}.pdf"
    out_pdf_path = os.path.join(daily_out_dir, out_pdf_name)

    # --- HTMLテンプレート読み込み ---
    tmpl_path = CHINAJUN_TMPL if dest_type == 'chinajun' else OTHER_TMPL
    with open(tmpl_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # --- seal ---
    try:
        with open(SEAL_PATH, 'r', encoding='utf-8') as f:
            seal_b64 = f.read().strip()
        html = html.replace('SEAL_BASE64', seal_b64.split(',', 1)[-1] if ',' in seal_b64 else seal_b64)
        # 既存テンプレート用にも対応
        html = re.sub(r'src="data:image/png;base64,[^"]*"', f'src="{seal_b64}"', html)
    except Exception as e:
        print(f"[WARN] seal load error: {e}")

    # --- 行HTML生成 ---
    rows_html = ''
    for i, it in enumerate(items):
        cls = 'even' if i % 2 == 0 else 'odd'
        unit_str = f"{'−' if it['unit'] < 0 else ''}¥{abs(it['unit']):,}"
        total_str = f"{'−' if it['total'] < 0 else ''}¥{abs(it['total']):,}"
        rows_html += f'''<tr>
            <td class="name-col">{it["name"]}</td>
            <td>{unit_str}</td>
            <td style="text-align:center;">{it["qty"]}</td>
            <td>{total_str}</td>
            <td></td>
        </tr>\n'''

    # --- プレースホルダー置換 ---
    if dest_type == 'chinajun':
        html = html.replace('<!-- RECIPIENT_NAME -->', dest_name)
        html = html.replace('<!-- PAYMENT_NO -->', invoice_no)
        html = html.replace('<!-- CREATED_DATE -->', today_jp)
        html = html.replace('<!-- PAYMENT_DATE -->', payment_date_jp)
        html = html.replace('<!-- PAYMENT_TOTAL -->', f'{grand_total:,}')
        html = html.replace('<!-- INVOICE_NO -->', 'T4120001206506')
        html = html.replace('<!-- ITEM_ROWS -->', rows_html)
        html = html.replace('<!-- SUBTOTAL -->', f'¥{grand_total:,}')
        html = html.replace('<!-- TAX_EXCL -->', f'¥{tax_excl:,}')
        html = html.replace('<!-- GRAND_TOTAL -->', f'¥{grand_total:,}')
    else:
        # それ以外用：既存テンプレートに合わせた置換
        html = re.sub(
            r'<div class="to-company"[^>]*>.*?</div>',
            f'<div class="to-company" style="font-size:16px;white-space:nowrap;"><span>{dest_name}</span><span style="margin-left:10px;">御 中</span></div>',
            html, flags=re.DOTALL
        )
        html = re.sub(r'id="invoice-no">.*?<', f'id="invoice-no">{invoice_no}<', html)
        html = html.replace('<!-- ITEM_ROWS -->', rows_html)
        # 合計金額
        html = re.sub(r'<div class="amount-value">\s*¥[0-9,]+\s*-\s*</div>', f'<div class="amount-value">¥{grand_total:,}-</div>', html)
        html = re.sub(r'<div class="t-val">\s*¥[0-9,]+\s*</div>', f'<div class="t-val">¥{grand_total:,}</div>', html)

    # --- HTML一時保存 ---
    temp_html = os.path.join(daily_out_dir, f"temp_{today_str}_p{file_no}.html")
    with open(temp_html, 'w', encoding='utf-8') as f:
        f.write(html)

    # --- Playwright PDF変換 ---
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        executable_path = None
        if os.name != 'nt':
            import glob as g
            pw_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
            candidates = []
            if pw_path:
                candidates += g.glob(os.path.join(pw_path, 'chromium-*', 'chrome-linux', 'chrome'))
            candidates += ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
            for c in candidates:
                if os.path.exists(c):
                    executable_path = c
                    break
        kwargs = {'headless': True, 'args': ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']}
        if executable_path:
            kwargs['executable_path'] = executable_path
        browser = p.chromium.launch(**kwargs)
        page = browser.new_page()
        uri = pathlib.Path(temp_html).resolve().as_uri()
        page.goto(uri, wait_until='load')
        page.evaluate('document.fonts.ready')
        page.wait_for_timeout(1000)
        page.pdf(path=out_pdf_path, format='A4', display_header_footer=False, print_background=True)
        browser.close()

    if os.path.exists(temp_html):
        os.remove(temp_html)

    return out_pdf_path


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--payment-json':
        try:
            payload = json.loads(sys.argv[2])
            dest_type = payload['destType']   # 'chinajun' or 'other'
            dest_name = payload['destName']
            items = payload['items']
            out = generate_pdf(dest_type, dest_name, items)
            print(f'___PDF_GENERATED___:{out}')
        except Exception as e:
            print(f'エラー: {e}', file=sys.stderr)
            sys.exit(1)
    else:
        print('使用方法: python payment_notice.py --payment-json \'{"destType":"chinajun","destName":"ちなじゅん運送","items":[...]}\'')
        sys.exit(1)
