#!/usr/bin/env python3
"""
OMR 识别脚本
调用 Audiveris 将预处理后的乐谱图片识别为 MusicXML。

用法:
    python run_omr.py                        # 处理 temp/ 下所有预处理图片
    python run_omr.py temp/score1_preprocessed.png  # 处理指定图片
"""

import os
import sys
import glob
import shutil
import subprocess
import argparse
import platform

# Windows 中文环境 UTF-8 输出（避免 GBK 编码 emoji 失败）
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def find_audiveris():
    """查找 Audiveris 可执行文件"""
    # 1. 查 PATH
    for name in ["audiveris", "Audiveris"]:
        path = shutil.which(name)
        if path:
            return path

    # 2. 查 Windows 常见路径
    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\Audiveris\bin\Audiveris.exe",
            r"C:\Program Files (x86)\Audiveris\bin\Audiveris.exe",
            os.path.expanduser(r"~\Audiveris\bin\Audiveris.exe"),
            os.path.expanduser(r"~\AppData\Local\Audiveris\bin\Audiveris.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

    # 3. 环境变量
    env_path = os.environ.get("AUDIVERIS_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    return None


def run_audiveris(input_image, output_dir, audiveris_path=None):
    """
    调用 Audiveris 批处理模式识别乐谱。
    Audiveris 命令行用法:
      Audiveris -batch -export -output <output_dir> <input_image>
    """
    if not audiveris_path:
        audiveris_path = find_audiveris()

    if not audiveris_path:
        print("错误: 未找到 Audiveris，请安装后确保在 PATH 中")
        print("下载: https://github.com/Audiveris/audiveris/releases")
        print("或设置环境变量 AUDIVERIS_PATH 指向 Audiveris.exe")
        return None

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        audiveris_path,
        "-batch",
        "-export",
        "-output", output_dir,
        input_image,
    ]

    print(f"  Audiveris 路径: {audiveris_path}")
    print(f"  输入: {input_image}")
    print(f"  输出目录: {output_dir}")
    print(f"  命令: {' '.join(cmd)}")
    print(f"  正在识别（可能需要 10-60 秒）...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,  # 5分钟超时
        )
        stdout_text = result.stdout.decode('utf-8', errors='replace') if result.stdout else ""
        stderr_text = result.stderr.decode('utf-8', errors='replace') if result.stderr else ""

        if result.returncode != 0:
            print(f"  ⚠️ Audiveris 返回码: {result.returncode}")
            if stderr_text:
                stderr_lines = stderr_text.strip().split("\n")
                for line in stderr_lines[-8:]:
                    print(f"     {line}")

        # 查找生成的 MusicXML 文件
        # Audiveris 输出 .mxl（压缩 MusicXML）和 .omr（项目文件）
        # 多声部会输出 xxx.mvt1.mxl, xxx.mvt2.mxl 等
        base_name = os.path.splitext(os.path.basename(input_image))[0]
        mxl_files = sorted(glob.glob(os.path.join(output_dir, f"{base_name}*.mxl")))
        # 兜底：搜索目录下所有 .mxl
        if not mxl_files:
            mxl_files = sorted(glob.glob(os.path.join(output_dir, "**", "*.mxl"), recursive=True))
        # 也搜索 .musicxml / .xml（非压缩格式）
        musicxml_files = sorted(
            glob.glob(os.path.join(output_dir, f"{base_name}*.musicxml")) +
            glob.glob(os.path.join(output_dir, f"{base_name}*.xml"))
        )

        all_outputs = mxl_files + musicxml_files

        if all_outputs:
            print(f"  ✅ 识别完成，生成 {len(all_outputs)} 个 MusicXML 文件:")
            for f in all_outputs:
                size_kb = os.path.getsize(f) / 1024
                print(f"     {os.path.basename(f)} ({size_kb:.1f} KB)")
            return all_outputs[0]
        else:
            print(f"  ❌ 未找到输出的 MusicXML/.mxl 文件")
            print(f"     输出目录: {output_dir}")
            if stdout_text:
                stdout_lines = stdout_text.strip().split("\n")
                for line in stdout_lines[-8:]:
                    print(f"     {line}")
            return None

    except subprocess.TimeoutExpired:
        print(f"  ❌ Audiveris 超时（5分钟），可能图片过大或过于复杂")
        return None
    except FileNotFoundError:
        print(f"  ❌ 无法执行 Audiveris: {audiveris_path}")
        return None
    except Exception as e:
        print(f"  ❌ 执行异常: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Audiveris OMR 识别")
    parser.add_argument("input", nargs="?", default=None, help="输入预处理图片路径")
    parser.add_argument("--audiveris", default=None, help="Audiveris 可执行文件路径")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    temp_dir = os.path.join(base_dir, "temp")

    if not os.path.isdir(temp_dir):
        print(f"temp/ 目录不存在，请先运行 preprocess.py")
        sys.exit(1)

    # 确定输入文件
    if args.input:
        input_files = [args.input]
    else:
        input_files = sorted(glob.glob(os.path.join(temp_dir, "*_preprocessed.png")))
        if not input_files:
            # 也尝试 temp 下的其他图片
            for ext in ["*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff"]:
                input_files.extend(glob.glob(os.path.join(temp_dir, ext)))

    if not input_files:
        print(f"未找到待识别图片。请先运行 preprocess.py 生成预处理图片")
        sys.exit(1)

    input_files.sort()
    print(f"找到 {len(input_files)} 张图片待识别")

    success_count = 0
    for img_path in input_files:
        print(f"\n识别: {img_path}")
        result = run_audiveris(img_path, temp_dir, args.audiveris)
        if result:
            success_count += 1

    print(f"\nOMR 识别完成: {success_count}/{len(input_files)} 张成功")
    print(f"\n下一步: 请用 MuseScore 打开 temp/ 目录下的 .musicxml 文件进行人工校正")
    return 0 if success_count == len(input_files) else 1


if __name__ == "__main__":
    sys.exit(main())
