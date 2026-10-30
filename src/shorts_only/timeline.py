"""Time mapping for preview hooks and explicit cuts; never invent word timings."""
import re
import subprocess


def silence_cuts(video, duration):
    """Optional audio-only pass to remove long pauses; all kept ranges stay explicit."""
    result = subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(video),'-vn',
                             '-af','silencedetect=noise=-35dB:d=0.6','-f','null','-'],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('無音カットを省略: FFmpegで音声を処理できませんでした')
    intervals, silence_start = [], None
    for kind, value in re.findall(r'silence_(start|end):\s*([0-9.]+)',result.stderr):
        if kind == 'start':
            silence_start = float(value)
        elif silence_start is not None:
            intervals.append((silence_start,float(value)))
            silence_start = None
    if silence_start is not None:
        intervals.append((silence_start,duration))
    kept, cursor = [], 0.0
    for start, end in intervals:
        if start > cursor:
            kept.append((cursor,min(duration,start+0.12)))
        cursor = max(cursor,end-0.12)
    if cursor < duration:
        kept.append((cursor,duration))
    return kept or [(0,duration)]


def read_srt(path):
    cues = []
    if not path.is_file():
        return cues
    for block in re.split(r'\n\s*\n', path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip()):
        lines = block.splitlines()
        at = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if at is None:
            continue
        stamps = re.findall(r'(\d+):(\d{2}):(\d{2})[,.](\d{3})', lines[at])
        if len(stamps) != 2:
            continue
        start, end = [int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000 for h,m,s,ms in stamps]
        cues.append({'start': start, 'end': end, 'text': '\n'.join(lines[at+1:])})
    return cues


def build(duration, cues, hook='auto', cuts=None, hook_seconds=None):
    # Hook points come from supplied clip-relative peaks or a cheap caption-text heuristic.
    body = [(max(0, float(start)), min(duration, float(end)))
            for start, end in (cuts if cuts is not None else [(0, duration)])]
    body = [(start, end) for start, end in body if end > start]
    if not body:
        return {'segments': [], 'duration': 0, 'hook_method': 'none'}
    peaks = list(hook_seconds or [])[:3]
    method = 'supplied_peaks' if peaks else 'caption_heuristic'
    if not peaks and hook != 'off':
        eligible = [c for c in cues if any(c['start'] >= start and c['start'] < end for start,end in body)]
        ranked = sorted(eligible, key=lambda c: sum(c['text'].count(k) for k in ('！', '!', '？', '?', 'すご', 'やば', 'えっ', 'まじ')), reverse=True)
        for cue in ranked:
            point = float(cue['start'])
            if all(abs(point - p) >= 1 for p in peaks):
                peaks.append(point)
            if len(peaks) == 3:
                break
    if not peaks:
        method = 'none'
    ranges = []
    if hook != 'off':
        for point in peaks:
            start = float(point)
            containing = next(((a, b) for a, b in body if a <= start < b), None)
            if containing:
                ranges.append((start, min(containing[1], start + 1), 'preview'))
    for start, end in body:
        start, end = max(0, float(start)), min(duration, float(end))
        if end > start:
            ranges.append((start, end, 'body'))
    sequence, offset = [], 0.0
    for start, end, kind in ranges:
        sequence.append({'source_start': start, 'source_end': end, 'target_start': offset, 'duration': end-start, 'kind': kind})
        offset += end-start
    if not any(part['kind'] == 'preview' for part in sequence):
        method = 'none'
    return {'segments': sequence, 'duration': offset, 'hook_method': method if hook != 'off' else 'off'}


def remap(cues, sequence):
    mapped = []
    for part in sequence:
        for cue in cues:
            start, end = max(cue['start'], part['source_start']), min(cue['end'], part['source_end'])
            if end > start:
                mapped.append({'start': part['target_start'] + start-part['source_start'],
                               'end': part['target_start'] + end-part['source_start'], 'text': cue['text']})
    return sorted(mapped, key=lambda cue: cue['start'])


def srt_text(cues):
    def stamp(value):
        ms = round(value*1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    return '\n\n'.join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i,c in enumerate(cues,1)) + '\n'
