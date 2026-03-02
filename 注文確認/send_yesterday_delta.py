import csv
import os
import glob
import json
import urllib.request
from datetime import datetime

def send_line_broadcast(message_text):
    env_path = r'C:\Users\Owner\OneDrive\デスクトップ\deveropment\line-bot-secretary\.env'
    token = ''
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('LINE_CHANNEL_ACCESS_TOKEN='):
                    token = line.strip().split('=', 1)[1].strip()
                    break
    if not token:
        print('LINE_CHANNEL_ACCESS_TOKEN が見つかりません。')
        return

    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    data = {'messages': [{'type': 'text', 'text': message_text}]}
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        urllib.request.urlopen(req)
        print("LINE sent.")
    except Exception as e:
        print(f"!!! LINE通知エラー: {e}")

def main():
    files = glob.glob("orders_result_*.csv")
    if len(files) < 2:
        print("Not enough files to compare.")
        return
        
    # Sort files by modification time
    files.sort(key=os.path.getmtime)
    
    # Get all files from "today" (last modified date)
    latest_file = files[-1]
    today_date = datetime.fromtimestamp(os.path.getmtime(latest_file)).date()
    
    # Find the latest file from a previous day
    previous_file = None
    for f in reversed(files):
        f_date = datetime.fromtimestamp(os.path.getmtime(f)).date()
        if f_date < today_date:
            previous_file = f
            break
            
    if not previous_file:
        print("Could not find a file from a previous day.")
        return
        
    print(f"Comparing {previous_file} and {latest_file}")
    
    old_data = {}
    with open(previous_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys = list(row.keys())
            if keys:
                old_data[row[keys[0]].strip()] = row.get("注文状況", "").strip()
                
    line_lines = ["昨日からのステータス変更報告\n"]
    changes = False
    
    with open(latest_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys = list(row.keys())
            if not keys: continue
            order_num = row[keys[0]].strip()
            new_status = row.get("注文状況", "").strip()
            
            old_status = old_data.get(order_num, "")
            
            if not old_status:
                pass # skip new ones if we only want diff? actually new ones are changes
                device_info = f"{row.get('機種名', '')} {row.get('ギガ数', '')} {row.get('色', '')} {row.get('台数', '')}".strip()
                line_lines.append(f"[*] 注文番号: {order_num}")
                if device_info: line_lines.append(f"機種: {device_info}")
                line_lines.append(f"【新規】 -> 【今回】{new_status}\n")
                changes = True
            elif old_status != new_status:
                device_info = f"{row.get('機種名', '')} {row.get('ギガ数', '')} {row.get('色', '')} {row.get('台数', '')}".strip()
                line_lines.append(f"[*] 注文番号: {order_num}")
                if device_info: line_lines.append(f"機種: {device_info}")
                line_lines.append(f"【前回】{old_status} -> 【今回】{new_status}\n")
                changes = True

    if not changes:
        line_lines.append("昨日からステータスが進んだ注文はありませんでした。")
        
    msg = "\n".join(line_lines).strip()
    send_line_broadcast(msg)

if __name__ == '__main__':
    main()
