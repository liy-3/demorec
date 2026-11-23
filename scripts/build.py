# -*- coding: utf-8 -*-
"""demorec build — mask, concatenate, mux narration, emit the deliverable.

Masking happens after recording, on the video, because the source site is
never modified. Two mechanisms, both declared in demorec.yaml:

  mask.boxes      static rectangles painted opaque over the frame.
                  The fill MUST be fully opaque: a 97%-alpha box still shows
                  the glyph outlines underneath.
  mask.hide_text  keyword list hidden at runtime by an injected script.
                  Use this for watermarks that move with scrolling, which a
                  fixed box cannot cover.
"""
import os, sys, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from stage import find_ffmpeg, probe_media  # noqa: E402


def run(ff, args, **kw):
    pr = subprocess.run([ff, '-y', '-hide_banner', '-loglevel', 'error'] + list(args),
                        capture_output=True, text=True, errors='ignore', **kw)
    if pr.returncode != 0:
        raise RuntimeError('ffmpeg failed: %s' % (pr.stderr or '')[:500])
    return pr


def mask_filter(boxes, color):
    # 即使没有打码框也必须产出一个 [out] 标签，否则 -map [out] 找不到输出。
    if not boxes:
        return '[0:v]format=yuv420p[out]'
    parts, cur = [], '[0:v]'
    for i, b in enumerate(boxes):
        x, y, w, h = b
        parts.append('%sdrawbox=x=%d:y=%d:w=%d:h=%d:color=%s:t=fill[vm%d]'
                     % (cur, x, y, w, h, color, i))
        cur = '[vm%d]' % i
    parts.append('%sformat=yuv420p[out]' % cur)
    return ';'.join(parts)


def main(argv):
    import yaml
    workdir = os.path.abspath(argv[0]) if argv else os.getcwd()
    with open(os.path.join(workdir, 'demorec.yaml'), encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    with open(os.path.join(workdir, 'scenes.yaml'), encoding='utf-8') as f:
        scenes = yaml.safe_load(f)['scenes']

    bcfg = cfg.get('build', {})
    ff = find_ffmpeg(bcfg.get('ffmpeg'))
    rec_dir = os.path.join(workdir, 'rec')
    out_dir = os.path.join(workdir, 'out')
    os.makedirs(out_dir, exist_ok=True)

    boxes = cfg.get('mask', {}).get('boxes') or []
    color = cfg.get('mask', {}).get('color', '0xEEF2FA')
    crf = str(bcfg.get('crf', 17))
    preset = bcfg.get('preset', 'medium')
    audio_bitrate = bcfg.get('audio_bitrate', '192k')
    name = bcfg.get('output_name', 'demo.mp4')

    masked = []
    for sc in scenes:
        sid = sc['id']
        src = os.path.join(rec_dir, sid + '.mp4')
        if not os.path.exists(src):
            raise SystemExit('missing recording: %s (run the recorder first)' % src)
        dst = os.path.join(out_dir, 'masked_' + sid + '.mp4')
        run(ff, ['-i', src, '-filter_complex', mask_filter(boxes, color),
                 '-map', '[out]', '-c:v', 'libx264', '-preset', preset,
                 '-crf', crf, '-an', '-movflags', '+faststart', dst])
        masked.append(dst)
        print('  masked %-14s %s' % (sid, probe_media(ff, dst)['duration']), flush=True)

    lst = os.path.join(out_dir, 'concat_scenes.txt')
    with open(lst, 'w', encoding='utf-8') as f:
        for p in masked:
            f.write("file '%s'\n" % p.replace('\\', '/'))
    full = os.path.join(out_dir, 'full_masked.mp4')
    run(ff, ['-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy',
             '-movflags', '+faststart', full])

    narration = os.path.join(out_dir, 'narration_full.wav')
    if not os.path.exists(narration):
        raise SystemExit('missing narration track %s (run audio first)' % narration)

    final = os.path.join(out_dir, name)
    run(ff, ['-i', full, '-i', narration, '-map', '0:v:0', '-map', '1:a:0',
             '-c:v', 'copy', '-c:a', 'aac', '-b:a', audio_bitrate,
             '-ar', '48000', '-ac', '2', '-movflags', '+faststart',
             '-shortest', final])

    info = probe_media(ff, final)
    print('\ndeliverable: %s' % final, flush=True)
    print('  %.1fs  %s  %.1fMB' % (info['duration'] or 0, info.get('resolution', '?'),
                                    info['size'] / 1024 / 1024), flush=True)
    return final


if __name__ == '__main__':
    main(sys.argv[1:])
