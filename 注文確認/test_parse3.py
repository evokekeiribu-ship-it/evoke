with open('w15_dump.txt', 'r', encoding='utf-8') as f:
    page_text = f.read()
    
text_lines = [line.strip() for line in page_text.split('\n') if line.strip()]

status_text = ""

reached_phases = []
for i, line in enumerate(text_lines):
    if line in ["注文確定", "処理中", "配送準備中", "出荷完了", "配送済み"]:
        if i+1 < len(text_lines):
            next_line = text_lines[i+1]
            if next_line in ["(完了)", "(進行中)", "（完了）", "（進行中）"]:
                reached_phases.append(line)
                
if reached_phases:
    status_text = reached_phases[-1]

print(f"Status extracted: '{status_text}'")
