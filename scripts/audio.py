# -*- coding: utf-8 -*-
"""demorec audio — build one narration track that matches each scene exactly.

TRAP (this bit me): concatenating mixed-format audio with ffmpeg's concat
demuxer corrupts the timestamps. Mixing 24 kHz mono mp3 with 48 kHz stereo wav
produced ~6s of audio per scene instead of ~90s, and the finished video was 30
seconds out of sync with the picture.

Fix: transcode every clip to the same WAV format first, then concatenate, and
force each scene track to the recorded video duration (pad the tail, or shrink
the inter-line gaps when narration overruns).
"""
import os, sys, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from stage import find_ffmpeg, probe_media  # noqa: E402

SAMPLE_RATE = 48000


class AudioBuilder:
    def __init__(self, workdir, ffmpeg):
        self.workdir = workdir
        self.ff = ffmpeg
        self.tts = os.path.join(workdir, 'tts')
        self.out = os.path.join(workdir, 'out')
        os.makedirs(self.tts, exist_ok=True)
        os.makedirs(self.out, exist_ok=True)

    def run(self, *args, **kw):
        pr = subprocess.run([self.ff, '-y', '-hide_banner', '-loglevel', 'error'] + list(args),
                            capture_output=True, text=True, errors='ignore', **kw)
        if pr.returncode != 0:
            raise RuntimeError('ffmpeg failed: %s' % (pr.stderr or '')[:500])
        return pr

    def to_wav(self, src, dst):
        self.run('-i', src, '-ar', str(SAMPLE_RATE), '-ac', '2', '-c:a', 'pcm_s16le', dst)

    def silence(self, sec, dst):
        self.run('-f', 'lavfi', '-i', 'anullsrc=r=%d:cl=stereo' % SAMPLE_RATE,
                 '-t', '%.3f' % sec, '-c:a', 'pcm_s16le', '-ar', str(SAMPLE_RATE),
                 '-ac', '2', dst)

    def concat(self, parts, dst):
        lst = os.path.join(self.tts, '_concat.txt')
        with open(lst, 'w', encoding='utf-8') as f:
            for p in parts:
                f.write("file '%s'\n" % p.replace('\\', '/'))
        self.run('-f', 'concat', '-safe', '0', '-i', lst,
                 '-c:a', 'pcm_s16le', '-ar', str(SAMPLE_RATE), '-ac', '2', dst)
        os.remove(lst)

    def build_scene(self, sid, video, narration_count, pacing):
        lead = float(pacing.get('lead_in', 0.8))
        gap = float(pacing.get('gap', 0.38))
        sent_wavs = []
        for i in range(narration_count):
            src = os.path.join(self.tts, '%s_%02d.mp3' % (sid, i))
            dst = os.path.join(self.tts, '%s_%02d.wav' % (sid, i))
            self.to_wav(src, dst)
            sent_wavs.append(dst)
        durs = [probe_media(self.ff, w)['duration'] for w in sent_wavs]
        speech = lead + sum(durs) + gap * max(0, len(durs) - 1)

        vdur = probe_media(self.ff, video)['duration']
        tail = vdur - speech
        lead_use, gap_use = lead, gap
        if tail < 0.15:
            need = speech - vdur + 0.25
            gap_use = max(0.10, gap - need / max(1, len(durs) - 1))
            lead_use = max(0.40, lead - 0.25)
            tail = vdur - (lead_use + sum(durs) + gap_use * max(0, len(durs) - 1))
        tail_use = max(0.25, tail)

        lead_w = os.path.join(self.tts, '_lead.wav')
        gap_w = os.path.join(self.tts, '_gap.wav')
        tail_w = os.path.join(self.tts, '_tail_%s.wav' % sid)
        self.silence(lead_use, lead_w)
        self.silence(gap_use, gap_w)
        self.silence(tail_use, tail_w)

        parts = [lead_w]
        for i, w in enumerate(sent_wavs):
            parts.append(w)
            if i < len(sent_wavs) - 1:
                parts.append(gap_w)
        parts.append(tail_w)

        scene_wav = os.path.join(self.tts, '_scene_%s.wav' % sid)
        self.concat(parts, scene_wav)
        got = probe_media(self.ff, scene_wav)['duration']
        return scene_wav, durs, (lead_use, gap_use, tail_use), got, vdur


def build(workdir, scenes, cfg, timing_path=None):
    """Returns (full_narration_wav, updated_timing)."""
    ff = find_ffmpeg(cfg.get('build', {}).get('ffmpeg'))
    ab = AudioBuilder(workdir, ff)
    pacing = cfg.get('pacing', {})
    rec_dir = os.path.join(workdir, 'rec')

    timing_path = timing_path or os.path.join(workdir, 'timing.json')
    timing = json.load(open(timing_path, encoding='utf-8')) if os.path.exists(timing_path) else {}

    scene_wavs, report = [], []
    for sc in scenes:
        sid = sc['id']
        lines = sc.get('narration') or []
        if not lines:
            continue
        video = os.path.join(rec_dir, sid + '.mp4')
        if not os.path.exists(video):
            raise SystemExit('missing recording: %s (run the recorder first)' % video)
        wav, durs, pace, got, vdur = ab.build_scene(sid, video, len(lines), pacing)
        scene_wavs.append(wav)
        report.append((sid, vdur, got, got - vdur, pace))

        t, starts, ends = pace[0], [], []
        for d in durs:
            starts.append(round(t, 3))
            ends.append(round(t + d, 3))
            t += d + pace[1]
        timing.setdefault(sid, {})
        timing[sid].update({'sent_starts': starts, 'sent_ends': ends,
                            'durs': [round(d, 3) for d in durs],
                            'scene_len': round(got, 3), 'narration': lines})

    full = os.path.join(ab.out, 'narration_full.wav')
    ab.concat(scene_wavs, full)
    with open(timing_path, 'w', encoding='utf-8') as f:
        json.dump(timing, f, ensure_ascii=False, indent=1)

    print('%-14s %8s %8s %8s  lead  gap   tail' % ('scene', 'video', 'audio', 'diff'), flush=True)
    for sid, v, g, d, pace in report:
        print('%-14s %8.2f %8.2f %+8.2f  %.2f  %.2f  %.2f'
              % (sid, v, g, d, pace[0], pace[1], pace[2]), flush=True)
    total = probe_media(ff, full)['duration']
    print('\nnarration track %.2fs -> %s' % (total, full), flush=True)
    return full, timing


def main(argv):
    import yaml
    workdir = os.path.abspath(argv[0]) if argv else os.getcwd()
    with open(os.path.join(workdir, 'demorec.yaml'), encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    with open(os.path.join(workdir, 'scenes.yaml'), encoding='utf-8') as f:
        scenes = yaml.safe_load(f)['scenes']
    build(workdir, scenes, cfg)


if __name__ == '__main__':
    main(sys.argv[1:])
