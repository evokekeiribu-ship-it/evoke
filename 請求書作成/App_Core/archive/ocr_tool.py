import asyncio
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage import StorageFile

async def run_ocr(image_path):
    try:
        file = await StorageFile.get_file_from_path_async(image_path)
        stream = await file.open_async(0)
        decoder = await BitmapDecoder.create_async(stream)
        software_bitmap = await decoder.get_software_bitmap_async()
        
        engine = OcrEngine.try_create_from_user_profile_languages()
        result = await engine.recognize_async(software_bitmap)
        with open("ocr_result.txt", "w", encoding="utf-8") as f:
            f.write(result.text)
        print("OCR complete.")
    except Exception as e:
        print(f"OCR failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_ocr(r"C:\Users\Owner\OneDrive\デスクトップ\deveropment\請求書作成\src_img.png"))
