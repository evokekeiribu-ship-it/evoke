import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

# ロガーの基本設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BrowserSkill:
    """
    特定のサイトで指定箇所を探し、クリックする操作を汎用化・スキル化したモジュール。
    """

    def __init__(self, driver: webdriver.Chrome):
        """
        :param driver: SeleniumのWebDriverインスタンス
        """
        self.driver = driver

    def find_and_click(self, locator: tuple, timeout: int = 10, retries: int = 3, scroll_to: bool = True) -> bool:
        """
        指定した要素をページ上から探し、確実にクリックするスキル。

        :param locator: 要素を特定するためのタプル (By, "値") (例: (By.ID, "submit-btn"))
        :param timeout: 要素が見つかるまでの最大待機時間（秒）
        :param retries: クリック失敗時（他の要素に覆われている等）の再試行回数
        :param scroll_to: 要素が画面外にある場合にスクロールして表示させるか
        :return: クリック成功時に True、失敗時に False
        """
        element_identifier = f"'{locator[1]}'"
        logger.info(f"要素 {element_identifier} を検索し、クリックを試みます...")

        for attempt in range(1, retries + 1):
            try:
                # 1. 要素が現れ、クリック可能になるまで待機
                wait = WebDriverWait(self.driver, timeout)
                element = wait.until(EC.element_to_be_clickable(locator))

                # 2. 必要に応じて要素の位置までスクロール
                if scroll_to:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.5) # スクロール後のUI安定化待ち

                # 3. クリックの実行
                # 通常のクリック
                try:
                    element.click()
                    logger.info(f"要素 {element_identifier} のクリックに成功しました。")
                    return True
                except ElementClickInterceptedException:
                    logger.warning(f"要素が他の要素に覆われています。JavaScriptによる強制クリックを試行します...")
                    # 覆われている場合はJSで直接クリック
                    self.driver.execute_script("arguments[0].click();", element)
                    logger.info(f"要素 {element_identifier} をJavaScriptでクリックしました。")
                    return True

            except TimeoutException:
                logger.error(f"タイムアウト: 要素 {element_identifier} は {timeout} 秒以内に見つからないか、クリック可能になりませんでした。")
                break # タイムアウトは再試行しても無駄なことが多いので抜ける
            except NoSuchElementException:
                logger.error(f"エラー: 要素 {element_identifier} がDOM上に存在しません。")
                break
            except Exception as e:
                logger.warning(f"試行 {attempt}/{retries} - 例外が発生しました: {e}")
                if attempt == retries:
                    logger.error(f"要素 {element_identifier} のクリックに最終的に失敗しました。")
                    return False
                time.sleep(1) # 再試行前の短い待機

        return False

    def input_text(self, locator: tuple, text: str, timeout: int = 10):
        """
        要素を探してテキストを入力するスキル（おまけ）
        """
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located(locator))
            # 要素までスクロール
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.2)
            element.clear()
            element.send_keys(text)
            
            # 一部のフロントエンドフレームワーク（React等）で値が認識されないケースを防ぐための強制イベント発行
            self.driver.execute_script("""
                let el = arguments[0];
                let val = arguments[1];
                let tracker = el._valueTracker;
                if (tracker) { tracker.setValue(el.value === val ? '' : el.value); }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            """, element, text)
            
            # 確実を期すため、キーボード操作で「スペースを入力してすぐ消す」というアクションを追加
            from selenium.webdriver.common.keys import Keys
            element.send_keys(Keys.SPACE)
            time.sleep(0.1)
            element.send_keys(Keys.BACKSPACE)
            
            logger.info(f"要素 '{locator[1]}' にテキストを入力しました。")
            return True
        except Exception as e:
            logger.error(f"テキスト入力中にエラーが発生しました: {e}")
            return False
