#!/usr/bin/env python3
"""
对比两份乐谱（.mscz / .musicxml / .xml），输出逐小节差异清单。

用途:
  1. 校验 OMR/AI 转谱结果 与 人工底稿 的差异
  2. 校验同一份谱在不同工具间转换后的完整性

用法:
    python scripts/diff_scores.py <reference> <candidate> [--max-report 50] [--json]

退出码: 0 = 完全一致；1 = 存在差异；2 = 解析失败
"""

import argparse
import difflib
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ---------- 统一事件模型 ----------
# event = {"kind": "chord"|"rest"|"grace", "pitches": (int,...) | (),
#          "duration": "quarter", "dots": 0}

def _event(kind, pitches, duration, dots):
    return {
        'kind': kind,
        'pitches': tuple(sorted(pitches)),
        'duration': duration or '?',
        'dots': dots,
    }


def parse_mscz(path):
    with zipfile.ZipFile(path) as z:
        mscx = next(n for n in z.namelist() if n.endswith('.mscx'))
        root = ET.fromstring(z.read(mscx))

    score = root.find('Score')
    if score is None:
        raise ValueError('无 Score 节点')

    staves = score.findall('Staff')
    result = []
    for staff in staves:
        measures = []
        for m in staff.findall('Measure'):
            voices = {}
            for vi, v in enumerate(m.findall('voice'), 1):
                events = []
                for el in v:
                    if el.tag == 'Chord':
                        pitches = [int(n.findtext('pitch'))
                                   for n in el.findall('Note') if n.findtext('pitch')]
                        dots = len(el.findall('dots'))
                        kind = 'grace' if el.find('grace8') is not None else 'chord'
                        events.append(_event(kind, pitches,
                                             el.findtext('durationType'), dots))
                    elif el.tag == 'Rest':
                        dots = len(el.findall('dots'))
                        events.append(_event('rest', (), el.findtext('durationType'), dots))
                if events:
                    voices[vi] = events
            measures.append(voices)
        result.append(measures)
    return result


def parse_musicxml(path):
    root = ET.parse(path).getroot()
    parts = root.findall('part')
    result = []
    for part in parts:
        measures = []
        for m in part.findall('measure'):
            voices = {}
            for note in m.findall('note'):
                voice = int(note.findtext('voice') or 1)
                is_chord = note.find('chord') is not None
                is_rest = note.find('rest') is not None
                is_grace = note.find('grace') is not None
                dots = len(note.findall('dot'))
                dur = note.findtext('type')
                if not dur:
                    # MusicXML 的整小节休止没有 <type>；measure="yes" 在 <rest> 上
                    rest_el = note.find('rest')
                    whole_bar = rest_el is not None and rest_el.get('measure') == 'yes'
                    dur = 'measure' if is_rest and whole_bar else '?'
                pitch_el = note.find('pitch')
                pitch = None
                if pitch_el is not None:
                    step = pitch_el.findtext('step')
                    alter = int(pitch_el.findtext('alter') or 0)
                    octave = int(pitch_el.findtext('octave'))
                    base = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[step]
                    pitch = 12 * (octave + 1) + base + alter

                if is_chord and voices.get(voice):
                    last = voices[voice][-1]
                    last['pitches'] = tuple(sorted(last['pitches'] + (pitch,)))
                    continue

                if is_rest:
                    ev = _event('rest', (), dur, dots)
                else:
                    ev = _event('grace' if is_grace else 'chord', (pitch,), dur, dots)
                voices.setdefault(voice, []).append(ev)
            measures.append(voices)
        result.append(measures)
    return result


def load(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.mscz':
        return parse_mscz(path)
    if suffix in ('.musicxml', '.xml'):
        return parse_musicxml(path)
    raise ValueError(f'不支持的格式: {suffix}（支持 .mscz/.musicxml/.xml）')


def describe(ev):
    if ev['kind'] == 'rest':
        body = 'rest'
    else:
        body = ','.join(str(p) for p in ev['pitches'])
    dots = '.' * ev['dots']
    return f'{ev["duration"]}{dots}[{body}]'


def _measure_sig(m):
    parts = []
    for voice in sorted(m):
        parts.append('|'.join(describe(e) for e in m[voice]))
    return '||'.join(parts)


def _is_all_rest(m):
    events = [e for v in m.values() for e in v]
    return bool(events) and all(e['kind'] == 'rest' for e in events)


def _compare_measure(r, c, label, stats, issues):
    """比较两个小节，把结果累加进 stats，差异写入 issues。"""
    for voice in sorted(set(r) | set(c)):
        rv = r.get(voice, [])
        cv = c.get(voice, [])
        stats['events'] += max(len(rv), len(cv))
        for j in range(max(len(rv), len(cv))):
            if j >= len(rv):
                issues.append(f'{label} v{voice} #{j+1}: 候选多出 {describe(cv[j])}')
                continue
            if j >= len(cv):
                issues.append(f'{label} v{voice} #{j+1}: 候选缺少 {describe(rv[j])}')
                continue
            a, b = rv[j], cv[j]
            if a == b:
                stats['matched'] += 1
            else:
                issues.append(f'{label} v{voice} #{j+1}: 参考 {describe(a)} ≠ 候选 {describe(b)}')


def diff(ref, cand, max_report):
    if len(ref) != 1 or len(cand) != 1:
        print(f'⚠️  谱表数不同: 参考 {len(ref)}，候选 {len(cand)}；只比较第 1 个谱表')

    ref_m, cand_m = ref[0], cand[0]

    # 休止小节各工具的压缩方式不同，不参与逐小节对齐；只比较有音符的小节。
    ref_idx = [i for i, m in enumerate(ref_m) if not _is_all_rest(m)]
    cand_idx = [i for i, m in enumerate(cand_m) if not _is_all_rest(m)]
    ref_sigs = [_measure_sig(ref_m[i]) for i in ref_idx]
    cand_sigs = [_measure_sig(cand_m[i]) for i in cand_idx]

    stats = {'events': 0, 'matched': 0}
    issues = []
    sm = difflib.SequenceMatcher(None, ref_sigs, cand_sigs, autojunk=False)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                ri, ci = ref_idx[i1 + k], cand_idx[j1 + k]
                _compare_measure(ref_m[ri], cand_m[ci],
                                 f'小节 {ri+1}/候选 {ci+1}', stats, issues)
        elif tag == 'replace':
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                ri, ci = ref_idx[i1 + k], cand_idx[j1 + k]
                _compare_measure(ref_m[ri], cand_m[ci],
                                 f'小节 {ri+1}/候选 {ci+1}', stats, issues)
            for k in range(n, i2 - i1):
                issues.append(f'小节 {ref_idx[i1+k]+1}: 候选缺少有音符小节 {ref_sigs[i1+k]}')
            for k in range(n, j2 - j1):
                issues.append(f'候选小节 {cand_idx[j1+k]+1}: 参考中无对应 ({cand_sigs[j1+k]})')
        elif tag == 'delete':
            for k in range(i1, i2):
                issues.append(f'小节 {ref_idx[k]+1}: 候选缺少有音符小节 {ref_sigs[k]}')
        elif tag == 'insert':
            for k in range(j1, j2):
                issues.append(f'候选小节 {cand_idx[k]+1}: 参考中无对应 ({cand_sigs[k]})')

    return {
        'measures_ref': len(ref_m),
        'measures_cand': len(cand_m),
        'rest_measures_ref': len(ref_m) - len(ref_idx),
        'rest_measures_cand': len(cand_m) - len(cand_idx),
        'content_measures': len(ref_idx),
        'events': stats['events'],
        'matched': stats['matched'],
        'issues': issues,
    }


def main():
    ap = argparse.ArgumentParser(description='对比两份乐谱的逐小节差异')
    ap.add_argument('reference', help='参考谱（人工底稿）')
    ap.add_argument('candidate', help='待校验谱（OMR/AI 输出）')
    ap.add_argument('--max-report', type=int, default=50, help='最多打印多少条差异')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出')
    args = ap.parse_args()

    try:
        ref = load(args.reference)
        cand = load(args.candidate)
    except Exception as e:
        print(f'❌ 解析失败: {e}')
        return 2

    result = diff(ref, cand, args.max_report)
    issues = result['issues']
    total = result['events']
    matched = result['matched']
    rate = (matched / total * 100) if total else 0.0

    if args.json:
        out = dict(result)
        out['accuracy'] = round(rate, 2)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if not issues else 1

    print('=' * 60)
    print('  乐谱对比报告')
    print('=' * 60)
    print(f'  参考: {args.reference}')
    print(f'  候选: {args.candidate}')
    print(f'  小节数: 参考 {result["measures_ref"]} / 候选 {result["measures_cand"]}')
    print(f'  有音符小节: {result["content_measures"]}'
          f'（休止小节 参考 {result["rest_measures_ref"]} / 候选 {result["rest_measures_cand"]}，不参与逐小节对比）')
    print(f'  事件数: {total}，一致: {matched}，一致率: {rate:.1f}%')
    print(f'  差异条目: {len(issues)}')
    print('-' * 60)

    for line in issues[:args.max_report]:
        print('  ' + line)
    if len(issues) > args.max_report:
        print(f'  ... 其余 {len(issues) - args.max_report} 条已省略（--max-report 可调）')

    print('=' * 60)
    return 0 if not issues else 1


if __name__ == '__main__':
    sys.exit(main())
