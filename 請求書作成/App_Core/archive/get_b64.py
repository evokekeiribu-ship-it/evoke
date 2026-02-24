import base64
with open("image_1_1.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode('utf-8')
    print(f"data:image/png;base64,{b64[:30]}... (total length {len(b64)})")
    with open("seal_b64.txt", "w") as out:
        out.write(f"data:image/png;base64,{b64}")
