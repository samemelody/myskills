#!/usr/bin/env python3
"""
图像预处理脚本
对扫描乐谱图片进行去噪、二值化、倾斜校正、手写笔迹过滤。
使用 OpenCV 实现。

用法:
    python preprocess.py                    # 处理 input/ 下所有图片
    python preprocess.py input/score1.png   # 处理指定图片
    python preprocess.py --dpi 300          # 指定 DPI
"""

import os
import sys
import glob

# Windows 中文环境 UTF-8 输出（避免 GBK 编码 emoji 失败）
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import argparse

try:
    import cv2
    import numpy as np
except ImportError:
    print("错误: 缺少 OpenCV 或 NumPy，请运行:")
    print("  pip install opencv-python numpy")
    sys.exit(1)


# ============ 可调参数 ============
BINARIZE_BLOCK_SIZE = 31   # 自适应二值化块大小（奇数）
BINARIZE_C = 5             # 二值化偏移常数（越大越严格）
MIN_CONTOUR_AREA = 30      # 噪声过滤最小面积（越大过滤越多手写笔迹）
DESKEW_THRESHOLD = 0.5     # 倾斜检测角度阈值（度）
MORPH_KERNEL_SIZE = 2      # 形态学操作核大小（谱线加固用）
TARGET_DPI = 300           # 目标 DPI（低于此值会缩放）


def load_image(path):
    """加载图片，返回灰度图。支持中文路径（OpenCV imread 对中文路径不稳定）"""
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法加载图片: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img, gray


def imwrite_utf8(path, img):
    """保存图片，支持中文路径"""
    ext = os.path.splitext(path)[1].lower() or ".png"
    # 映射常见扩展名到 OpenCV 编码格式
    ext_to_fmt = {
        ".png": (".png", cv2.IMWRITE_PNG_COMPRESSION, 3),
        ".jpg": (".jpg", cv2.IMWRITE_JPEG_QUALITY, 95),
        ".jpeg": (".jpeg", cv2.IMWRITE_JPEG_QUALITY, 95),
        ".bmp": (".bmp",),
        ".tif": (".tiff",),
        ".tiff": (".tiff",),
    }
    fmt = ext_to_fmt.get(ext, (".png",))
    success, buf = cv2.imencode(fmt[0], img, params=list(fmt[1:]) if len(fmt) > 1 else [])
    if not success:
        raise IOError(f"无法编码图片: {path}")
    buf.tofile(path)


def check_and_resize(gray, target_dpi=TARGET_DPI):
    """检查 DPI，过低则放大"""
    h, w = gray.shape
    # 假设原始 ~150 DPI，如果宽度 < 2000px 可能 DPI 不足
    if w < 2000:
        scale = 2000 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        print(f"    图片放大 {scale:.2f}x (原宽度 {w}px → {gray.shape[1]}px)")
    return gray


def deskew(gray):
    """使用霍夫变换检测五线谱倾斜并校正"""
    # 二值化用于检测直线
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 霍夫变换检测直线
    lines = cv2.HoughLinesP(
        binary,
        rho=1,
        theta=np.pi / 180,
        threshold=200,
        minLineLength=gray.shape[1] // 3,
        maxLineGap=20,
    )

    if lines is None:
        print("    未检测到明显倾斜，跳过校正")
        return gray

    # 计算所有检测到的直线角度
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # 只接受接近水平的线（五线谱）
        if abs(angle) < 15:
            angles.append(angle)

    if not angles:
        print("    未检测到水平直线，跳过校正")
        return gray

    median_angle = np.median(angles)

    if abs(median_angle) < DESKEW_THRESHOLD:
        print(f"    倾斜角度 {median_angle:.2f}° < 阈值 {DESKEW_THRESHOLD}°，跳过校正")
        return gray

    print(f"    检测到倾斜 {median_angle:.2f}°，正在校正...")

    # 旋转校正
    h, w = gray.shape
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(
        gray, rotation_matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

    return rotated


def adaptive_binarize(gray):
    """自适应二值化，去除扫描灰底"""
    # 高斯自适应二值化
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        BINARIZE_BLOCK_SIZE,
        BINARIZE_C,
    )
    return binary


def remove_handwriting(binary):
    """
    过滤手写笔迹和噪点。
    手写笔画通常比印刷谱线细，通过连通域面积和长宽比过滤。
    """
    # 反转（让前景为白色）
    inverted = cv2.bitwise_not(binary)

    # 形态学操作：水平方向闭合，加固五线谱横线
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    horizontal = cv2.morphologyEx(inverted, cv2.MORPH_CLOSE, horizontal_kernel)

    # 垂直方向闭合，加固音符干
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 20))
    vertical = cv2.morphologyEx(inverted, cv2.MORPH_CLOSE, vertical_kernel)

    # 合并水平+垂直方向加固的结果
    reinforced = cv2.bitwise_and(horizontal, vertical)

    # 连通域分析，过滤小面积噪点（含大部分手写笔迹）
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(reinforced, connectivity=8)

    filtered = np.zeros_like(reinforced)
    kept_count = 0
    removed_count = 0

    for i in range(1, num_labels):  # 跳过背景（0）
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= MIN_CONTOUR_AREA:
            filtered[labels == i] = 255
            kept_count += 1
        else:
            removed_count += 1

    print(f"    保留 {kept_count} 个连通域，过滤 {removed_count} 个小区域（含手写笔迹/噪点）")

    # 转回正常黑白
    result = cv2.bitwise_not(filtered)
    return result


def denoise(binary):
    """轻度去噪"""
    # 中值滤波去除孤立噪点
    denoised = cv2.medianBlur(binary, 3)
    return denoised


def process_image(input_path, output_path):
    """处理单张图片"""
    print(f"\n处理: {input_path}")

    # 1. 加载
    _, gray = load_image(input_path)
    print(f"    原始尺寸: {gray.shape[1]}x{gray.shape[0]}")

    # 2. 检查分辨率
    gray = check_and_resize(gray)

    # 3. 倾斜校正
    gray = deskew(gray)

    # 4. 自适应二值化
    binary = adaptive_binarize(gray)
    print("    自适应二值化完成")

    # 5. 过滤手写笔迹和噪点
    filtered = remove_handwriting(binary)

    # 6. 轻度去噪
    final = denoise(filtered)

    # 7. 保存
    imwrite_utf8(output_path, final)
    print(f"    保存到: {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="乐谱图像预处理")
    parser.add_argument("input", nargs="?", default=None, help="输入图片路径（默认处理 input/ 目录）")
    parser.add_argument("--dpi", type=int, default=TARGET_DPI, help=f"目标 DPI（默认 {TARGET_DPI}）")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_dir = os.path.join(base_dir, "input")
    temp_dir = os.path.join(base_dir, "temp")

    os.makedirs(temp_dir, exist_ok=True)

    # 确定输入文件
    if args.input:
        input_files = [args.input]
    else:
        extensions = ["*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff", "*.bmp"]
        input_files = []
        for ext in extensions:
            input_files.extend(glob.glob(os.path.join(input_dir, ext)))
        # 去重（Windows 不区分大小写，glob 可能大小写重复匹配）
        input_files = sorted(set(input_files), key=lambda x: x.lower())

    if not input_files:
        print(f"未找到输入图片。请将乐谱扫描图放入 {input_dir}/ 目录")
        sys.exit(1)

    input_files.sort()
    print(f"找到 {len(input_files)} 张图片待处理")

    processed = []
    for img_path in input_files:
        filename = os.path.splitext(os.path.basename(img_path))[0]
        output_path = os.path.join(temp_dir, f"{filename}_preprocessed.png")
        try:
            process_image(img_path, output_path)
            processed.append(output_path)
        except Exception as e:
            print(f"    ❌ 处理失败: {e}")

    print(f"\n预处理完成: {len(processed)}/{len(input_files)} 张图片成功")
    return 0 if len(processed) == len(input_files) else 1


if __name__ == "__main__":
    sys.exit(main())
