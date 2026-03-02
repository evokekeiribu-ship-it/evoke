import csv
import os
import urllib.request
import json
import glob

def send_line_broadcast(message_text):
    env_path = r'C:\Users\Owner\OneDrive\デスクトップ\deveropment\line-bot-secretary\.env'
    token = ''
    try:
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('LINE_CHANNEL_ACCESS_TOKEN='):
                        token = line.strip().split('=', 1)[1].strip()
                        break
    except Exception as e:
        print(f'LINE トークンの読み込みに失敗しました: {e}')
        return

    if not token:
        print('LINE_CHANNEL_ACCESS_TOKEN が見つかりません。')
        return

    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    data = {
        'messages': [
            {
                'type': 'text',
                'text': message_text
            }
        ]
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print(f'!!! LINE通知エラー: {e}')
        
def main():
    files = glob.glob("orders_result_*.csv")
    if not files:
        print("No csv found")
        return
        
    latest_file = max(files, key=os.path.getctime)
    lines = ['【最新 全注文ステータス一覧】\n']
    count = 0
    try:
        with open(latest_file, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                keys = list(row.keys())
                if not keys: continue
                order_num = row.get(keys[0], '').strip()
                status = row.get('注文状況', '').strip()
                
                # Skip delivered/canceled to keep it short
                if status in ['配送済み', 'キャンセル済み']:
                    continue
                
                device = f"{row.get('機種名', '')} {row.get('ギガ数', '')} {row.get('色', '')} {row.get('台数', '')}".strip()
                
                lines.append(f'[*] {order_num}')
                if device: lines.append(f'機種: {device}')
                lines.append(f'状況: {status}\n')
                count += 1
                
        if count == 0:
            lines.append('現在、進行中の注文はありません。')
            
        lines.append(f'({latest_file} より取得)')
        msg = '\n'.join(lines).strip()
        print('Sending message...')
        send_line_broadcast(msg)
        print('Done!')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    main()
