import csv
import time
import datetime
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

import datetime

import glob
import os
import urllib.request
import json

# 設定
INPUT_CSV = "orders.csv"          # 読み込むCSVファイルの名前
# 結果保存用ファイル名（エクセルで開いている最中も書き出せるよう時刻をつける）
OUTPUT_CSV = f"orders_result_{datetime.datetime.now().strftime('%H%M%S')}.csv"
URL = "https://www.apple.com/jp/shop/order/list"

def get_previous_results():
    # 最も新しい過去のorders_result_*.csvを見つける
    files = glob.glob("orders_result_*.csv")
    if not files:
        return {}
        
    latest_file = max(files, key=os.path.getctime)
    previous_data = {}
    try:
        with open(latest_file, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 辞書のキーに使用する注文番号を取得（最初の列と仮定）
                keys = list(row.keys())
                if keys:
                    order_num = row.get(keys[0], "").strip()
                    if order_num:
                        previous_data[order_num] = row
        print(f"--- 前回データ ({latest_file}) を読み込みました ---")
    except Exception as e:
        print(f"前回データの読み込みに失敗しました: {e}")
        
    return previous_data

def send_line_broadcast(message_text):
    # .env ファイルのパス (line-bot-secretary フォルダ内)
    env_path = r"C:\Users\Owner\OneDrive\デスクトップ\deveropment\line-bot-secretary\.env"
    token = ""
    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("LINE_CHANNEL_ACCESS_TOKEN="):
                        token = line.strip().split("=", 1)[1].strip()
                        break
    except Exception as e:
        print(f"LINE トークンの読み込みに失敗しました: {e}")
        return

    if not token:
        print("LINE トークンが見つかりませんでした。LINE通知はスキップします。")
        return

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as res:
            print(">>> [LINE] への通知を送信しました。")
    except Exception as e:
        print(f"!!! LINE通知エラー: {e}")

def cleanup_old_files(days=2):
    """指定した日数より古い結果ファイルと報告ファイルを削除する"""
    now = time.time()
    cutoff = now - (days * 86400)
    
    deleted_count = 0
    patterns = ["orders_result_*.csv", "status_changes_*.txt"]
    
    for pattern in patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path):
                    # ファイルの最終更新日時を取得
                    t = os.path.getmtime(file_path)
                    if t < cutoff:
                        os.remove(file_path)
                        deleted_count += 1
            except Exception as e:
                print(f"古いファイルの削除中にエラーが発生しました ({file_path}): {e}")
                
    if deleted_count > 0:
         print(f"--- {days}日以上経過した古いログファイルを {deleted_count} 件削除しました ---")

def check_orders():
    print(">>> スプレッドシート（CSV）の読み込みを開始します...")
    
    # CSVからデータの読み込み
    try:
        with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            orders = list(reader)
    except UnicodeDecodeError:
        # もし UTF-8 でダメなら Windows 標準の Shift-JIS (cp932) で読み直す
        with open(INPUT_CSV, mode="r", encoding="cp932") as f:
            reader = csv.DictReader(f)
            orders = list(reader)
    except FileNotFoundError:
        print(f"!!! エラー: '{INPUT_CSV}' が見つかりません。")
        print("スプレッドシートからダウンロードしたファイルを、このプログラムと同じフォルダに配置し、名前を 'orders.csv' に変更してください。")
        return
    except Exception as e:
         print(f"!!! エラー: CSVの読み込みに失敗しました ({e})")
         return


    print(f"### {len(orders)}件のデータを読み込みました。ブラウザを起動して確認を開始します。")
    previous_results = get_previous_results()
    results = []

    with Stealth().use_sync(sync_playwright()) as p:
        # ブラウザの起動 (headless=False で実際の画面を表示します)
        # channel="chrome" を指定することで、bot検知されにくいPC本体のChromeを使用します。
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 初回はページの読み込み（JavaScriptなど）に時間がかかり、5秒でタイムアウトするため一度アクセスしておく
        print(">>> ブラウザの準備中（初回アクセス）...")
        page.goto(URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#signIn\\.orderLookUp\\.orderNumber", timeout=15000)
        except:
            pass
        time.sleep(2)

        for idx, row in enumerate(orders):
            keys = list(row.keys())
            if len(keys) >= 2:
                order_number = row.get(keys[0], "").strip()
                email = row.get(keys[1], "").strip()
            else:
                order_number = ""
                email = ""
            
            if not order_number or not email:
                print(f"--- {idx+1}行目: ご注文番号またはメールアドレスが空欄のためスキップします。")
                continue
                
            print(f"*** [{idx+1}/{len(orders)}] 注文番号: {order_number} を検索中...")
            
            # キャンセル・配送済みの場合はスキップ
            if order_number in previous_results:
                prev_row = previous_results[order_number]
                prev_status = prev_row.get("注文状況", "").strip()
                if prev_status in ["キャンセル済み", "配送済み"]:
                    print(f"    -> 前回 '{prev_status}' のため、情報取得をスキップします。")
                    row["注文状況"] = prev_status
                    row["日付"] = prev_row.get("日付", "")
                    row["機種名"] = prev_row.get("機種名", "")
                    row["ギガ数"] = prev_row.get("ギガ数", "")
                    row["色"] = prev_row.get("色", "")
                    row["台数"] = prev_row.get("台数", "")
                    results.append(row)
                    continue
            
            success = False
            for attempt in range(3):
                try:
                    # Apple Store ゲスト注文検索ページへ移動
                    page.goto(URL, wait_until="domcontentloaded")
                    
                    # 入力欄が表示されるまで待機（最大15秒）
                    page.wait_for_selector("#signIn\\.orderLookUp\\.orderNumber", timeout=15000)
                    
                    # ご注文番号とメールアドレスを入力
                    page.fill("#signIn\\.orderLookUp\\.emailAddress", email)
                    page.fill("#signIn\\.orderLookUp\\.orderNumber", order_number)
                    
                    # 検索ボタンをクリック
                    page.click("#signIn\\.orderLookUp\\.guestUserOrderLookUp")
                    
                    # 画面が切り替わるまで少し待機（2秒）
                    time.sleep(2)
                    # 注文詳細ページの読み込み完了を待機 (特定の要素が出現するのを待つなど状況により調整)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except:
                         pass
    
                    # TODO: 実際の注文詳細ページからステータス（処理中など）のテキストを取得する処理を記述
                    # 現在は仮のステータスを取得できたものとして扱う
                    
                    # 具体的なステータス要素が不明なため、ページ全体のテキストから推測するか、
                    # ノンブレークスペースを通常のスペースに変換
                    page_text = page.locator("body").inner_text().replace('\xa0', ' ')
                    text_lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                    
                    # --- 日付の抽出 ---
                    date_text = ""
                    # 「到着」「お届け」「配達」などのキーワードの後ろにある日付単体、または期間を抽出
                    date_pattern = r'(\d{4}(?:年|/)\d{1,2}(?:月|/)\d{1,2}日?(?:\s*(?:-|〜)\s*\d{1,4}(?:年|/)?\d{1,2}(?:月|/)\d{1,2}日?)?)'
                    match = re.search(r'(?:到着|お届け|配達|予定)[\s：:]*' + date_pattern, page_text)
                    
                    if match:
                        date_text = match.group(1)
                    else:
                        # キーワードが見つからない場合は、日付らしい文字列をすべて抽出
                        all_dates = re.findall(date_pattern, page_text)
                        if len(all_dates) > 1:
                            # 1つ目は「注文日」なので、2つ目（または最後）を到着日として採用
                            date_text = all_dates[-1]
                    # --- ステータス抽出 ---
                    status_text = ""
                    if "お探しのページが見つかりません" in page_text or "入力された情報と一致するご注文が見つかりません" in page_text or "正しいメールアドレスを入力" in page_text:
                        status_text = "エラー: 注文が見つかりません"
                        date_text = ""
                    elif "キャンセル済み" in page_text:
                        status_text = "キャンセル済み"
                        date_text = "" # キャンセルの場合は日付不要
                    else:
                        # 進行中のステータスを探す (Appleのプログレスバー仕様に対応)
                        for i, line in enumerate(text_lines):
                            if line == "(進行中)" and i > 0:
                                status_text = text_lines[i-1]
                                break
                        
                        # 進行中が見つからない場合(すべて完了している場合など)
                        if not status_text:
                            completed_statuses = []
                            for i, line in enumerate(text_lines):
                                if line in ["注文確定", "処理中", "配送準備中", "出荷完了", "配送済み"]:
                                    if i+1 < len(text_lines) and text_lines[i+1] == "(完了)":
                                        completed_statuses.append(line)
                            
                            if completed_statuses:
                                # 進行状態が一番進んでいる一番最後のものを取得
                                status_text = completed_statuses[-1]
                                    
                        if not status_text:
                            # プログレスバーがない場合の最終手段
                            if "配送済み" in page_text: status_text = "配送済み"
                            elif "出荷完了" in page_text: status_text = "出荷完了"
                            elif "配送準備中" in page_text: status_text = "配送準備中"
                            elif "処理中" in page_text: status_text = "処理中"
                            else: status_text = "注文確定"
    
                    # --- 機種情報 (機種名、ギガ数、色、台数) の抽出 ---
                    model_text, capacity_text, color_text, qty_text = "", "", "", ""
                    device_counts = {}
                    
                    for line in text_lines:
                        # 例: "iPhone 17 Pro 256GB シルバー"
                        match_device = re.match(r'^(iPhone.+?)\s+(\d{2,4}(?:GB|TB))\s+(.+)$', line, re.IGNORECASE)
                        if match_device:
                            m_name = match_device.group(1).strip()
                            # "iPhone " を削除
                            m_name = re.sub(r'^iPhone\s*', '', m_name, flags=re.IGNORECASE).strip()
                            
                            m_cap = match_device.group(2).strip()
                            # "GB" または "TB" を削除して数字だけにする
                            m_cap = re.sub(r'(GB|TB)$', '', m_cap, flags=re.IGNORECASE).strip()
                            
                            m_col = match_device.group(3).strip()
                            key = (m_name, m_cap, m_col)
                            device_counts[key] = device_counts.get(key, 0) + 1
                            
                    if device_counts:
                        ml, cl, col_l, ql = [], [], [], []
                        for (m_name, m_cap, m_col), qty in device_counts.items():
                            ml.append(m_name)
                            cl.append(m_cap)
                            col_l.append(m_col)
                            ql.append(f"{qty}台")
                        
                        model_text = " / ".join(ml)
                        capacity_text = " / ".join(cl)
                        color_text = " / ".join(col_l)
                        qty_text = " / ".join(ql)
                    else:
                        # 失敗時のフォールバック（機種名だけ取得）
                        match_fallback = re.search(r'(iPhone\s+(?:\d+|SE)(?:\s+(?:Pro|Max|Plus|mini))*)', page_text, re.IGNORECASE)
                        if match_fallback:
                            m_name_fb = match_fallback.group(1).strip()
                            model_text = re.sub(r'^iPhone\s*', '', m_name_fb, flags=re.IGNORECASE).strip()
                            
                    # すでに到着(出荷完了・配送済み)しているもの以外は日付を消定す
                    if status_text not in ["出荷完了", "配送済み"]:
                        date_text = ""
                    
                    print(f"+++ 結果: {status_text} (日付: {date_text}, 機種: {model_text} {capacity_text} {color_text} {qty_text})")
                    success = True
                    break # 成功したらループを抜ける
                    
                except Exception as e:
                    print(f"!!! エラー (試行 {attempt+1}/3): {e}")
                    if attempt < 2:
                        print("    -> 5秒後に再試行します...")
                        time.sleep(5)
            
            if not success:
                status_text = "エラー: 取得失敗(リトライ上限)"
                date_text = ""
                model_text, capacity_text, color_text, qty_text = "", "", "", ""
            
            # 結果を保存リストに追加
            row["注文状況"] = status_text
            row["日付"] = date_text
            row["機種名"] = model_text
            row["ギガ数"] = capacity_text
            row["色"] = color_text
            row["台数"] = qty_text
            results.append(row)
            
            # 連続アクセスでブロックされないよう少し待機
            time.sleep(1)

        browser.close()

    # 結果を新しいCSVに保存
    print(">>> 結果を保存しています...")
    if results:
         fieldnames = list(results[0].keys())
         # もし元のCSVに "注文状況" 列がなければ追加
         if "注文状況" not in fieldnames:
             fieldnames.append("注文状況")

         try:
             # Excelで文字化けしないよう BOM付きUTF-8 (utf-8-sig) で書き出す
             with open(OUTPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
                 writer = csv.DictWriter(f, fieldnames=fieldnames)
                 writer.writeheader()
                 writer.writerows(results)
             print(f"*** 完了しました！結果は '{OUTPUT_CSV}' に保存されています。")
         except Exception as e:
             print(f"!!! エラー: 結果の保存に失敗しました ({e})")
             
    # 変更があったものだけを最後にまとめて報告
    report_lines = []
    line_report_lines = []
    
    report_lines.append("==============================================")
    report_lines.append("               ステータス変更報告")
    report_lines.append("==============================================")
    
    line_report_lines.append("ステータス変更報告\n")
    
    changes_found = False
    for row in results:
        # 最初の列（注文番号が入っているはずの列）を取得
        keys = list(row.keys())
        if not keys: continue
         
        order_num = row.get(keys[0], "").strip()
        new_status = row.get("注文状況", "").strip()
        # previous_resultsは各行の辞書を格納している
        old_row = previous_results.get(order_num, {})
        old_status = old_row.get("注文状況", "").strip() if old_row else ""
         
        if not old_status:
            report_lines.append(f"[*] 注文番号: {order_num}")
            
            device_info = f'{row.get("機種名", "")} {row.get("ギガ数", "")} {row.get("色", "")} {row.get("台数", "")}'.strip()
            if device_info:
                report_lines.append(f"   機種: {device_info}")
                
            report_lines.append(f"   【新規】 ->  【今回】{new_status}")
            
            line_report_lines.append(f"[*] 注文番号: {order_num}")
            if device_info:
                line_report_lines.append(f"機種: {device_info}")
            line_report_lines.append(f"【新規】 -> 【今回】{new_status}\n")
            
            changes_found = True
        elif old_status != new_status:
            report_lines.append(f"[*] 注文番号: {order_num}")
            
            device_info = f'{row.get("機種名", "")} {row.get("ギガ数", "")} {row.get("色", "")} {row.get("台数", "")}'.strip()
            if device_info:
                report_lines.append(f"   機種: {device_info}")
                
            report_lines.append(f"   【前回】{old_status}  ->  【今回】{new_status}")
            
            line_report_lines.append(f"[*] 注文番号: {order_num}")
            if device_info:
                line_report_lines.append(f"機種: {device_info}")
            line_report_lines.append(f"【前回】{old_status} -> 【今回】{new_status}\n")
            
            changes_found = True
             
    if not changes_found:
        if not previous_results:
            report_lines.append("前回データが存在しなかったため、比較は行われませんでした。")
            line_report_lines.append("前回データが存在しなかったため、比較は行われませんでした。")
        else:
            report_lines.append("[OK] 前回からステータスが進んだ注文はありませんでした。")
            line_report_lines.append("前回からステータスが進んだ注文はありませんでした。")
            
    report_lines.append("==============================================")
    
    report_text = "\n".join(report_lines)
    line_text = "\n".join(line_report_lines).strip()
    print("\n" + report_text + "\n")
    
    # 差分結果をテキストファイル出力
    report_filename = f"status_changes_{datetime.datetime.now().strftime('%H%M%S')}.txt"
    try:
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"*** 変更報告を '{report_filename}' に出力しました。")
    except Exception as e:
        print(f"!!! エラー: 変更報告の保存に失敗しました ({e})")
        
    # LINEに通知を送信 (変更があった場合のみ)
    if changes_found:
        send_line_broadcast(line_text)
        
    # 古いファイルのクリーンアップ（2日以上前のものを削除）
    cleanup_old_files(days=2)
    
if __name__ == "__main__":
    check_orders()
