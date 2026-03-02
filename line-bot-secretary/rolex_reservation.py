import json
import time
from playwright.sync_api import sync_playwright

# 設定ファイルのパス
CONFIG_FILE = "rolex_config.json"
# ヒルトン大阪 ロレックス来店予約ページのURL
RESERVATION_URL = "https://reservation.rolexboutique-hiltonplaza-osaka.jp/osaka-umeda/reservation"

def load_config():
    """設定ファイルを読み込む"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"エラー: {CONFIG_FILE} が見つかりません。作成してから実行してください。")
        exit(1)
    except json.JSONDecodeError:
        print(f"エラー: {CONFIG_FILE} の形式が正しくありません。JSON形式を確認してください。")
        exit(1)

def main():
    config = load_config()
    
    print("=== ロレックス ヒルトン大阪 来店予約 補助スクリプト ===")
    print("ブラウザを起動しています...")

    # Playwrightを起動
    with sync_playwright() as p:
        # headless=False にすることで実際のブラウザを表示（手動操作のため必須）
        # channel="chrome" でPCにインストールされているChromeを使用
        try:
            browser = p.chromium.launch(headless=False, channel="chrome")
        except Exception as e:
            print("Chromeが見つからないため、内蔵ブラウザで起動します。")
            browser = p.chromium.launch(headless=False)
            
        context = browser.new_context()
        page = context.new_page()

        print(f"予約ページ（{RESERVATION_URL}）にアクセスしています...")
        page.goto(RESERVATION_URL)

        print("-" * 50)
        print("【重要】")
        print("現在は受付期間外、または抽選ページの内容が変更されている可能性があります。")
        print("ページが表示されたら、以下の操作を手動で行ってください：")
        print("1. 希望日時やモデルを選択する")
        print("2. スクリプトがフォーム入力欄を見つけたら自動入力します")
        print("3. SMS認証（電話番号へのコード）を受け取る")
        print("4. CAPTCHA（画像認証・私はロボットではありません）をクリアする")
        print("5. 確定ボタンを押す")
        print("-" * 50)

        # フォームの要素が現れるまで待機
        # ※実際のサイトのHTML構造に応じてセレクタ（idやnameなど）を修正する必要があります
        # 以下は一般的なフォーム要素を想定した仮のセレクタです。
        # 実際の受付開始時にHTMLを確認し、適宜書き換えてください。
        
        selectors = {
            "last_name_kanji": "input[name='lastName'], input[placeholder*='姓']",
            "first_name_kanji": "input[name='firstName'], input[placeholder*='名']",
            "last_name_kana": "input[name='lastNameKana'], input[placeholder*='セイ']",
            "first_name_kana": "input[name='firstNameKana'], input[placeholder*='メイ']",
            "email": "input[type='email'], input[name='email']",
            "phone_number": "input[type='tel'], input[name='phoneData']"
        }

        print("フォーム要素を探しています...")
        
        # フォーム要素が見つかったら自動入力
        try:
            # 姓（漢字）の入力
            page.wait_for_selector(selectors["last_name_kanji"], timeout=30000)
            page.fill(selectors["last_name_kanji"], config["last_name_kanji"])
            print("姓（漢字）を入力しました。")

            # 名（漢字）の入力
            page.fill(selectors["first_name_kanji"], config["first_name_kanji"])
            print("名（漢字）を入力しました。")

            # 姓（カナ）の入力
            page.fill(selectors["last_name_kana"], config["last_name_kana"])
            print("姓（カナ）を入力しました。")

            # 名（カナ）の入力
            page.fill(selectors["first_name_kana"], config["first_name_kana"])
            print("名（カナ）を入力しました。")

            # メールアドレスの入力
            page.fill(selectors["email"], config["email"])
            print("メールアドレスを入力しました。")

            # 電話番号の入力
            page.fill(selectors["phone_number"], config["phone_number"])
            print("電話番号を入力しました。")
            
            print("\n自動入力が完了しました。")
            print("引き続き、ブラウザ上で【SMS認証】と【確定・送信】を行ってください。")

        except Exception as e:
            print(f"\n自動入力エラー: フォーム要素が見つかりませんでした。")
            print("ページがロードされていないか、HTMLの構造が想定と異なる可能性があります。")
            print("手動で入力を行ってください。")
            # print(e) # デバッグ用

        # ブラウザを閉じないようにループで待機
        print("\nブラウザを閉じるまでスクリプトは待機しています...")
        print("終了するには、ブラウザの「×」ボタンを押すか、ここでCtrl+Cを押してください。")
        try:
            while len(context.pages) > 0:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nスクリプトを終了します。")
        finally:
            browser.close()

if __name__ == "__main__":
    main()
