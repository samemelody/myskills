#!/usr/bin/env python3
"""
简单放大脚本：将 input/ 中的图片放大到 300 DPI 等效分辨率。
A4 @ 96 DPI = 793x1123 px
A4 @ 300 DPI = 2480x3508 px
放大倍数约 3.125x
"""

import os
import sys
import glob
from PIL import Image

# Windows UTF-8 输出
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "input")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

# 目标：A4 @ 300 DPI
TARGET_WIDTH = 2480
TARGET_HEIGHT = 3508

os.makedirs(TEMP_DIR, exist_ok=True)


def upscale_image(input_path, output_path):
    """放大图片到 300 DPI 等效，用 Lanczos 保持谱线清晰"""
    img = Image.open(input_path)
    w, h = img.size
    print(f"  Original: {w}x{h}")

    # 按宽度比例放大，保持纵横比
    if w >= TARGET_WIDTH:
        print(f"  Already >= {TARGET_WIDTH}px wide, copy as-is")
        img.save(output_path, "PNG")
        return

    scale = TARGET_WIDTH / w
    new_w = TARGET_WIDTH
    new_h = int(h * scale)
    print(f"  Upscaling {scale:.2f}x -> {new_w}x{new_h}")

    # 先用 BICUBIC 放大，再用 sharpen 轻微锐化谱线
    img_resized = img.resize((new_w, new_h), Image.BICUBIC)

    # 轻度锐化
    from PIL import ImageFilter
    img_sharp = img_resized.filter(ImageFilter.SHARPEN)

    # 转灰度
    if img_sharp.mode != "L":
        img_sharp = img_sharp.convert("L")

    img_sharp.save(output_path, "PNG")
    print(f"  Saved: {output_path}")


def main():
    input_files = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff"]:
        input_files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
        input_files.extend(glob.glob(os.path.join(INPUT_DIR, ext.upper())))

    input_files = sorted(set(input_files))

    if not input_files:
        print(f"No images found in {INPUT_DIR}")
        sys.exit(1)

    print(f"Found {len(input_files)} images to upscale")
    print(f"Target: {TARGET_WIDTH}x{TARGET_HEIGHT} (A4 @ 300 DPI)")
    print()

    for img_path in input_files:
        filename = os.path.splitext(os.path.basename(img_path))[0]
        output_path = os.path.join(TEMP_DIR, f"{filename}_300dpi.png")
        print(f"Processing: {os.path.basename(img_path)}")
        try:
            upscale_image(img_path, output_path)
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    print("Done! Upscaled images are in temp/ directory.")
    print("Next: run run_audiveris.bat to do OMR recognition.")


if __name__ == "__main__":
    main()
