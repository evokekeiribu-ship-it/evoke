import os
from datetime import datetime
from weasyprint import HTML, CSS

# フォルダ設定
BASE_DIR = r"C:\Users\Owner\OneDrive\デスクトップ\deveropment\請求書作成"
OUT_DIR = BASE_DIR

today = datetime.now()
today_str = today.strftime('%Y%m%d')
today_jp = today.strftime('%Y年%m月%d日')

# 請求書Noの採番
count = 1
for fname in os.listdir(OUT_DIR):
    if fname.startswith(f"{today_str}-") and fname.endswith(".pdf"):
        count += 1
invoice_no = f"{today_str}-{count:02}"
out_pdf_path = os.path.join(OUT_DIR, f"{invoice_no}.pdf")

print(f"Generating {out_pdf_path}...")

# HTMLテンプレートの読み込みと置換
html_path = os.path.join(BASE_DIR, "invoice_template.html")
with open(html_path, "r", encoding="utf-8") as f:
    html_content = f.read()

# Noと日付を置換
import re
html_content = re.sub(r'id=\"invoice-no\">.*?<', f'id="invoice-no">{invoice_no}<', html_content)
html_content = re.sub(r'<th>請求 日 :</th>.*?<td>.*?<', f'<th>請求 日 :</th><td>{today_jp}<', html_content, flags=re.DOTALL)

# HTMLからPDF生成 (WeasyPrint)
# A4サイズを強制し、マージンを0にして100%のサイズ感で出力する
custom_css = CSS(string='''
    @page { size: A4; margin: 0; }
    body { font-family: "Meiryo", sans-serif; background: #fff; margin: 0; }
''')

HTML(string=html_content, base_url=BASE_DIR).write_pdf(out_pdf_path, stylesheets=[custom_css])

print("Finished generation!")
os.startfile(out_pdf_path)
