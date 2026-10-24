#!/usr/bin/env python3
"""
对 .mscz / .musicxml 做和声体检：找"演奏者耳朵会抓到"的和弦异常。

检查项:
  1. 和弦内部小二度/大七度冲突（持续音色下极刺耳）
  2. 相邻和弦的半音斜向冲突（同一框架内一个音移动半音，如 F↔F#）
  3. 调外音（默认 C 大调/A 小调框架，F# 作为常见离调音单独标注）
  4. 结构异常（既非三度叠置也非笙传统四/五度叠置的和弦）

用法:
  python scripts/harmony_check.py <score.mscz|score.musicxml>
"""

import argparse
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diff_scores

PC_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NATURAL_PCS = {0, 2, 4, 5, 7, 9, 11}
# 常见离调音：F#（V/V、D 大调）、Bb（V/VI）、C#（A 大调/V of D）
COMMON_ALTERED = {6, 10, 1}


def pc_name(m):
    return PC_NAMES[m % 12] + str(m // 12 - 1)


def chord_label(midis):
    return ','.join(pc_name(m) for m in midis)


def has_internal_clash(midis):
    """和弦内含小二度/大七度音程（模12后差1）"""
    pcs = sorted({m % 12 for m in midis})
    for i in range(len(pcs)):
        for j in range(i + 1, len(pcs)):
            if (pcs[j] - pcs[i]) % 12 in (1, 11):
                return True
    return False


def chromatic_shift(prev, cur):
    """相邻和弦恰好只有一个音移动了半音（其余相同）→ 记号嫌疑"""
    p1, p2 = {m % 12 for m in prev}, {m % 12 for m in cur}
    if len(p1) != len(p2):
        return None
    only1 = p1 - p2
    only2 = p2 - p1
    if len(only1) != 1 or len(only2) != 1:
        return None
    a, b = only1.pop(), only2.pop()
    if (b - a) % 12 in (1, 11):
        return (a, b)
    return None


def is_tertian_or_sheng(midis):
    """三度叠置三和弦/七和弦，或笙传统叠置（纯四五度+八度框架）"""
    pcs = sorted({m % 12 for m in midis})
    if len(pcs) <= 2:
        return True
    # 三度叠置：存在一个根音，其余音在 {0,3,4,7,8,11} 相对集合内
    for root in pcs:
        rel = {(p - root) % 12 for p in pcs}
        if rel <= {0, 3, 4, 7, 8, 11}:
            return True
    # 四五度叠置：相邻音级差为 5 或 7（允许八度）
    rel = sorted((p - pcs[0]) % 12 for p in pcs)
    ok = True
    for i in range(1, len(rel)):
        if (rel[i] - rel[i - 1]) % 12 not in (5, 7, 2, 10, 0):
            ok = False
            break
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('score')
    ap.add_argument('--max-report', type=int, default=40)
    args = ap.parse_args()

    path = args.score
    staves = diff_scores.parse_mscz(path) if path.lower().endswith('.mscz') \
        else diff_scores.parse_musicxml(path)
    measures = staves[0]

    # 展平为和弦事件序列
    seq = []  # (measure, [midis])
    for mi, voices in enumerate(measures, 1):
        for vi in sorted(voices):
            for e in voices[vi]:
                if e['kind'] == 'chord' and e['pitches']:
                    seq.append((mi, sorted(e['pitches'])))

    print(f'共 {len(measures)} 小节，{len(seq)} 个和弦事件')
    print('=' * 60)

    flags = []

    # 1. 和弦内部冲突
    for mi, ch in seq:
        if has_internal_clash(ch):
            flags.append((mi, '内部冲突', f'{chord_label(ch)} 含小二度/大七度'))

    # 2. 相邻和弦半音斜向
    for k in range(1, len(seq)):
        mi, ch = seq[k]
        pmi, pch = seq[k - 1]
        shift = chromatic_shift(pch, ch)
        if shift:
            a, b = shift
            flags.append((mi, '半音斜向',
                          f'{chord_label(ch)}: {PC_NAMES[a]}→{PC_NAMES[b]} '
                          f'(前小节 m{pmi})'))

    # 3. 调外音（C/Am 框架；F#/Bb/C# 常见离调单独提示）
    for mi, ch in seq:
        out = [pc_name(m) for m in ch if m % 12 not in NATURAL_PCS]
        if not out:
            continue
        unexpected = [o for o in out if int(o[:-1].rstrip('#+B') and
                                           {'C#': 1, 'D#': 3, 'F#': 6, 'G#': 8, 'A#': 10, 'Bb': 10}.get(o[:-1], -1)) not in COMMON_ALTERED]
        if unexpected:
            flags.append((mi, '调外音', f'{chord_label(ch)} 含 {",".join(unexpected)}'))

    # 4. 结构异常
    for mi, ch in seq:
        if not is_tertian_or_sheng(ch):
            flags.append((mi, '非典型结构', f'{chord_label(ch)}'))

    # 汇总
    if not flags:
        print('未发现明显和声异常。')
        return 0

    # 合并同一小节的多条
    by_measure = {}
    for mi, kind, detail in flags:
        by_measure.setdefault(mi, []).append((kind, detail))

    print(f'标记 {len(by_measure)} 个小节、{len(flags)} 条：')
    print('-' * 60)
    shown = 0
    for mi in sorted(by_measure):
        items = by_measure[mi]
        kinds = {k for k, _ in items}
        print(f'  m{mi:<5} [{"；".join(sorted(kinds))}]')
        for kind, detail in items:
            print(f'         {detail}')
        shown += 1
        if shown >= args.max_report:
            print(f'  ... 其余 {len(by_measure) - shown} 小节省略')
            break
    return 0


if __name__ == '__main__':
    sys.exit(main())
