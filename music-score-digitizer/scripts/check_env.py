#!/usr/bin/env python3
"""
环境依赖检查脚本
检测 OMR 工作流所需的所有工具是否已安装并可用。
"""

import shutil
import subprocess
import sys
import os
import platform

# Windows 中文环境 UTF-8 输出（避免 GBK 编码 emoji 失败）
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ============ 工具定义 ============
# 每个工具: (显示名称, 可执行文件名列表, 验证命令, 版本解析函数)

TOOLS = [
    {
        "name": "Python",
        "executables": ["python", "python3", sys.executable],
        "check_args": ["--version"],
        "required": True,
    },
    {
        "name": "OpenCV (Python)",
        "executables": None,  # 特殊处理：检查 Python 包
        "check_args": None,
        "required": False,  # 仅做图像预处理时需要；像素分析可用 PowerShell 完成
        "pip_package": "opencv-python",
        "import_name": "cv2",  # pip 包名与 import 名不同
    },
    {
        "name": "NumPy (Python)",
        "executables": None,
        "check_args": None,
        "required": False,
        "pip_package": "numpy",
    },
    {
        "name": "PowerShell",
        "executables": ["powershell", "pwsh"],
        "check_args": ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
        "required": True,  # 像素测量/系统裁切依赖 System.Drawing
    },
    {
        "name": "Audiveris",
        "executables": ["audiveris", "Audiveris"],
        "check_args": ["-version"],
        "required": False,  # 可选；高复杂度谱面可用 AI 辅助 + 几何校验替代
        "windows_paths": [
            r"C:\Program Files\Audiveris\bin\Audiveris.exe",
            r"C:\Program Files (x86)\Audiveris\bin\Audiveris.exe",
            os.path.expanduser(r"~\Audiveris\bin\Audiveris.exe"),
        ],
    },
    {
        "name": "MuseScore",
        "executables": ["musescore", "MuseScore", "mscore"],
        "check_args": ["--version"],
        "required": True,
        "windows_paths": [
            r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
            r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\MuseScore\bin\MuseScore4.exe"),
        ],
    },
    {
        "name": "LilyPond",
        "executables": ["lilypond", "lilypond-windows"],
        "check_args": ["--version"],
        "required": False,  # 可选，可用 MuseScore 替代
        "windows_paths": [
            r"C:\Program Files\LilyPond\usr\bin\lilypond-windows.exe",
            r"C:\Program Files (x86)\LilyPond\usr\bin\lilypond-windows.exe",
        ],
    },
    {
        "name": "ImageMagick",
        "executables": ["magick"],  # 只用 magick（ImageMagick 7），避免误中 Windows 自带 convert.exe
        "check_args": ["--version"],
        "required": False,  # 可选，OpenCV 可替代
        "windows_paths": [],
        "version_keyword": "ImageMagick",  # 版本输出必须包含此关键词，否则视为误报
    },
]


def find_executable(name, windows_paths=None):
    """查找可执行文件，先查 PATH，再查 Windows 常见路径"""
    path = shutil.which(name)
    if path:
        return path

    if platform.system() == "Windows" and windows_paths:
        for wp in windows_paths:
            if os.path.isfile(wp):
                return wp

    return None


def check_python_package(tool):
    """检查 Python 包是否已安装。支持 import_name 覆盖（如 opencv-python 的 import 名是 cv2）"""
    import_name = tool.get("import_name")
    if not import_name:
        import_name = tool["pip_package"].replace("-", "_").split(".")[0]
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False


def get_version(executable, args, version_keyword=None):
    """运行命令获取版本信息。可指定 version_keyword 验证非误报。"""
    try:
        result = subprocess.run(
            [executable] + args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15,
            shell=False,
        )
        output = (result.stdout + result.stderr).strip()
        # 版本关键词校验（防止 Windows convert.exe 等同名工具误报）
        if version_keyword and version_keyword.lower() not in output.lower():
            return None
        # 取第一行
        first_line = output.split("\n")[0] if output else "unknown"
        return first_line
    except Exception:
        return None


def main():
    print("=" * 60)
    print("  OMR 乐谱数字化工作流 — 环境检查")
    print("=" * 60)
    print()

    all_required_ok = True
    optional_ok = 0
    optional_total = 0

    for tool in TOOLS:
        name = tool["name"]
        required = tool["required"]

        # Python 包检查
        if tool.get("pip_package"):
            installed = check_python_package(tool)
            status = "✅ 已安装" if installed else "❌ 未安装"
            print(f"  {status}  {name}")
            if not installed and required:
                print(f"           安装: pip install {tool['pip_package']}")
                all_required_ok = False
            print()
            continue

        # 可执行文件检查
        exe_path = None
        for exe_name in tool["executables"]:
            exe_path = find_executable(exe_name, tool.get("windows_paths"))
            if exe_path:
                break

        if not required:
            optional_total += 1

        if exe_path:
            version = get_version(exe_path, tool["check_args"], tool.get("version_keyword"))
            # 版本为 None 说明命中了同名工具（如 Windows convert.exe），视为未安装
            if version is None and tool.get("version_keyword"):
                status = "⚠️  (可选，未安装)"
                print(f"  {status}  {name}")
                print(f"           命中的可执行文件未通过版本验证，视为未安装")
            else:
                status = "✅" if required else "✅ (可选)"
                print(f"  {status}  {name}")
                print(f"           路径: {exe_path}")
                if version:
                    print(f"           版本: {version}")
                if not required:
                    optional_ok += 1
        else:
            status = "❌" if required else "⚠️  (可选，未安装)"
            print(f"  {status}  {name}")
            if not required:
                print(f"           未安装不影响核心流程，但有更好")
            else:
                print(f"           请参考 references/tool_setup.md 安装")
                all_required_ok = False

        print()

    # 总结
    print("=" * 60)
    if all_required_ok:
        print("  ✅ 所有必要工具已就绪，可以开始工作流！")
    else:
        print("  ❌ 部分必要工具缺失，请先安装后再运行工作流。")

    if optional_total > 0:
        print(f"  ℹ️  可选工具: {optional_ok}/{optional_total} 已安装")

    print("=" * 60)

    # 检查工作目录
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print()
    print("工作目录检查:")
    for subdir in ["input", "output", "temp"]:
        dir_path = os.path.join(base_dir, subdir)
        exists = os.path.isdir(dir_path)
        file_count = len(os.listdir(dir_path)) if exists else 0
        status = "✅" if exists else "❌"
        print(f"  {status}  {subdir}/  ({file_count} 个文件)")

    return 0 if all_required_ok else 1


if __name__ == "__main__":
    sys.exit(main())
