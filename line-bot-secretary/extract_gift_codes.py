import sys
import re

def main():
    print("テキストを貼り付けてください。（貼り付け後、Windowsの場合は Ctrl+Z を押し、その後 Enter を押すと抽出を実行します）:")
    try:
        # 標準入力からテキストをすべて読み込む
        text = sys.stdin.read()
    except KeyboardInterrupt:
        print("\nキャンセルされました。")
        return

    # BuyGiftで販売されているAppleギフトカード（主にXから始まる16桁の英数字）を想定
    # ※Amazon等他のギフト券の場合、正規表現のパターンの調整が必要です
    apple_pattern = r'\bX[A-Z0-9]{15}\b'
    codes = re.findall(apple_pattern, text)

    # X始まりで見つからなかった場合は、単なる16桁の大文字英数字を探す
    if not codes:
        generic_pattern = r'\b[A-Z0-9]{16}\b'
        codes = re.findall(generic_pattern, text)
        
    # Amazonギフト券（例: AQ12-34R567-890VB）のような形式も念のためサポートする場合：
    # amazon_pattern = r'\b[A-Z0-9]{4}-[A-Z0-9]{6}-[A-Z0-9]{5}\b'
    # codes.extend(re.findall(amazon_pattern, text))

    if codes:
        # 重複を排除して元の順序を維持
        unique_codes = list(dict.fromkeys(codes))
        print("\n=== 抽出結果 ===")
        print("\n".join(unique_codes))
    else:
        print("\n一致するギフト券番号が見つかりませんでした。")

if __name__ == "__main__":
    main()
