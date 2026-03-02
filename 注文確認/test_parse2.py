with open('w15_dump.txt', 'r', encoding='utf-8') as f:
    page_text = f.read()
    
text_lines = [line.strip() for line in page_text.split('\n') if line.strip()]

for i, line in enumerate(text_lines):
    if "(進行中)" in line or "処理中" in line or "注文確定" in line:
        print(f"Line {i}: {repr(line)}")
