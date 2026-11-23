# -*- coding: utf-8 -*-
"""demorec runner — interprets scenes.yaml and drives a Stage.

The whole point of this module is that a project never writes Python:
a scene is a list of YAML steps, and this file is the only interpreter.

Step vocabulary (every step is a one-key mapping, plus optional modifiers):

    - goto: home                 # open a page defined in pages.yaml
    - start                      # begin CDP recording
    - stop                       # stop recording and encode the mp4
    - say: 0                     # block until narration line 0 has finished
    - say: [0, 0.4]              # ... plus 0.4s of breathing room
    - wait: 12.5                 # block until t=12.5s of the recording
    - sleep: 1.2                 # block for 1.2s of wall/recording time
    - move:  {el: role_button}   # glide the synthetic cursor there
    - click: {el: role_button}
    - hover: {sel: ".card"}
    - type: "some text"          # human-paced typing into the focused field
    - key: Enter
    - scroll: 420                # smooth wheel scroll
    - shot: after_switch         # save a PNG for manual review

Targets accept exactly one of:
    {el: <name>}   named selector from pages.yaml   (preferred: semantic,
                                                     survives layout changes)
    {sel: <css>}   raw CSS / Playwright selector     (escape hatch)
    {at: [x, y]}   absolute pixel in the video frame (last resort)

Modifiers: hover, after, dur, steps, cps, settle — see StepRunner.
"""
import os, sys, json, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from stage import Stage, find_ffmpeg, probe_media  # noqa: E402


class StepRunner:
    def __init__(self, stage, dry=False):
        self.s = stage
        self.dry = dry

    def run(self, steps):
        for i, step in enumerate(steps):
            try:
                self.step(step)
            except Exception:
                print('!! step %d failed: %r' % (i, step), flush=True)
                raise
        return self

    def step(self, step):
        # 裸写的 - start / - stop 在 YAML 里是字符串，等价于无参步骤。
        if isinstance(step, str):
            step = {step.strip(): None}
        if not isinstance(step, dict) or len(step) < 1:
            raise ValueError('bad step: %r' % (step,))
        op = next(iter(step))
        arg = step[op]
        rest = {k: v for k, v in step.items() if k != op}

        if op == 'goto':
            # dry 模式也真实导航：否则页面停在空白页，选择器一个都验不到。
            print('  goto %s' % arg, flush=True)
            self.s.goto(self.s.pages[arg])
            return
        if op == 'start':
            print('  start recording %s' % self.s.scene, flush=True)
            if not self.dry:
                self.s.start()
            return
        if op == 'stop':
            if self.dry:
                return
            self.s.stop()
            return
        if op == 'say':
            if arg is None:
                raise ValueError('say needs an index, e.g. - say: 0 or - say: [0, 0.4]')
            idx, extra = (arg, 0.0) if not isinstance(arg, list) else (arg[0], arg[1] if len(arg) > 1 else 0.0)
            extra = rest.get('extra', extra)
            if self.dry:
                return
            self.s.say(int(idx), float(extra))
            return
        if op == 'wait':
            if self.dry:
                return
            self.s.wait_until(float(arg))
            return
        if op == 'sleep':
            if self.dry:
                return
            self.s.sleep(float(rest.get('seconds', arg)))
            return
        if op == 'move':
            x, y = self.s.resolve(arg)
            if self.dry:
                print('    move -> %r' % ((round(x), round(y)),), flush=True)
                return
            self.s.move(x, y, dur=float(rest.get('dur', 0.55)))
            return
        if op == 'click':
            # dry 模式真实点击：UI 状态必须推进，后面步骤的选择器才验得到。
            x, y = self.s.resolve(arg)
            if self.dry:
                print('    click -> %r' % ((round(x), round(y)),), flush=True)
            self.s.click_at(x, y,
                            hover=float(rest.get('hover', 0.35)),
                            after=float(rest.get('after', 0.6)),
                            dur=float(rest.get('dur', 0.55)))
            return
        if op == 'hover':
            x, y = self.s.resolve(arg)
            if self.dry:
                print('    hover -> %r' % ((round(x), round(y)),), flush=True)
                return
            self.s.move(x, y, dur=float(rest.get('dur', 0.55)))
            self.s.sleep(float(rest.get('hold', 0.9)))
            return
        if op == 'type':
            if self.dry:
                print('    type %r' % str(arg)[:40], flush=True)
            self.s.type_text(str(arg), cps=float(rest.get('cps', 6.0)))
            return
        if op == 'key':
            if self.dry:
                print('    key %s' % arg, flush=True)
            self.s.key(str(arg))
            return
        if op == 'scroll':
            if self.dry:
                print('    scroll %s' % arg, flush=True)
                return
            self.s.scroll(float(arg),
                          steps=int(rest.get('steps', 16)),
                          settle=float(rest.get('settle', 0.25)))
            return
        if op == 'shot':
            if self.dry:
                return
            self.s.shot(str(arg))
            return
        if op == 'for_each':
            over = arg.get('over', [])
            body = arg.get('do', [])
            for item in over:
                for sub in body:
                    sub2 = dict(sub)
                    op2 = next(iter(sub2))
                    if isinstance(sub2[op2], dict) and 'at' in sub2[op2]:
                        sub2[op2] = {'at': item} if isinstance(item, list) else {**sub2[op2], 'at': item}
                    self.step(sub2)
            return
        raise ValueError('unknown step "%s" (supported: goto, start, stop, say, wait, '
                         'sleep, move, click, hover, type, key, scroll, shot, for_each)' % op)



def run_scene(workdir, scene, cfg, pages, dry=False, elements=None):
    cfg = dict(cfg)
    timing_path = os.path.join(workdir, 'timing.json')
    cfg['_timing'] = json.load(open(timing_path, encoding='utf-8')) if os.path.exists(timing_path) else {}

    sid = scene['id']
    els = dict(pages.get(scene.get('page'), {}).get('elements', {}))
    if scene.get('elements'):
        els.update(scene['elements'])

    print('=' * 64, flush=True)
    print('SCENE %s  %s%s' % (sid, scene.get('title', ''), '  (dry)' if dry else ''), flush=True)
    t0 = time.time()
    root = (cfg.get('root_url') or '').strip()
    with Stage(workdir, sid, cfg, elements=els) as stage:
        # url 支持相对路径（拼 root_url）与绝对地址两种写法
        stage.pages = {name: (p['url'] if str(p['url']).startswith(('http://', 'https://'))
                              else root.rstrip('/') + '/' + str(p['url']).lstrip('/'))
                       for name, p in pages.items()}
        StepRunner(stage, dry=dry).run(scene.get('steps', []))
    print('done %s in %.1fs' % (sid, time.time() - t0), flush=True)
    return os.path.join(workdir, 'rec', sid + '.mp4')


def main(argv):
    import yaml
    args = [a for a in argv if not a.startswith('--')]
    dry = '--dry' in argv
    workdir = os.path.abspath(args[0]) if args else os.getcwd()
    only = args[1:] if len(args) > 1 else None

    cfg_path = os.path.join(workdir, 'demorec.yaml')
    with open(cfg_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    with open(os.path.join(workdir, 'pages.yaml'), encoding='utf-8') as f:
        pages = yaml.safe_load(f)['pages']
    with open(os.path.join(workdir, 'scenes.yaml'), encoding='utf-8') as f:
        scenes = yaml.safe_load(f)['scenes']

    ids = [s['id'] for s in scenes]
    todo = [s for s in scenes if not only or s['id'] in only or '--all' in argv]
    if not todo:
        raise SystemExit('no matching scenes; available: %s' % ', '.join(ids))

    done = []
    for scene in todo:
        try:
            done.append(run_scene(workdir, scene, cfg, pages, dry=dry))
        except Exception:
            traceback.print_exc()
            print('!! scene %s FAILED' % scene['id'], flush=True)
            break
    print(json.dumps([os.path.basename(p) for p in done], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
