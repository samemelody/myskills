#!/usr/bin/env python3
"""
对扫描件中的一个谱表系统做音头几何测量，输出每个和弦的音高集合，
并与 .mscz / .musicxml 底稿对比。

原理:
  1. 由 5 条五线 y 坐标得到线距 s，建立 y -> 音级 映射（顶线 = F5）。
  2. 在系统 x 范围内找"暗列簇"（宽度 8-40px 的和弦块，排除小节线/符干）。
  3. 对每个簇取中心窗口，按行统计暗像素得到音头条带；条带高 > 20px 视为
     三度叠置的双音头，拆成两个中心。
  4. 音头中心 y 映射为自然音级（不含升降号），与底稿 MIDI 以 ±1 半音容差匹配
     （扫描件读不出临时记号，升/降号差按"待人工确认"处理）。

用法:
  python scripts/chord_scan.py <page.raw> --lines 524,540,554,570,586 \
      --x0 140 --x1 1740 [--ref score.mscz --measures 7-14]

注意: <page.raw> 需先用 scripts/dump_raw.ps1 生成。
"""

import argparse
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LUM = 170

# 自然音级 MIDI 表：索引 0 = 顶线 F5，每 +1 向下一个音级
NATURAL = [84, 83, 81, 79, 77, 76, 74, 72, 71, 69, 67, 65, 64, 62, 60, 59,
           57, 55, 53, 52, 50, 48, 47, 45, 43]
# 对应音名（用于展示）
NAMES = ['C6', 'B5', 'A5', 'G5', 'F5', 'E5', 'D5', 'C5', 'B4', 'A4', 'G4',
         'F4', 'E4', 'D4', 'C4', 'B3', 'A3', 'G3', 'F3', 'E3', 'D3', 'C3',
         'B2', 'A2', 'G2']
TOP_INDEX = 4  # NATURAL/TOP_NAMES 中 F5 的位置


def load_raw(path):
    with open(path, 'rb') as f:
        header = f.readline().split()
        assert header[0] == b'SCORERAW', '不是 dump_raw.ps1 生成的文件'
        w, h, stride = int(header[1]), int(header[2]), int(header[3])
        data = f.read()
    return w, h, stride, data


def make_is_dark(data, stride):
    def is_dark(x, y):
        off = stride * y + 3 * x
        b, g, r = data[off], data[off + 1], data[off + 2]
        return (b * 29 + g * 150 + r * 77) >> 8 < LUM
    return is_dark


def detect_pitches_by_coverage(is_dark, cx, y1, spacing, ytop, ybot,
                               head_w=15, head_h=9, threshold=0.42):
    """在候选中心 x 处，对每个半音级位置计算椭圆掩膜内的暗像素覆盖率，
    取局部极大且超过阈值的位置为音头。比行条带法更抗五线粘连。"""
    half_w = head_w // 2
    half_h = head_h // 2
    mask = [(dx, dy) for dy in range(-half_h, half_h + 1)
            for dx in range(-half_w, half_w + 1)
            if (dx / (half_w + 0.5)) ** 2 + (dy / (half_h + 0.5)) ** 2 <= 1]
    n_max = int((ybot - y1) / (spacing / 2)) + 2
    scores = []
    for n in range(-4, n_max):
        yc = y1 + n * spacing / 2
        cnt = 0
        for dx, dy in mask:
            if is_dark(int(cx + dx), int(yc + dy)):
                cnt += 1
        scores.append((n, cnt / len(mask)))
    pitches = []
    for i, (n, sc) in enumerate(scores):
        if sc < threshold:
            continue
        left = scores[i - 1][1] if i > 0 else 0.0
        right = scores[i + 1][1] if i < len(scores) - 1 else 0.0
        if sc >= left and sc >= right:
            pitches.append(n)
    return pitches


def detect_chords(is_dark, lines, x0, x1,
                  band_above=10, band_below=42,
                  min_col_dark=6, min_width=8, max_width=46):
    y1, y5 = lines[0], lines[4]
    spacing = (y5 - y1) / 4.0
    ytop = int(y1 - band_above)
    ybot = int(y5 + band_below)
    band_h = ybot - ytop

    # 五线本身会让每一列都有 ~15 个暗行，必须剔除线附近(±2px)的行
    line_rows = set()
    for ly in lines:
        for dy in range(-2, 3):
            line_rows.add(ly + dy)

    cols = {}
    for x in range(x0, x1):
        d = sum(1 for y in range(ytop, ybot)
                if y not in line_rows and is_dark(x, y))
        cols[x] = d

    # 聚类暗列（小节线是整高暗列，直接排除）
    clusters = []
    cur = []
    for x in range(x0, x1):
        d = cols[x]
        is_barline = d >= band_h * 0.8
        if d >= min_col_dark and not is_barline:
            if cur and x - cur[-1] > 4:
                clusters.append(cur)
                cur = []
            cur.append(x)
        elif cur and x - cur[-1] > 4:
            clusters.append(cur)
            cur = []
    if cur:
        clusters.append(cur)

    events = []
    for cl in clusters:
        width = cl[-1] - cl[0] + 1
        if width < min_width or width > max_width:
            continue
        cx = (cl[0] + cl[-1]) // 2
        half = max(6, width // 2 + 2)
        wx0, wx1 = cx - half, cx + half
        wlen = wx1 - wx0 + 1
        row_th = max(2, int(wlen * 0.3))

        # 行分类：音头行(中等宽度) / 纯线行(接近全宽)。
        # 音头与五线粘连时，条带中心会被线拉偏——所以先按"音头行"分组，
        # 组内允许跨 1 条五线(间隙 ≤5px)合并，中心取音头行首尾中点。
        head_lo = 8
        head_hi = int(wlen * 0.75)
        head_rows = []
        for y in range(ytop, ybot):
            d = sum(1 for x in range(wx0, wx1 + 1) if is_dark(x, y))
            if head_lo <= d <= head_hi:
                head_rows.append(y)

        # 按 run 分组（间隙 ≤5px，即允许跨 1 条五线）
        runs = []
        for y in head_rows:
            if runs and y - runs[-1][1] <= 5:
                runs[-1][1] = y
            else:
                runs.append([y, y])
        # 线的抗锯齿尾巴（≤2px 的 run）会拉偏中心，丢弃
        if len(runs) > 1:
            kept = [r for r in runs if r[1] - r[0] + 1 > 2]
            if kept:
                runs = kept

        pitches = []
        for a, z in runs:
            hgt = z - a + 1
            if hgt < 7:
                continue
            if hgt > 20:
                # 三度叠置双音头粘连，拆两个中心
                for frac in (0.28, 0.72):
                    yc = a + (z - a) * frac
                    pitches.append(int(round((yc - y1) / (spacing / 2))))
            else:
                yc = (a + z) / 2
                pitches.append(int(round((yc - y1) / (spacing / 2))))

        midis = []
        names = []
        for n in pitches:
            idx = TOP_INDEX + n
            if 0 <= idx < len(NATURAL):
                midis.append(NATURAL[idx])
                names.append(NAMES[idx])
        events.append({'x': cx, 'width': width, 'midis': sorted(midis),
                       'names': sorted(names)})
    return events


def load_ref_chords(ref_path, m_from, m_to):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import diff_scores
    staves = diff_scores.parse_mscz(ref_path) if ref_path.lower().endswith('.mscz') \
        else diff_scores.parse_musicxml(ref_path)
    measures = staves[0]
    events = []
    for m in range(m_from, m_to + 1):
        voices = measures[m - 1]
        for vi in sorted(voices):
            for e in voices[vi]:
                if e['kind'] == 'chord':
                    events.append({'measure': m, 'midis': list(e['pitches'])})
    return events


def compare(ref, scan):
    rows = []
    n = max(len(ref), len(scan))
    exact = soft = miss = 0
    for i in range(n):
        r = ref[i] if i < len(ref) else None
        s = scan[i] if i < len(scan) else None
        if r is None:
            rows.append((i + 1, '-', s, '候选多出（可能为休止符/记号误检）'))
            continue
        if s is None:
            rows.append((i + 1, r['midis'], '-', '扫描件未检出'))
            miss += 1
            continue
        rp, sp = set(r['midis']), set(s['midis'])
        if rp == sp:
            verdict = '一致'
            exact += 1
        elif all(any(abs(a - b) <= 1 for b in sp) for a in rp) and len(rp) == len(sp):
            verdict = '音级一致（差临时记号，需人工确认）'
            soft += 1
        else:
            verdict = '❌ 不一致'
        rows.append((i + 1, r['midis'], s['midis'], verdict))
    return rows, exact, soft, miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('raw', help='dump_raw.ps1 生成的 raw 文件')
    ap.add_argument('--lines', required=True, help='5 条线的 y，逗号分隔')
    ap.add_argument('--x0', type=int, default=140)
    ap.add_argument('--x1', type=int, default=1740)
    ap.add_argument('--ref', help='底稿 .mscz/.musicxml')
    ap.add_argument('--measures', help='底稿小节范围，如 7-14')
    args = ap.parse_args()

    w, h, stride, data = load_raw(args.raw)
    is_dark = make_is_dark(data, stride)
    lines = [int(v) for v in args.lines.split(',')]

    scan = detect_chords(is_dark, lines, args.x0, args.x1)
    print(f'检出 {len(scan)} 个和弦块:')
    for i, e in enumerate(scan, 1):
        print(f'  #{i:<3} x={e["x"]:<5} w={e["width"]:<3} {e["names"]}')

    if args.ref and args.measures:
        a, b = [int(v) for v in args.measures.split('-')]
        ref = load_ref_chords(args.ref, a, b)
        print(f'\n底稿 m{a}-{b} 共 {len(ref)} 个和弦，开始对比:')
        rows, exact, soft, miss = compare(ref, scan)
        for idx, r, s, v in rows:
            print(f'  #{idx:<3} 底稿={r}  扫描={s}  {v}')
        total = len(rows)
        print(f'\n一致 {exact}，音级一致(差临时记号) {soft}，未检出 {miss}，'
              f'共 {total}，硬一致率 {exact / total * 100:.1f}%'
              f'（含临时记号容差 {100 * (exact + soft) / total:.1f}%）')


if __name__ == '__main__':
    main()
