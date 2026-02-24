import asyncio
import os
import re
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage import StorageFile

IN_DIR = r"C:\Users\Owner\OneDrive\デスクトップ\deveropment\請求書作成\請求書作成依頼"

async def test_all2():
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
            if 'iphone' in k or 'apple' in k or 'sim' in k or '未開封' in k or 'playstation' in k or 'piaystation' in k or 'station' in k or 'switch' in k or 'instax' in k or 'コントローラー' in k or 'チェキ' in k or 'phone' in k or 'stax' in k:
                name_clean = row
                name_clean = re.sub(r'\bPhone\b', 'iPhone', name_clean, flags=re.I)
                name_clean = re.sub(r'(?<!SI)M FREE', 'SIM FREE', name_clean, flags=re.I)
                name_clean = re.sub(r'\bnstax\b', 'instax', name_clean, flags=re.I)
                name_clean = re.sub(r'\bPIayStation\b', 'PlayStation', name_clean, flags=re.I)
                name_clean = name_clean.replace('  ', ' ')
                
                row_clean = re.sub(r'\b\d{13}\b', '', name_clean)
                row_clean = re.sub(r'\s*,\s*', ',', row_clean)
                row_clean = re.sub(r'\s+([¥円])', r'\1', row_clean)
                
                prices_str = re.findall(r'\b\d{1,3}(?:,\d{3})+\b', row_clean)
                
                unit, qty, total = 0, 0, 0
                valid = False
                
                if len(prices_str) >= 2:
                    p1 = int(prices_str[0].replace(',', ''))
                    p2 = int(prices_str[-1].replace(',', ''))
                    if p1 > 1000 and p2 >= p1 and p2 % p1 == 0 and p2 // p1 < 100:
                        unit, total, qty = p1, p2, p2 // p1
                        valid = True
                        
                if not valid and len(prices_str) == 1:
                    p_str = prices_str[0]
                    parts = p_str.split(',')
                    if len(parts) >= 2:
                        unit = int(parts[0] + parts[1])
                        qty = 1
                        total = unit
                        valid = True
                        
                if not valid:
                    digits = re.sub(r'[^\d]', '', row_clean)
                    for lt in range(3, 8):
                        if lt > len(digits): break
                        total_str = digits[-lt:]
                        if not total_str.isdigit() or int(total_str) == 0: continue
                        tot = int(total_str)
                        
                        for lu in range(3, 8):
                            if lt + lu > len(digits): break
                            unit_str = digits[-(lt+lu):-lt]
                            if not unit_str.isdigit() or int(unit_str) == 0: continue
                            un = int(unit_str)
                            
                            rem = digits[:-(lt+lu)]
                            q = int(rem) if rem.isdigit() and int(rem) > 0 else 0
                            
                            if 0 < q < 100 and q * un == tot:
                                unit, qty, total = un, q, tot
                                valid = True
                                break
                            elif q == 0 and un > 0 and tot % un == 0 and tot // un < 100:
                                unit, qty, total = un, tot // un, tot
                                valid = True
                                break
                        if valid: break

                if unit == 0:
                    continue
                    
                name = re.sub(r'[\d\s,¥円]+$', '', name_clean).strip()
                name = re.sub(r'^(?:品番・品名|単価|小計|金額|数量)+', '', name).strip()
                
                if 'iphone' in name.lower() or unit >= 20000:
                    unit -= 100
                else:
                    unit -= 20
                total = unit * qty
                
                print(f"FOUND: '{name}' | {unit} x {qty} = {total}")

if __name__ == "__main__":
    asyncio.run(test_all2())
