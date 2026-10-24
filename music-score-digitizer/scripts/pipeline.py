#!/usr/bin/env python3
"""
全流程编排脚本 — OMR 乐谱数字化主入口
依次执行: 预处理 → OMR识别 → [人工校正暂停] → PDF导出

用法:
    python pipeline.py                  # 完整流程
    python pipeline.py --skip-preprocess  # 跳过预处理
    python pipeline.py --skip-omr         # 跳过OMR识别
    python pipeline.py --skip-correction  # 跳过人工校正等待
    python pipeline.py --skip-export      # 跳过PDF导出
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path

# Windows 中文环境 UTF-8 输出（避免 GBK 编码 emoji 失败）
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# 工作目录
BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"

PYTHON = sys.executable


def print_banner():
    print()
    print("=" * 60)
    print("  ♪♪♪  OMR 乐谱数字化工作流  ♪♪♪")
    print("  扫描图片 → 预处理 → OMR识别 → 人工校正 → 矢量PDF")
    print("=" * 60)
    print()


def print_step(step_num, title):
    print()
    print(f"{'─' * 60}")
    print(f"  步骤 {step_num}: {title}")
    print(f"{'─' * 60}")


def run_script(script_name, description):
    """运行子脚本"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"  ❌ 脚本不存在: {script_path}")
        return False

    print(f"  执行: python {script_name}")
    print()

    result = subprocess.run(
        [PYTHON, str(script_path)],
        cwd=str(BASE_DIR),
    )

    success = result.returncode == 0
    status = "✅" if success else "⚠️"
    print(f"\n  {status} {description}: {'成功' if success else '部分失败'}")
    return success


def wait_for_user(prompt):
    """等待用户确认"""
    print()
    print(f"  {'!' * 56}")
    print(f"  {prompt}")
    print(f"  {'!' * 56}")
    print()
    input("  >>> 完成后按回车继续...")
    print()


def count_files(directory, pattern):
    """统计目录下匹配模式的文件数"""
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def main():
    parser = argparse.ArgumentParser(description="OMR 乐谱数字化全流程")
    parser.add_argument("--skip-preprocess", action="store_true", help="跳过图像预处理")
    parser.add_argument("--skip-omr", action="store_true", help="跳过 OMR 识别")
    parser.add_argument("--skip-correction", action="store_true", help="跳过人工校正等待")
    parser.add_argument("--skip-export", action="store_true", help="跳过 PDF 导出")
    parser.add_argument("--engine", choices=["lilypond", "musescore", "auto"], default="auto",
                        help="PDF 导出引擎")
    args = parser.parse_args()

    print_banner()

    # 确保目录存在
    for d in [INPUT_DIR, OUTPUT_DIR, TEMP_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # 检查输入
    if not args.skip_preprocess:
        input_count = count_files(INPUT_DIR, "*.[pPjJtTbB]*")  # png/jpg/tiff/bmp
        if input_count == 0:
            print(f"❌ input/ 目录中没有图片文件")
            print(f"   请将扫描的乐谱图片放入: {INPUT_DIR}")
            sys.exit(1)
        print(f"📁 输入目录: {INPUT_DIR} ({input_count} 张图片)")
    else:
        print(f"⏭️  跳过预处理")

    # ========== 步骤1: 环境检查 ==========
    if not args.skip_preprocess or not args.skip_omr:
        print_step(0, "环境检查")
        run_script("check_env.py", "环境检查")

    # ========== 步骤1: 图像预处理 ==========
    if not args.skip_preprocess:
        print_step(1, "图像预处理 (OpenCV)")
        print("  对每张图片执行: 去噪 → 二值化 → 倾斜校正 → 手写笔迹过滤")
        ok = run_script("preprocess.py", "图像预处理")

        if not ok:
            print("\n⚠️ 预处理部分失败，继续尝试处理成功的图片")

        preprocessed_count = count_files(TEMP_DIR, "*_preprocessed.png")
        if preprocessed_count == 0:
            print("\n❌ 预处理未生成任何输出图片，无法继续")
            sys.exit(1)
        print(f"\n  预处理输出: {preprocessed_count} 张图片在 {TEMP_DIR}")

    # ========== 步骤2: OMR 识别 ==========
    if not args.skip_omr:
        print_step(2, "OMR 识别 (Audiveris)")
        print("  调用 Audiveris 将图片识别为 MusicXML")
        print("  此步骤可能需要较长时间，请耐心等待...")
        ok = run_script("run_omr.py", "OMR 识别")

        musicxml_count = count_files(TEMP_DIR, "*.musicxml") + count_files(TEMP_DIR, "*.xml")
        if musicxml_count == 0:
            print("\n❌ OMR 识别未生成任何 MusicXML 文件")
            print("   可能原因:")
            print("   1. Audiveris 未安装或不在 PATH 中")
            print("   2. 图片质量不足，尝试调整预处理参数")
            print("   3. 图片 DPI 过低（需要 ≥ 300）")
            sys.exit(1)
        print(f"\n  OMR 输出: {musicxml_count} 个 MusicXML 文件在 {TEMP_DIR}")

    # ========== 步骤3: 人工校正 ==========
    if not args.skip_correction:
        print_step(3, "人工校正 (MuseScore)")

        musicxml_files = list(TEMP_DIR.glob("*.musicxml")) + list(TEMP_DIR.glob("*.xml"))

        print("  请按以下步骤操作:")
        print()
        for i, f in enumerate(musicxml_files, 1):
            print(f"  {i}. 用 MuseScore 打开: {f}")
        print()
        print("  在 MuseScore 中:")
        print("    - 检查音高、节奏、调号是否正确")
        print("    - 修正遗漏或多余的音符")
        print("    - 检查力度记号、演奏记号")
        print("    - 保存修改 (Ctrl+S)")
        print()
        print("  提示: OMR 识别准确率通常 70-90%，人工校正是保证质量的关键步骤")

        wait_for_user("请在 MuseScore 中完成所有 MusicXML 文件的校正并保存")

    # ========== 步骤4: PDF 导出 ==========
    if not args.skip_export:
        print_step(4, "PDF 导出 (LilyPond/MuseScore)")
        engine_desc = {
            "lilypond": "LilyPond（出版级排版质量）",
            "musescore": "MuseScore（稳定兼容）",
            "auto": "自动选择（优先 LilyPond，回退 MuseScore）",
        }
        print(f"  导出引擎: {engine_desc[args.engine]}")

        export_script = SCRIPTS_DIR / "export_pdf.py"
        cmd = [PYTHON, str(export_script)]
        if args.engine != "auto":
            cmd.extend(["--engine", args.engine])

        result = subprocess.run(cmd, cwd=str(BASE_DIR))
        success = result.returncode == 0

        pdf_count = count_files(OUTPUT_DIR, "*.pdf")
        if pdf_count > 0:
            print(f"\n  ✅ 导出完成: {pdf_count} 个 PDF 文件在 {OUTPUT_DIR}")
        else:
            print(f"\n  ❌ PDF 导出失败")

    # ========== 完成 ==========
    print()
    print("=" * 60)
    print("  ♪♪♪  工作流完成  ♪♪♪")
    print("=" * 60)
    print()
    print(f"  输入: {INPUT_DIR}")
    print(f"  中间产物: {TEMP_DIR}")
    print(f"  最终输出: {OUTPUT_DIR}")
    print()

    pdf_files = list(OUTPUT_DIR.glob("*.pdf"))
    if pdf_files:
        print("  生成的 PDF 文件:")
        for f in pdf_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"    📄 {f.name} ({size_mb:.2f} MB)")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
