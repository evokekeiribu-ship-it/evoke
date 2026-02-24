import fitz
import sys

pdf_path = "株式会社ミナミトランスポートレーション御中2月21日納品分(ホムラ) 請求書.pdf"
doc = fitz.open(pdf_path)
for page_index in range(len(doc)):
    page = doc.load_page(page_index)
    image_list = page.get_images()
    for image_index, img in enumerate(image_list, start=1):
        xref = img[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        image_ext = base_image["ext"]
        with open(f"image_{page_index+1}_{image_index}.{image_ext}", "wb") as f:
            f.write(image_bytes)
        print(f"Saved image_{page_index+1}_{image_index}.{image_ext}")
