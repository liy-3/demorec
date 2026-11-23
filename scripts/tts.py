# -*- coding: utf-8 -*-
"""demorec tts — synthesize narration and emit timing.json.

One mp3 per narration line so that every line gets an exact timestamp.
Scenes are timed by those timestamps, which is what lets a scene script say
"hold until line 3 has finished" instead of hard-coding seconds.

Changing one line of narration therefore re-flows the whole scene rhythm
automatically: re-run tts, then re-record only that scene.
"""
import os, sys, json, asyncio, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from stage import find_ffmpeg, probe_media  # noqa: E402


def tts_dir(workdir):
    d = os.path.join(workdir, 'tts')
    os.makedirs(d, exist_ok=True)
    return d


async def synthesize(workdir, scenes, voice, rate, force=False):
    import edge_tts
    d = tts_dir(workdir)
    for sc in scenes:
        sid = sc['id']
        lines = sc.get('narration') or []
        if not lines:
            continue
        for i, text in enumerate(lines):
            p = os.path.join(d, '%s_%02d.mp3' % (sid, i))
            if not force and os.path.exists(p) and os.path.getsize(p) > 2000:
                continue
            last = None
            for attempt in range(4):
                try:
                    await edge_tts.Communicate(text, voice, rate=rate).save(p)
                    if os.path.exists(p) and os.path.getsize(p) > 2000:
                        break
                except Exception as e:
                    last = e
                    await asyncio.sleep(1.5 * (attempt + 1))
            if not (os.path.exists(p) and os.path.getsize(p) > 2000):
                raise RuntimeError('TTS failed for %s line %d: %s' % (sid, i, last))
            print('  tts %-12s %02d  %6d bytes' % (sid, i, os.path.getsize(p)), flush=True)


def mp3_duration(path):
    from mutagen.mp3 import MP3
    return MP3(path).info.length


def build_timing(workdir, scenes, lead, gap, tail):
    """timing.json: per scene, the start/end of every narration line."""
    d = tts_dir(workdir)
    timing = {}
    total = 0.0
    for sc in scenes:
        sid = sc['id']
        lines = sc.get('narration') or []
        if not lines:
            timing[sid] = {'sent_starts': [], 'sent_ends': [], 'durs': [],
                           'scene_len': 0.0, 'narration': []}
            continue
        starts, ends, durs = [], [], []
        t = lead
        for i, text in enumerate(lines):
            dur = mp3_duration(os.path.join(d, '%s_%02d.mp3' % (sid, i)))
            starts.append(round(t, 3))
            ends.append(round(t + dur, 3))
            durs.append(round(dur, 3))
            t += dur + gap
        scene_len = round(ends[-1] + tail, 3)
        timing[sid] = {
            'title': sc.get('title', sid),
            'sent_starts': starts,
            'sent_ends': ends,
            'durs': durs,
            'scene_len': scene_len,
            'narration': lines,
        }
        total += scene_len
    return timing, round(total, 2)


def main(argv):
    import yaml
    workdir = os.path.abspath(argv[0]) if argv else os.getcwd()
    force = '--force' in argv
    with open(os.path.join(workdir, 'demorec.yaml'), encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    with open(os.path.join(workdir, 'scenes.yaml'), encoding='utf-8') as f:
        scenes = yaml.safe_load(f)['scenes']

    voice = cfg.get('voice', {}).get('name', 'zh-CN-YunxiNeural')
    rate = str(cfg.get('voice', {}).get('rate', '+8%'))
    pace = cfg.get('pacing', {})
    lead = float(pace.get('lead_in', 0.8))
    gap = float(pace.get('gap', 0.38))
    tail = float(pace.get('tail', 1.6))

    print('synthesizing narration with %s at %s ...' % (voice, rate), flush=True)
    asyncio.run(synthesize(workdir, scenes, voice, rate, force=force))
    timing, total = build_timing(workdir, scenes, lead, gap, tail)
    with open(os.path.join(workdir, 'timing.json'), 'w', encoding='utf-8') as f:
        json.dump(timing, f, ensure_ascii=False, indent=1)

    print('\nnarration total %.1fs (%.1f min)' % (total, total / 60.0), flush=True)
    for sc in scenes:
        t = timing[sc['id']]
        print('  %-14s %6.1fs  %d lines' % (sc['id'], t['scene_len'], len(t['narration'])), flush=True)
    print('timing.json written', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
