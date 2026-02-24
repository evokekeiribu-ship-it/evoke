import asyncio
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage import StorageFile

async def run_ocr_bboxes():
    engine = OcrEngine.try_create_from_user_profile_languages()
    img_path = r"C:\Users\Owner\OneDrive\デスクトップ\deveropment\請求書作成\請求書作成依頼\C2FF3D4A-807D-474E-96C2-A19BF2F3AF39.png"
    file = await StorageFile.get_file_from_path_async(img_path)
    stream = await file.open_async(0)
    decoder = await BitmapDecoder.create_async(stream)
    sw_bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(sw_bitmap)
    
    words_info = []
    for line in result.lines:
        for word in line.words:
            rect = word.bounding_rect
            # rect.y, rect.x, rect.width, rect.height
            words_info.append((rect.y, rect.x, word.text))
            
    # Y座標でのグルーピング（多少のブレを許容するため、Y座標が近いものは同じ行とする）
    words_info.sort(key=lambda w: w[0])
    
    rows = []
    current_row = []
    last_y = -100
    
    for y, x, text in words_info:
        if abs(y - last_y) > 10 and current_row:  # Y座標が10ピクセル以上違うなら次の行
            # X座標でソートして結合
            current_row.sort(key=lambda w: w[1])
            rows.append(" ".join([w[2] for w in current_row]))
            current_row = []
        current_row.append((y, x, text))
        if len(current_row) == 1:
            last_y = y
            
    if current_row:
        current_row.sort(key=lambda w: w[1])
        rows.append(" ".join([w[2] for w in current_row]))
        
    with open("ocr_bboxes.txt", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{r}\n")
            
if __name__ == "__main__":
    asyncio.run(run_ocr_bboxes())
