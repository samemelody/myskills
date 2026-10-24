---
name: music-score-digitizer
description: >
  乐谱数字化工作流 Skill：将扫描/拍照的乐谱转换为 MusicXML、矢量 PDF 和参考音频。
  提供两条路径：高分辨率扫描件的 AI 辅助转谱（像素几何校验），以及
  传统 Audiveris OMR 流水线。当用户需要"数字化乐谱"、"识别五线谱"、
  "乐谱转PDF"、"OMR识别"、"扫描乐谱转电子版"、"校对手工转谱"时触发。
  也适用于 "sheet music recognition"、"convert score to PDF"、"music score digitization"。
agent_created: true
---

# Music Score Digitizer v2 — 扫描乐谱数字化

## 0. 先审计源文件，再决定路径（最重要的一步）

**输入质量决定上限，模型和算法只能逼近这个上限。** 同一份谱，96 DPI 导出图会让
任何 OMR 失败；PDF 里 219 DPI 的原始内嵌图则足以逐音转谱。

| 源文件 | 处理方式 |
|---|---|
| 扫描类 App 导出的 PDF（扫描全能王等） | **先抽内嵌原图**：`python scripts/extract_pdf.py <pdf>`；不要直接用同时导出的 JPG |
| JPG / PNG / TIFF | 直接做分辨率审计 |
| 出版方原始 PDF（矢量） | 优先；可无损转 MusicXML |
| 已有手工 `.mscz` / `.musicxml` 底稿 | 进入"校验模式"，用 `diff_scores.py` 对照，而不是从零转谱 |

### 质量闸门

用 `scripts/staff_spacing.ps1` 测五线线距（比折算 DPI 更可靠）：

| 线距 | 判定 | 处理 |
|---|---|---|
| ≥ 16 px | ✅ 可靠 | 可全自动/半自动转谱 |
| 8–15 px | ⚠️ 边缘 | 每个和弦必须做像素几何校验；密集段预期准确率下降 |
| < 8 px | ❌ 不可用 | 停止，要求 300–600 DPI 重扫或提供 PDF 原图 |

等效 DPI 参考：A4 页面高度像素数 ÷ 11.69。≥300 理想；200–300 可配合几何校验；
<150 基本不可用。**不要用插值放大伪造分辨率**——它不增加信息。

## 1. 两条工作流

### 模式 A：AI 辅助转谱（推荐，适合复杂/手写标注乐谱）

```
源文件 → [审计分辨率] → [按谱表系统裁切] → [逐系统读谱 + 像素校验]
       → [生成 MusicXML] → [MuseScore 渲染 PDF/MP3] → [与原图/底稿逐小节校对]
```

关键原则：

1. **逐系统处理**：不要一次看整页。按五线位置切出每个 system，放大 4–6 倍读取。
2. **密集和弦禁止"肉眼定音"**：三度叠置的音头会粘连成"8"字形。必须做像素测量：
   - 先用行亮度剖面定出 5 条五线；
   - 再在单个和弦的 x 窗口内找暗行带（音头比线厚，宽度 > 8 px）；
   - 由音头中心 y 映射到线/间，得到音高；
   - 用 `scripts/staff_spacing.ps1` 的思路可扩展成测量脚本。
3. **每个音标置信度**：音头粘连、临时记号、加线、手写覆盖处标记为低置信，交给人工确认。
4. **手写标注不要盲目过滤**：本类谱常带手写简谱和音、速度、力度。把印刷层与手写层
   分开记录，手写速度/力度可作为演奏版信息保留；不要为了"干净"破坏印刷谱。
5. **渲染回读**：生成的 MusicXML 用 MuseScore 导出 MP3/PDF，和原图并排比对。

### 模式 B：传统 OMR（适合干净、印刷清晰、无手写的谱）

```
input/*.png → [OpenCV 预处理] → [Audiveris OMR] → *.musicxml
  → [MuseScore 人工校正] → [PDF 导出]
```

Audiveris 仍是可选项（若已安装，check_env.py 会自动检出）。
但注意：密集笙和弦、手写覆盖、低分辨率会让 Audiveris 输出不可用；这时回退到模式 A。

## 2. 脚本清单

| 脚本 | 作用 | 状态 |
|---|---|---|
| `scripts/extract_pdf.py` | 抽取 PDF 内嵌原图，报告等效 DPI，过滤水印小图 | 新增，已实测 |
| `scripts/staff_spacing.ps1` | 测五线线距，输出 OK / MARGINAL / TOO_LOW | 新增，已实测 |
| `scripts/crop_region.ps1` | 按坐标裁切并放大图像，生成逐系统读谱图 | 新增 |
| `scripts/dump_raw.ps1` | 整页转灰度原始数据，供批量像素分析 | 新增 |
| `scripts/chord_scan.py` | 自动检测一个系统的全部和弦并读音高，与底稿对比 | 新增，已实测 |
| `scripts/diff_scores.py` | `.mscz` / `.musicxml` 逐小节对比，输出差异清单和一致率 | 新增，已实测 |
| `scripts/harmony_check.py` | 和声体检：内部冲突/半音斜向/调外音/非典型结构 | 新增 |
| `scripts/check_env.py` | 环境检查（PowerShell/MuseScore 必需，OpenCV/Audiveris 可选） | 已更新 |
| `scripts/preprocess.py` | OpenCV 预处理（模式 B） | 保留 |
| `scripts/run_omr.py` | Audiveris 调用（模式 B） | 保留 |
| `scripts/export_pdf.py` | MuseScore / LilyPond 导出 | 保留 |
| `scripts/pipeline.py` | 模式 B 全流程编排 | 保留 |

### 常用命令

```bash
# 1) 审计源文件
python scripts/extract_pdf.py "扫描件.pdf" --outdir temp/pdf_images
powershell -File scripts/staff_spacing.ps1 -Src "temp/pdf_images/pdf_image_01.jpg"

# 2) 裁切某个谱表系统（例如第一页第一个 system）
powershell -File scripts/crop_region.ps1 -Src page.jpg -Out sys1.png -X 140 -Y 230 -W 1600 -H 230 -Scale 4

# 3) 对比底稿与转谱结果
python scripts/diff_scores.py "人工底稿.mscz" "转谱结果.musicxml" --max-report 50

# 4) 渲染试听
MuseScore4.exe --sound-profile "MuseScore Basic" -b 192 -o out.mp3 out.musicxml
MuseScore4.exe -o out.pdf out.musicxml
```

## 3. 校对与验收

- **有底稿时**：一律用 `diff_scores.py` 对照，不要凭感觉判断。该脚本按"有音符小节"
  做内容对齐，忽略各工具对多小节休止的不同压缩方式；一致率按事件数统计。
- **无底稿时**：抽样 3–5 个系统（慢速/中速/密集各取一），逐和弦像素测量
  （`chord_scan.py`），记录音高准确率；低于 99% 不允许批量推进。
- **每页留痕**：记录该页的谱表数、线距、低置信和弦清单、人工修改清单。

### 3.1 分歧仲裁：乐理优先，识别次之，人工兜底

底稿/候选谱与印刷谱出现分歧时，按以下顺序裁决：

1. **乐理排除**：对两版分歧和弦分别做和声体检（`harmony_check.py`）——
   - 一方存在**和弦内部冲突**（持续小二度/大七度）、**无解决的调外音**、
     **功能断裂**（离调和弦不解决）→ 判定该版本不成立，取另一方；
   - 一方只是**转调段落的调外音**（如 D 小调段的 B♭/E♭、那不勒斯和弦）、
     **半音 planing**、**离调解决**（V/iv → iv）→ 这是正常作曲手法，不是错误。
2. **两版都和声成立 → 按识别（印刷谱）为准**。识别的是原谱，底稿修改若
   无乐理依据则回退。
3. **乐理也裁不了的**（节奏/内容缺失、装饰音差异、加和弦 vs 加休止、
   小节号对齐未确认）→ **不得擅自定稿**，进入"待人工核验清单"。

注意：乐理体检标记的"调外音"大多是有意的转调/离调（实测本谱 33 个标记小节
中绝大多数是 D 小调/G 小调转调段与那不勒斯和弦），**标记 ≠ 错误**，
必须结合上下文（前后和弦、段落调性）人工判读后再下结论。

### 3.2 最终交付物

- 修订后 MusicXML + 排版 PDF + 参考 MP3
- 差异报告（`diff_scores.py` 输出 + 每处分歧的裁切图）
- **待人工核验小节清单**（必须交付）：所有不满足以下条件的小节——
  - 像素几何读数存在半音级歧义（音头与线粘连、临时记号无法判定）
  - 底稿与印刷谱分歧且乐理无法裁定
  - 检测置信度低（手写覆盖、加线音、密集段）
  清单每条应包含：小节号、底稿记法、印刷谱读数、裁切图路径、
  乐理意见、建议动作（改回/保留/待定）。**没有这份清单不允许宣布完成。**

## 4. 实测经验（2026-10，本机）

- 同一份《梦寻长安》：
  - CamScanner 导出的 JPG：793×1123，96 DPI，五线间距 6–7 px → OMR 不可用。
  - 同一 PDF 内嵌图：1796×2560，约 219 DPI，五线间距 16 px → 可逐音转谱。
- 抽样验证：5 个和弦、15 个音，像素读数与人工 `.mscz` 底稿 **15/15 一致**。
- 但纯肉眼读图在低音叠置和弦上出过错（把 C–F–A 看成 E–G–B）；
  引入像素测量后才全部正确。**几何校验不是可选项。**
- 219 DPI 仍低于 300 DPI 推荐值；密集快速段（十六分音符、加线、临时记号）
  需要逐小节核对。
- MuseScore 4.7.3 便携版 CLI 实测：`-o *.pdf`、`-o *.mp3` 可用；
  本构建下 `-o *.wav`、`-o *.png` 未生成文件，不要依赖。
- MuseScore 自带 `wind.reed.sheng`（笙）乐器；无笙音源时可用 GM Reed Organ 代音色。

## 5. 常见坑

| 问题 | 原因 / 解决 |
|---|---|
| PDF 导出图和 PDF 内嵌图清晰度差很多 | 先 `extract_pdf.py`，用内嵌原图 |
| 音头粘成"8"字，读不准 | 三度叠置 + 低分辨率；做像素测量，别靠肉眼 |
| 手写覆盖谱线 | 无法可靠分离时，按低置信区处理并人工确认；不要强行滤波 |
| 两份谱小节数不一致 | 多小节休止编码方式不同；用 `diff_scores.py` 的内容对齐，不按索引硬比 |
| PowerShell 脚本行为诡异 | 变量名大小写不敏感；`$Lum` 与 `$lum` 会互相覆盖，命名要区分 |
| MuseScore CLI 不覆盖已有输出 | 先删除旧文件再导出 |
| 中文路径/文件名 | Python 侧正常；PowerShell 脚本参数用绝对路径并加引号 |

## 6. 模式 B 的保留流程

```bash
python scripts/check_env.py
# 将扫描图放入 input/
python scripts/pipeline.py
```

模式 B 仍按四步走：预处理 → Audiveris OMR → MuseScore 人工校正 → PDF 导出。
如果 `check_env.py` 显示 Audiveris 可用，可先跑一遍作为基线；其结果必须用
`diff_scores.py` 或人工校对验证后才能交付。
