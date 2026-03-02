import re

with open('w15_dump.txt', 'r', encoding='utf-8') as f:
    page_text = f.read()
    
text_lines = [line.strip() for line in page_text.split('\n') if line.strip()]

status_text = ""

for i, line in enumerate(text_lines):
    if line == "(進行中)" and i > 0:
        status_text = text_lines[i-1]
        break

if not status_text:
    completed_statuses = []
    for i, line in enumerate(text_lines):
        if line in ["注文確定", "処理中", "配送準備中", "出荷完了", "配送済み"]:
            if i+1 < len(text_lines) and text_lines[i+1] == "(完了)":
                completed_statuses.append(line)
    
    if completed_statuses:
        status_text = completed_statuses[-1]

print(f"Status extracted: '{status_text}'")
