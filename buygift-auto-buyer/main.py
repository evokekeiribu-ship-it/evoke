import yaml
import time
import logging
import sys
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException

# 独自作成スキルのインポート
from browser_skill import BrowserSkill

# ロガーの基本設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BuyGiftAutoBuyer:
    def __init__(self, config_path="config.yaml"):
        # 設定の読み込み
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        # Selenium WebDriverの初期化設定
        chrome_options = Options()
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        # chrome_options.add_argument("--headless") # ヘッドレス（画面非表示）で動かしたい場合はコメントアウトを外す

        logger.info("Chromeブラウザを起動しています...")
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        self.driver.implicitly_wait(5) # 要素が見つかるまでのデフォルト待機時間
        
        # 共通クリック処理スキルのインスタンス化
        self.skill = BrowserSkill(self.driver)

    def login(self):
        """BUYGIFTへのログイン処理（手動）"""
        login_url = "https://buygift.app/users/signin"
        self.driver.get(login_url)
        logger.info("=========================================")
        logger.info("ログイン画面を開きました。")
        logger.info("※サイトの堅牢なBot対策により自動入力が制限されているため、")
        logger.info("  ブラウザ上で「手動で」メールアドレスとパスワードを入力し、")
        logger.info("  ログインボタンを押してください。")
        logger.info("  ログイン状態が確認でき次第、自動で監視システムが起動します。")
        logger.info("  （待機タイムアウト時間：300秒）")
        logger.info("=========================================")
        
        self.send_line_notification("\n🔄【自動購入bot】ブラウザが起動し待機状態に入りました！\n表示されているChromeブラウザで、5分以内にメールアドレスとパスワードを入力して手動でログインを完了させてください。")
        
        # ページ遷移を待機（手動ログイン完了・認証突破を待つ）
        for _ in range(150): # 150 * 2秒 = 300秒間（5分）待機
            time.sleep(2)
            if "signin" not in self.driver.current_url:
                logger.info("ログインに成功し、システム画面に遷移したことを確認しました！監視処理に移行します。")
                return
        
        logger.error("ログイン後、一定時間（5分）経過しても出品画面等への遷移が確認されませんでした。システムを終了します。")
        sys.exit(1)

    def monitor_and_buy(self):
        """Appleギフトカードページの監視と購入条件判定"""
        target_url = self.config['app']['target_url']
        interval = self.config['app']['check_interval']
        
        min_price = self.config['purchase_conditions']['min_price']
        max_price = self.config['purchase_conditions']['max_price']
        min_rate = self.config['purchase_conditions']['min_discount_rate']
        allowed_sellers = self.config['purchase_conditions'].get('allowed_sellers', [])

        logger.info(f"監視を開始します URL: {target_url}")
        logger.info(f"条件: 額面 {min_price}円 ～ {max_price}円、割引率 {min_rate}%以上")
        
        self.driver.get(target_url)
        time.sleep(2)

        while True:
            try:
                # ページをリロードして最新の情報を取得
                self.driver.refresh()
                time.sleep(1.5) # 描画待ち
                
                # もし未ログイン状態でログイン画面にリダイレクトされている場合は再ログイン
                if "signin" in self.driver.current_url:
                    logger.warning("ログアウト状態を検知しました。再度ログインを試みます。")
                    self.login()
                    self.driver.get(target_url)
                    continue
                
                # CSS Modulesの可変クラス名に対応するため、主要なコンテナの特徴等に依存するXPathや部分一致クラスを使用
                # 調査結果に基づくアイテム行の取得
                items = self.driver.find_elements(By.CSS_SELECTOR, "div[class*='styles_gift_table__']")
                
                found_target = False
                for item in items:
                    try:
                        # 調査の結果、1つの .styles_gift_table__ 内に複数の商品データが結合されて入っている（または親要素を取得しすぎている）ことが判明しました。
                        # 以下のように「円」や「%」といった単位キーワードをトリガーにしたステートマシンで、
                        # 結合されたテキストの中から個別の出品データセットを順次切り出して判定します。
                        lines = item.text.split('\n')
                        
                        idx = 0
                        while idx < len(lines):
                            # 各アイテムの先頭は必ず「出品個数 (例: 1)」「"枚"」で始まると仮定して探す
                            # あるいは、一番特徴的な「%」と「出品者名」を起点に過去の要素を特定する方が確実
                            price = 0
                            display_rate = 0.0
                            seller_name = ""
                            
                            # 1商品分のデータをパースする（次の商品が来るかリストが終わるまで）
                            # 典型的には: [枚数, '枚', 額面, '円', 販売価格, '円', 割引率, '%', 出品者名, '購入']
                            if idx + 9 < len(lines) and lines[idx+1] == '枚' and lines[idx+3] == '円' and lines[idx+5] == '円' and lines[idx+7] == '%':
                                try:
                                    price = int(lines[idx+2].replace(',', ''))
                                    display_rate = float(lines[idx+6])
                                    seller_name = lines[idx+8]
                                except ValueError:
                                    idx += 1
                                    continue
                                
                                discount_rate = round(100.0 - display_rate, 2)
                                logger.debug(f"抽出: 出品者={seller_name}, 額面={price}円, 販売率={display_rate}%, 割引率={discount_rate}%")
                                
                                # 条件判定
                                if min_price <= price <= max_price and discount_rate >= min_rate:
                                    if not allowed_sellers or seller_name in allowed_sellers:
                                        logger.info(f"★★★ 狙い目のアイテムを発見！ [出品者:{seller_name} 額面:{price}円 割引率:{discount_rate}% (表示{display_rate}%)]")
                                        found_target = True
                                        
                                        # 期待される条件を見つけたことを共有
                                        logger.info(f">>> 条件に合致しました。購入手続きを開始します。")
                                        notify_message = f"\n🚨【購入実行】条件に合致したため購入を試みます！\n\n出品者: {seller_name}\n額面: {price}円\n割引率: {discount_rate}%"
                                        self.send_line_notification(notify_message)
                                        
                                        # 購入処理（「購入」ボタンを押す準備）
                                        try:
                                            # 親要素内の全ボタン（divタグで実装されている）を取得
                                            all_btns = item.find_elements(By.XPATH, ".//div[contains(@class, 'globalbuttonpurchase')]")
                                            btn_index = idx // 10
                                            
                                            if all_btns: # ボタンが1つ以上見つかった場合
                                                if btn_index < len(all_btns):
                                                    buy_btn = all_btns[btn_index]
                                                else:
                                                    buy_btn = all_btns[0]
                                                    
                                                # ==== 本番稼働：購入ボタンをクリック ====
                                                # divタグで作られたボタン等への対応として、まず要素が見えるようにスクロールし、通常のクリックを試みてからJSでの強制クリックを行う
                                                self.driver.execute_script("arguments[0].scrollIntoView(true);", buy_btn)
                                                time.sleep(0.5)
                                                try:
                                                    buy_btn.click()
                                                except Exception:
                                                    self.driver.execute_script("arguments[0].click();", buy_btn)
                                                
                                                logger.info("一覧から「購入」ボタンをクリックしました。次のページへの遷移を待ちます...")
                                                
                                                # 購入確定画面の描画を待つため、sleep時間を増やすかURL遷移明示待ちを追加
                                                time.sleep(8)
                                                
                                                # 続く購入ステータス（決済）画面の処理へ
                                                self._process_checkout()
                                            else:
                                                error_msg = f"⚠️【エラー停止】出品者 {seller_name} の購入ボタン要素が見つかりませんでした。システムを停止します。"
                                                logger.error(error_msg)
                                                self.send_line_notification(f"\n{error_msg}")
                                                sys.exit(1)
                                                
                                            break # 1件処理したら内部ループを抜ける
                                        except Exception as btn_e:
                                            error_msg = f"⚠️【エラー停止】ボタン取得・クリック中に予期せぬエラーが発生しました: {btn_e}"
                                            logger.error(error_msg)
                                            self.send_line_notification(f"\n{error_msg}")
                                            sys.exit(1)
                                            
                                # 1商品分（通常10要素＝"購入"まで）スキップして次の商品へ
                                idx += 10
                            else:
                                idx += 1
                                
                        if found_target:
                            break # 外側のループも抜ける
                                
                    except NoSuchElementException as e:
                        # 必要な情報が要素内にない場合（ヘッダ行など）はスキップ
                        logger.debug(f"要素内パーススキップ: {e}")
                        continue
                    except Exception as e:
                        logger.debug(f"アイテム解析中の予期せぬエラー: {e}")
                        continue
                        
                if found_target:
                    # 購入が完了した（または失敗した）後の処理。再度監視に戻る場合は一旦数秒待機。
                    logger.info("購入シーケンスが終了しました。10秒後に監視を再開します。")
                    time.sleep(10)
                    self.driver.get(target_url) # 監視ページに戻る
                else:
                    # 条件に合うアイテムが見つからなければ、一定時間待機してループ先頭（リロード）に戻る
                    logger.info(f"条件に合致する出品がありません。{interval}秒後に再確認します。")
                    time.sleep(interval)
                    
            except Exception as e:
                error_msg = f"💥【異常終了】監視ループ内で重大なエラーが発生しました: {e}"
                logger.error(error_msg)
                self.send_line_notification(f"\n{error_msg}")
                sys.exit(1)

    def send_line_notification(self, message):
        """LINEに通知を送信する"""
        notify_config = self.config.get('notification', {})
        notify_token = notify_config.get('line_notify_token', "")
        
        # 1. LINE Notifyが設定されている場合
        if notify_token:
            headers = {"Authorization": f"Bearer {notify_token}"}
            data = {"message": message}
            try:
                requests.post("https://notify-api.line.me/api/notify", headers=headers, data=data)
                logger.info("LINE Notifyで通知を送信しました。")
            except Exception as e:
                logger.error(f"LINE Notify送信エラー: {e}")
                
        # 2. LINE Messaging API (Push) が設定されている場合
        ch_token = notify_config.get('line_channel_access_token', "")
        user_id = notify_config.get('line_user_id', "")
        if ch_token and user_id:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {ch_token}"
            }
            data = {
                "to": user_id,
                "messages": [{"type": "text", "text": message}]
            }
            try:
                requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
                logger.info("LINE Messaging APIで通知を送信しました。")
            except Exception as e:
                logger.error(f"LINE Messaging API送信エラー: {e}")

    def _process_checkout(self):
        """カート追加〜購入確定・残高不足判定までの処理"""
        logger.info(f"決済確認画面へ移行しました。（現在URL: {self.driver.current_url}）")
        time.sleep(2)
        
        # ユーザー指示: 「次のページにいって、購入するを押すと実際に購入になるよ」
        # "購入する" のテキストが含まれる最終ボタンを探す
        confirm_btn_locator = (By.XPATH, "//button[contains(., '購入する')]")
        
        # 本番実行時（専用スキルを使って確実にクリックさせる）
        logger.info(">>> 次のページで「購入する」ボタンを探してクリックします...")
        if self.skill.find_and_click(confirm_btn_locator):
             logger.info("購入確定処理が送信されました。結果判定を待ちます...")
             time.sleep(4) # 処理待ち
             
             # 購入結果の判定（「残高が不足しています」等のエラーメッセージが出ていないか確認）
             if "残高が不足しています" in self.driver.page_source or "残高不足" in self.driver.page_source:
                 logger.error("🚨 エラー: 残高不足のため購入に失敗しました。直ちにチャージしてください！")
                 self.send_line_notification("\n🚨【残高不足】自動購入に失敗しました。BUYGIFTの残高が不足しています！")
             else:
                 logger.info("購入完了画面が表示されました（成功したとみなします）。")
                 self.send_line_notification("\n✅【購入完了】ギフト券の自動購入処理が成功しました！")
        else:
             logger.error("購入確定ボタンが見つからないか、クリックできませんでした。")
             self.send_line_notification("\n⚠️【エラー】決済画面へ移行しましたが、購入確定ボタンが見つからずタイムアウトしました。")

    def run(self):
        try:
            self.login()
            self.monitor_and_buy()
        finally:
            logger.info("ブラウザを終了します...")
            self.driver.quit()

if __name__ == "__main__":
    bot = BuyGiftAutoBuyer()
    bot.run()
