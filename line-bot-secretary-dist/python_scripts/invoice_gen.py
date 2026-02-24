import os
import asyncio
import re
from datetime import datetime, timedelta
import subprocess

from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage import StorageFile

# =========================================================
# === 設定項目（ご自身の環境・ビジネスに合わせて変更してください） ===
# =========================================================

# 1. PDFに記載される宛先（あなたのお客様の会社名など）
CLIENT_NAME = "株式会社〇〇 御中"

# 2. 抽出したい商品名のキーワード群
# レシートから拾い出したい商品名の一部を小文字でリストアップしてください
KEYWORD_LIST = [
    'iphone', 'apple', 'sim', '未開封', 'playstation', 
    'station', 'switch', 'instax', 'コントローラー', 
    'チェキ', 'ps5', 'ディスク'
]

# 3. 利益の自動差し引き設定（仕入れ値から利益を抜いて請求書を作る場合）
# True にすると、商品の単価から自動で指定の金額を差し引きます
USE_AUTO_MARGIN = True

def adjust_margin(item_name, original_unit_price):
    """
    ここで商品名や単価に応じた「利益抜き（マイナス）」のルールを設定できます。
    デフォルトでは、2万円以上またはiPhoneなら100円引き、それ以外は20円引きの例です。
    """
    if 'iphone' in item_name.lower() or original_unit_price >= 20000:
        return original_unit_price - 100
    else:
        return original_unit_price - 20

# =========================================================
# === 以下、システム制御用（通常は変更不要です） ===
# =========================================================

# パスの設定 (index.js と連携するため、１つ上の階層にフォルダを作ります)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) 

IN_DIR = os.path.join(BASE_DIR, "invoice_in")
OUT_DIR = os.path.join(BASE_DIR, "invoice_out")

TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "テンプレート.html")
SEAL_PATH = os.path.join(SCRIPT_DIR, "seal_b64.txt")

# Edgeブラウザのパス（HTMLからPDFへの変換に使用します）
edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(edge_exe):
    edge_exe = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

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
    file_prefix = f"{CLIENT_NAME}{today_mmdd}-"
    for fname in os.listdir(daily_out_dir):
        if fname.startswith(file_prefix) and fname.endswith(".pdf"):
            count += 1
            
    file_no = f"{count:02}"
    invoice_no = f"{today_str}-{file_no}"
    out_pdf_name = f"{file_prefix}{file_no}.pdf"
    out_pdf_path = os.path.join(daily_out_dir, out_pdf_name)

    # テンプレートHTMLの読み込み
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    # ハンコ画像の埋め込み
    try:
        if os.path.exists(SEAL_PATH):
            with open(SEAL_PATH, "r", encoding="utf-8") as f:
                full_b64_string = f.read().strip()
            html_content = re.sub(r'src=\"data:image/png;base64,[^\"]*\"', f'src="{full_b64_string}"', html_content)
    except Exception as e:
        print("Base64 injection error: ", e)

    # 日付・請求番号の置換
    html_content = re.sub(r'id=\"invoice-no\">.*?<', f'id="invoice-no">{invoice_no}<', html_content)
    html_content = re.sub(r'<th>請求 日 :</th>.*?<td>.*?<', f'<th>請求 日 :</th><td>{today_jp}<', html_content, flags=re.DOTALL)
    html_content = re.sub(r'\(\s*お支払い期限\s*\)</span>\s*<span>.*?</span>', f'( お支払い期限 )</span>\n                    <span>{deadline_jp}</span>', html_content, flags=re.DOTALL)

    total_sum = sum(it['total'] for it in items)
    
    # 明細行の生成（最大7行、または明細数に合わせて拡張）
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

    # 合計金額の置換
    html_content = re.sub(r'<div class=\"amount-value\">\s*¥[0-9,]+\s*-\s*</div>', f'<div class="amount-value">¥{total_sum:,}-</div>', html_content)
    html_content = re.sub(r'<div class=\"t-val\">\s*¥[0-9,]+\s*</div>', f'<div class="t-val">¥{total_sum:,}</div>', html_content)

    # 見た目の微調整（文字サイズや余白）
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

    # 一時保存用のHTMLを作成
    temp_html = os.path.join(BASE_DIR, "temp_render.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Creating PDF: {out_pdf_name}")
    # EdgeのHeadlessモードを利用してHTMLをPDF化
    cmd = [edge_exe, "--headless", "--disable-gpu", "--print-to-pdf-no-header", f"--print-to-pdf={out_pdf_path}", temp_html]
    subprocess.run(cmd, check=True)
    
    # PDF化が終わったら一時ファイルを削除
    if os.path.exists(temp_html):
        os.remove(temp_html)
        
    return out_pdf_path

async def run_ocr_on_all():
    # 入力フォルダ内の画像を検索
    if not os.path.exists(IN_DIR):
        print(f"Directory not found: {IN_DIR}")
        return
        
    files = [f for f in os.listdir(IN_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf'))]
    if not files: 
        print("No images found to process.")
        return
    
    # Windows10/11標準のOCRエンジンを使用
    engine = OcrEngine.try_create_from_user_profile_languages()
    
    for filename in files:
        print(f"Processing image: {filename}")
        img_path = os.path.join(IN_DIR, filename)
        try:
            file = await StorageFile.get_file_from_path_async(img_path)
            stream = await file.open_async(0)
            decoder = await BitmapDecoder.create_async(stream)
            sw_bitmap = await decoder.get_software_bitmap_async()
            result = await engine.recognize_async(sw_bitmap)
            
            # 日付の抽出
            match_date = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', result.text)
            today = datetime.now()
            if match_date:
                y, m, d = int(match_date.group(1)), int(match_date.group(2)), int(match_date.group(3))
                today = datetime(y, m, d)
            deadline = today + timedelta(days=7) # 支払い期限は7日後に設定

            # 単語と座標を取得してソート
            words_info = []
            for line in result.lines:
                for word in line.words:
                    words_info.append((word.bounding_rect.y, word.bounding_rect.x, word.text))
            words_info.sort(key=lambda w: w[0])
            
            # 同じ行（Y座標が近いもの）をまとめる
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
                
            # 合計金額の特定
            target_subtotal = 0
            for row in rows:
                if '計' in row and '消費' not in row:
                    nums = re.findall(r'\b\d{1,3}(?:[ ,\s]*\d{3})+\b', row)
                    if not nums:
                        clean_row = row.replace(' ', '').replace(',', '')
                        nums = re.findall(r'\b\d{4,}\b', clean_row)
                    if nums:
                        try:
                            val = int(nums[-1].replace(' ', '').replace(',', ''))
                            if val > 1000:
                                target_subtotal = val
                        except: pass

            # 明細の抽出
            items = []
            for row in rows:
                k = row.lower()
                # 商品名のキーワードが含まれているか判定
                if any(keyword in k for keyword in KEYWORD_LIST):
                    name_clean = row
                    
                    # 機種依存文字や表記ゆれの修正
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

            # 総合計と一致しない場合の数量補正
            if target_subtotal > 0:
                current_subtotal = sum(it['total'] for it in items)
                if current_subtotal < target_subtotal:
                    diff = target_subtotal - current_subtotal
                    for it in items:
                        if it['unit'] > 0 and diff % it['unit'] == 0:
                            missing_qty = diff // it['unit']
                            if 0 < missing_qty < 50:
                                it['qty'] += missing_qty
                                it['total'] = it['unit'] * it['qty']
                                current_subtotal += missing_qty * it['unit']
                                diff = target_subtotal - current_subtotal
                                if diff == 0:
                                    break

            # === 利益抜きの処理（設定ONの場合のみ） ===
            if USE_AUTO_MARGIN:
                for it in items:
                    it['unit'] = adjust_margin(it['name'], it['unit'])
                    it['total'] = it['unit'] * it['qty']
            # ==========================================

            if not items:
                print(f"No items found for {filename}")
                continue
            
            invoice_data = {
                'today': today,
                'deadline': deadline,
                'items': items
            }
            
            # PDF化の実行
            pdf_path = generate_pdf(invoice_data)
            print(f" -> Generated {os.path.basename(pdf_path)}")
            
        except Exception as e:
            print(f"Failed {filename}: {e}".encode('cp932', errors='replace').decode('cp932'))

if __name__ == "__main__":
    asyncio.run(run_ocr_on_all())
