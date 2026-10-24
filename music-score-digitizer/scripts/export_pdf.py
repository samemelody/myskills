#!/usr/bin/env python3
"""
PDF 导出脚本
将人工校正后的 MusicXML 文件导出为矢量 PDF。
优先使用 LilyPond（排版质量最高），失败则回退到 MuseScore 命令行。

用法:
    python export_pdf.py                           # 导出 temp/ 下所有 MusicXML
    python export_pdf.py temp/score.musicxml       # 导出指定文件
    python export_pdf.py --engine lilypond          # 指定导出引擎
    python export_pdf.py --engine musescore         # 指定导出引擎
"""

import os
import sys
import glob
import shutil
import subprocess
import argparse
import platform
import tempfile

# Windows 中文环境 UTF-8 输出（避免 GBK 编码 emoji 失败）
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def find_executable(names, windows_paths=None):
    """查找可执行文件"""
    for name in names:
        path = shutil.which(name)
        if path:
            return path

    if platform.system() == "Windows" and windows_paths:
        for wp in windows_paths:
            if os.path.isfile(wp):
                return wp

    return None


def find_lilypond():
    return find_executable(
        ["lilypond", "lilypond-windows"],
        [
            r"C:\Program Files\LilyPond\usr\bin\lilypond-windows.exe",
            r"C:\Program Files (x86)\LilyPond\usr\bin\lilypond-windows.exe",
        ],
    )


def find_musescore():
    return find_executable(
        ["musescore", "MuseScore", "mscore"],
        [
            r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
            r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\MuseScore\bin\MuseScore4.exe"),
        ],
    )


def find_musicxml2ly():
    """查找 LilyPond 附带的 musicxml2ly 工具"""
    lilypond = find_lilypond()
    if not lilypond:
        return None

    lilypond_dir = os.path.dirname(lilypond)
    candidates = [
        os.path.join(lilypond_dir, "musicxml2ly"),
        os.path.join(lilypond_dir, "musicxml2ly.py"),
        os.path.join(os.path.dirname(lilypond_dir), "musicxml2ly"),
        os.path.join(os.path.dirname(lilypond_dir), "musicxml2ly.py"),
    ]

    for c in candidates:
        if os.path.isfile(c):
            return c

    return None


def export_with_lilypond(musicxml_path, output_pdf, lilypond_path=None):
    """
    使用 LilyPond 导出 PDF（排版质量最高）。
    流程: MusicXML → musicxml2ly → .ly → lilypond → .pdf
    """
    if not lilypond_path:
        lilypond_path = find_lilypond()

    if not lilypond_path:
        print("    LilyPond 未安装，尝试回退到 MuseScore")
        return export_with_musescore(musicxml_path, output_pdf)

    musicxml2ly = find_musicxml2ly()

    with tempfile.TemporaryDirectory() as tmp_dir:
        if musicxml2ly:
            # 方式1: 通过 musicxml2ly 转换（质量最好）
            ly_path = os.path.join(tmp_dir, "temp.ly")
            print(f"    [LilyPond] musicxml2ly 转换中...")

            cmd = [
                sys.executable if musicxml2ly.endswith(".py") else musicxml2ly,
                "--output", ly_path,
                musicxml_path,
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0 or not os.path.isfile(ly_path):
                    print(f"    ⚠️ musicxml2ly 转换失败: {result.stderr[:200]}")
                    print(f"    尝试直接用 LilyPond 处理 MusicXML...")
                    ly_path = musicxml_path  # LilyPond 也能直接处理部分 MusicXML
            except Exception as e:
                print(f"    ⚠️ musicxml2ly 异常: {e}")
                ly_path = musicxml_path
        else:
            print(f"    [LilyPond] 未找到 musicxml2ly，尝试直接处理...")
            ly_path = musicxml_path

        # 调用 LilyPond 生成 PDF
        print(f"    [LilyPond] 生成 PDF 中...")
        cmd = [
            lilypond_path,
            "--output", os.path.splitext(output_pdf)[0],
            "--pdf",
            "-dno-point-and-click",  # 禁用交互模式
            ly_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                    cwd=tmp_dir)

            # LilyPond 可能输出到 tmp_dir
            generated_pdf = os.path.join(tmp_dir, "temp.pdf")
            if not os.path.isfile(generated_pdf):
                # 也检查 output 目录
                base = os.path.splitext(os.path.basename(ly_path))[0]
                generated_pdf = os.path.join(tmp_dir, f"{base}.pdf")

            if os.path.isfile(generated_pdf):
                shutil.copy2(generated_pdf, output_pdf)
                print(f"    ✅ LilyPond 导出成功: {output_pdf}")
                return True
            else:
                print(f"    ❌ LilyPond 未生成 PDF")
                if result.stderr:
                    print(f"       {result.stderr[:300]}")
                return False

        except subprocess.TimeoutExpired:
            print(f"    ❌ LilyPond 超时")
            return False
        except Exception as e:
            print(f"    ❌ LilyPond 异常: {e}")
            return False


def export_with_musescore(musicxml_path, output_pdf, musescore_path=None):
    """
    使用 MuseScore 命令行导出 PDF。
    MuseScore 4: MuseScore4.exe -o output.pdf input.musicxml
    MuseScore 3: mscore -o output.pdf input.musicxml
    """
    if not musescore_path:
        musescore_path = find_musescore()

    if not musescore_path:
        print("    ❌ MuseScore 也未安装，无法导出 PDF")
        return False

    print(f"    [MuseScore] 导出 PDF 中...")
    print(f"    MuseScore 路径: {musescore_path}")

    cmd = [musescore_path, "-o", output_pdf, musicxml_path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if os.path.isfile(output_pdf):
            print(f"    ✅ MuseScore 导出成功: {output_pdf}")
            return True
        else:
            print(f"    ❌ MuseScore 未生成 PDF (返回码: {result.returncode})")
            if result.stderr:
                print(f"       {result.stderr[:300]}")
            # MuseScore 4 可能需要不同的参数格式
            print(f"    尝试备用参数格式...")
            cmd2 = [musescore_path, "--export-to", output_pdf, musicxml_path]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=120)
            if os.path.isfile(output_pdf):
                print(f"    ✅ MuseScore 导出成功（备用参数）: {output_pdf}")
                return True
            return False

    except subprocess.TimeoutExpired:
        print(f"    ❌ MuseScore 超时")
        return False
    except Exception as e:
        print(f"    ❌ MuseScore 异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="导出矢量 PDF")
    parser.add_argument("input", nargs="?", default=None, help="输入 MusicXML 文件路径")
    parser.add_argument("--engine", choices=["lilypond", "musescore", "auto"], default="auto",
                        help="导出引擎（默认 auto: 优先 LilyPond，回退 MuseScore）")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    temp_dir = os.path.join(base_dir, "temp")
    output_dir = os.path.join(base_dir, "output")

    os.makedirs(output_dir, exist_ok=True)

    # 确定输入文件
    if args.input:
        input_files = [args.input]
    else:
        input_files = sorted(
            glob.glob(os.path.join(temp_dir, "*.musicxml")) +
            glob.glob(os.path.join(temp_dir, "*.xml"))
        )

    if not input_files:
        print(f"未找到 MusicXML 文件。")
        print(f"请先运行 run_omr.py 生成 MusicXML，并在 MuseScore 中校正后保存。")
        sys.exit(1)

    print(f"找到 {len(input_files)} 个 MusicXML 文件待导出")

    success_count = 0
    for mxl_path in input_files:
        base_name = os.path.splitext(os.path.basename(mxl_path))[0]
        output_pdf = os.path.join(output_dir, f"{base_name}.pdf")
        print(f"\n导出: {mxl_path}")

        if args.engine == "lilypond":
            ok = export_with_lilypond(mxl_path, output_pdf)
        elif args.engine == "musescore":
            ok = export_with_musescore(mxl_path, output_pdf)
        else:
            # auto: 优先 lilypond，回退 musescore
            ok = export_with_lilypond(mxl_path, output_pdf)
            if not ok:
                print(f"    回退到 MuseScore...")
                ok = export_with_musescore(mxl_path, output_pdf)

        if ok:
            success_count += 1

    print(f"\nPDF 导出完成: {success_count}/{len(input_files)} 个成功")
    print(f"输出目录: {output_dir}")
    return 0 if success_count == len(input_files) else 1


if __name__ == "__main__":
    sys.exit(main())
