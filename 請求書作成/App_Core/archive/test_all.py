import asyncio
import os
import re
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage import StorageFile

IN_DIR = r"C:\Users\Owner\OneDrive\デスクトップ\deveropment\請求書作成\請求書作成依頼"

async def test_all():
    engine = OcrEngine.try_create_from_user_profile_languages()
    for fname in os.listdir(IN_DIR):
        if not fname.endswith('.png'): continue
        print("=======", fname, "=======")
        img_path = os.path.join(IN_DIR, fname)
        file = await StorageFile.get_file_from_path_async(img_path)
        stream = await file.open_async(0)
        decoder = await BitmapDecoder.create_async(stream)
        sw_bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(sw_bitmap)
        
        words_info = []
        for line in result.lines:
            for word in line.words:
                words_info.append((word.bounding_rect.y, word.bounding_rect.x, word.text))
        words_info.sort(key=lambda w: w[0])
        
        rows = []
        current_row = []
        last_y = -100
        for y, x, text in words_info:
            if abs(y - last_y) > 15 and current_row:
                current_row.sort(key=lambda w: w[1])
                rows.append(" ".join([w[2] for w in current_row]))
                current_row = []
            current_row.append((y, x, text))
            if len(current_row) == 1:
                last_y = y
        if current_row:
            current_row.sort(key=lambda w: w[1])
            rows.append(" ".join([w[2] for w in current_row]))
            
        for row in rows:
            k = row.lower()
            if 'iphone' in k or 'apple' in k or 'sim' in k or '未開封' in k or 'playstation' in k or 'switch' in k or 'instax' in k or 'コントローラー' in k or 'チェキ' in k or 'phone' in k or 'stax' in k:
                print("RAW ROW:", row)
                row_clean = re.sub(r'[^\w\s・/()\[\]】]', ' ', row).strip()
                print("  CLEAN:", row_clean)
                m = re.search(r'([\d\s]+)$', row_clean)
                if not m:
                    print("  No trailing digits")
                    continue
                name = row_clean[:m.start()].strip()
                digits = m.group(1).replace(' ', '')
                print(f"  NAME: '{name}' | DIGITS: '{digits}'")
                
                valid = False
                for lt in range(3, 8):
                    if lt > len(digits): break
                    total_str = digits[-lt:]
                    if not total_str.isdigit(): continue
                    total = int(total_str)
                    if total == 0: continue
                    
                    for lu in range(3, 8):
                        if lt + lu > len(digits): break
                        unit_str = digits[-(lt+lu):-lt]
                        if not unit_str.isdigit(): continue
                        unit = int(unit_str)
                        if unit == 0: continue
                        
                        rem = digits[:-(lt+lu)]
                        qty = int(rem) if rem.isdigit() and int(rem) > 0 else 0
                        
                        if qty > 0 and qty * unit == total:
                            print(f"    COMBINATION FOUND: {unit} x {qty} = {total}")
                            valid = True
                            break
                        elif qty == 0 and unit > 0 and total % unit == 0 and total // unit < 100:
                            qty = total // unit
                            print(f"    COMBINATION FOUND (IMPLIED QTY): {unit} x {qty} = {total}")
                            valid = True
                            break
                    if valid: break
                
                if not valid:
                    nums = re.findall(r'(\d{1,3}(?:[ ,]\d{3})*)', row)
                    print(f"    FALLBACK TRY: nums={nums}")
            
if __name__ == "__main__":
    asyncio.run(test_all())
