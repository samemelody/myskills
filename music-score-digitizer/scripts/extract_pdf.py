#!/usr/bin/env python3
"""
从 PDF 中抽取内嵌扫描图，并报告等效 DPI。

很多扫描类 App（扫描全能王等）导出的 PDF 里保存的是原始高清图，
而同时导出的 JPG 可能只有 96 DPI。直接处理 PDF 内嵌图通常能得到
2 倍以上线性分辨率。

用法:
    python scripts/extract_pdf.py <input.pdf> [--outdir temp/pdf_images]

只用标准库，不依赖 PyMuPDF / poppler。
"""

import argparse
import json
import re
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

A4_HEIGHT_IN = 842 / 72.0  # A4 高 297 mm，PDF 纸张单位 pt


def _int_value(dict_bytes, key):
    m = re.search(rb'/' + key + rb'\s+(\d+)', dict_bytes)
    return int(m.group(1)) if m else None


def _resolve_length(dict_bytes, objects):
    """解析 /Length，可能是直接数字，也可能是指向其他对象的引用。"""
    m = re.search(rb'/Length\s+(\d+)\s+(\d+)\s+R', dict_bytes)
    if m:
        num = int(m.group(1))
        body = objects.get(num)
        if body:
            mm = re.search(rb'^\s*(\d+)', body.strip())
            if mm:
                return int(mm.group(1))
    m = re.search(rb'/Length\s+(\d+)', dict_bytes)
    return int(m.group(1)) if m else None


def extract(pdf_path, outdir):
    data = Path(pdf_path).read_bytes()
    # 收集所有间接对象，用于解析间接 /Length
    objects = {}
    for m in re.finditer(rb'(\d+)\s+0\s+obj\b(.*?)\bendobj', data, re.S):
        objects[int(m.group(1))] = m.group(2)

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    images = []
    for num, body in objects.items():
        if b'/Subtype' not in body:
            continue
        if not re.search(rb'/Subtype\s*/Image', body):
            continue
        if b'DCTDecode' not in body:
            continue

        width = _int_value(body, rb'Width')
        height = _int_value(body, rb'Height')
        length = _resolve_length(body, objects)

        s = body.find(b'stream')
        if s < 0:
            continue
        s += len(b'stream')
        while body[s:s + 1] in (b'\r', b'\n'):
            s += 1
        if length:
            jpeg = body[s:s + length]
        else:
            e = body.find(b'endstream', s)
            jpeg = body[s:e]

        if not jpeg.startswith(b'\xff\xd8'):
            continue

        index = len(images) + 1
        path = outdir / f'pdf_image_{index:02d}.jpg'
        path.write_bytes(jpeg)

        dpi_h = round(height / A4_HEIGHT_IN, 1) if height else None
        is_page = bool(width and height and width >= 500 and height >= 500)
        images.append({
            'object': num,
            'file': str(path),
            'width': width,
            'height': height,
            'bytes': len(jpeg),
            'dpi_a4': dpi_h,
            'role': 'score' if is_page else 'asset',
        })

    return images


def main():
    ap = argparse.ArgumentParser(description='抽取 PDF 内嵌扫描图并报告 DPI')
    ap.add_argument('pdf', help='输入 PDF 路径')
    ap.add_argument('--outdir', default='temp/pdf_images', help='输出目录')
    ap.add_argument('--json', action='store_true', help='输出 JSON 清单')
    args = ap.parse_args()

    images = extract(args.pdf, args.outdir)

    if not images:
        print('未找到 DCTDecode 内嵌图。可能是纯文本 PDF 或使用了其他编码。')
        return 1

    if args.json:
        print(json.dumps(images, ensure_ascii=False, indent=2))
        return 0

    pages = [im for im in images if im['role'] == 'score']
    assets = [im for im in images if im['role'] == 'asset']
    print(f'共抽取 {len(images)} 张内嵌图，其中乐谱页 {len(pages)} 张 -> {args.outdir}')
    print(f'{"文件":<28}{"尺寸":<14}{"等效DPI":>9}{"大小":>10}  判定')
    for im in pages:
        size = f'{im["width"]}x{im["height"]}'
        dpi = im['dpi_a4'] or 0
        if dpi >= 300:
            verdict = '✅ 可直接 OMR'
        elif dpi >= 200:
            verdict = '⚠️  需几何校验'
        elif dpi >= 150:
            verdict = '⚠️  偏低，仅慢速段可用'
        else:
            verdict = '❌ 不可用，请重扫'
        print(f'{Path(im["file"]).name:<28}{size:<14}{dpi:>9}{im["bytes"]/1024:>8.0f}KB  {verdict}')
    if assets:
        names = ', '.join(Path(im['file']).name for im in assets)
        print(f'忽略 {len(assets)} 张小图（水印/图标）: {names}')

    print()
    print('提示: 等效 DPI 按 A4 纸高 297mm 估算；若原页不是 A4，数值会偏大/偏小。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
