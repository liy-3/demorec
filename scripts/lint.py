# -*- coding: utf-8 -*-
"""demorec lint — static project validation. No browser, no ffmpeg.

`dry` proves a project really works, but it needs the site to be up and takes
minutes. `lint` catches the mistakes that cause most of that loop instead:
typo'd element names, a `say` index past the last narration line, a step that
is not in the vocabulary, a mask box outside the frame.

Exit code: 0 clean, 1 errors found. Warnings never fail the run.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Keep in sync with run.StepRunner.step()
STEP_OPS = {'goto', 'start', 'stop', 'say', 'wait', 'sleep', 'move', 'click',
            'hover', 'type', 'key', 'scroll', 'shot', 'for_each'}
TARGET_OPS = {'move', 'click', 'hover'}
NOARG_OPS = {'start', 'stop'}


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, where, msg):
        self.errors.append('%s: %s' % (where, msg))

    def warn(self, where, msg):
        self.warnings.append('%s: %s' % (where, msg))

    def dump(self):
        for w in self.warnings:
            print('warn  ' + w, flush=True)
        for e in self.errors:
            print('ERROR ' + e, flush=True)
        print('\n%d error(s), %d warning(s)' % (len(self.errors), len(self.warnings)), flush=True)
        return 0 if not self.errors else 1


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_config(cfg, rep):
    if not isinstance(cfg, dict):
        rep.err('demorec.yaml', 'top level must be a mapping')
        return
    vp = cfg.get('viewport', [1920, 1080])
    if not (isinstance(vp, list) and len(vp) == 2 and all(isinstance(x, int) and x > 0 for x in vp)):
        rep.err('demorec.yaml', 'viewport must be [width, height] integers, got %r' % (vp,))
    else:
        w, h = vp
        for i, b in enumerate((cfg.get('mask', {}) or {}).get('boxes') or []):
            if not (isinstance(b, list) and len(b) == 4 and all(_is_num(x) for x in b)):
                rep.err('demorec.yaml', 'mask.boxes[%d] must be [x, y, w, h], got %r' % (i, b))
                continue
            x, y, bw, bh = b
            if bw <= 0 or bh <= 0:
                rep.err('demorec.yaml', 'mask.boxes[%d] has non-positive size %r' % (i, b))
            if x < 0 or y < 0 or x + bw > w or y + bh > h:
                rep.err('demorec.yaml', 'mask.boxes[%d] %r falls outside the %dx%d frame'
                        % (i, b, w, h))
    fps = cfg.get('fps', 30)
    if not _is_num(fps) or not (1 <= fps <= 60):
        rep.err('demorec.yaml', 'fps must be between 1 and 60, got %r' % (fps,))
    if not (cfg.get('root_url') or '').strip():
        rep.warn('demorec.yaml', 'root_url is empty; every page url must then be absolute')
    out = (cfg.get('build') or {}).get('output_name')
    if out is not None and (not isinstance(out, str) or not out.strip()):
        rep.err('demorec.yaml', 'build.output_name must be a non-empty string')


def check_pages(pages, rep):
    if not isinstance(pages, dict) or not pages:
        rep.err('pages.yaml', 'must contain a non-empty "pages" mapping')
        return {}
    names = set()
    for name, page in pages.items():
        if not isinstance(page, dict):
            rep.err('pages.yaml', 'page "%s" must be a mapping' % name)
            continue
        url = page.get('url')
        if not isinstance(url, str):
            rep.err('pages.yaml', 'page "%s" needs a string url' % name)
        els = page.get('elements') or {}
        if not isinstance(els, dict):
            rep.err('pages.yaml', 'page "%s" elements must be a mapping' % name)
            els = {}
        for en, sel in els.items():
            if isinstance(sel, str):
                if not sel.strip():
                    rep.err('pages.yaml', 'element "%s.%s" is an empty selector' % (name, en))
            elif isinstance(sel, list):
                if not sel or not all(isinstance(x, str) and x.strip() for x in sel):
                    rep.err('pages.yaml', 'element "%s.%s" list must hold non-empty strings' % (name, en))
            else:
                rep.err('pages.yaml', 'element "%s.%s" must be a string or a list of strings'
                        % (name, en))
        names.add(name)
    return names


def _check_target(where, target, page_elements, page_name, rep, seen_at):
    if isinstance(target, str):
        rep.warn(where, 'bare string target %r - use {el: name}, {sel: css} or {at: [x, y]}' % target)
        return
    if isinstance(target, list):
        if not (len(target) == 2 and all(_is_num(x) for x in target)):
            rep.err(where, 'positional target must be [x, y], got %r' % (target,))
        else:
            seen_at[0] += 1
        return
    if not isinstance(target, dict):
        rep.err(where, 'target must be a mapping, got %r' % (target,))
        return
    keys = [k for k in ('el', 'sel', 'at') if k in target]
    if len(keys) != 1:
        rep.err(where, 'target needs exactly one of el/sel/at, got %r' % (target,))
        return
    key = keys[0]
    if key == 'at':
        v = target['at']
        if not (isinstance(v, list) and len(v) == 2 and all(_is_num(x) for x in v)):
            rep.err(where, 'at must be [x, y], got %r' % (v,))
        else:
            seen_at[0] += 1
    elif key == 'sel':
        if not isinstance(target['sel'], str) or not target['sel'].strip():
            rep.err(where, 'sel must be a non-empty string')
    else:
        en = target['el']
        if not isinstance(en, str):
            rep.err(where, 'el must be a string')
            return
        if page_name is None:
            rep.err(where, 'el "%s" used but the scene declares no page' % en)
        elif page_name not in page_elements:
            pass
        elif en not in page_elements[page_name]:
            rep.err(where, 'element "%s" is not defined for page "%s"' % (en, page_name))


def check_steps(where, steps, scene, page_names, page_elements, rep, seen_at, depth=0):
    if depth > 4:
        rep.err(where, 'for_each nested too deeply')
        return
    if not isinstance(steps, list):
        rep.err(where, 'steps must be a list')
        return
    narration = scene.get('narration') or []
    nlines = len(narration)

    for i, st in enumerate(steps):
        at_where = '%s step %d' % (where, i)
        if isinstance(st, str):
            op = st.strip()
            if op not in STEP_OPS:
                rep.err(at_where, 'unknown step %r' % op)
            elif op not in NOARG_OPS:
                rep.err(at_where, 'step %r needs an argument (write it as a mapping)' % op)
            continue
        if not isinstance(st, dict) or not st:
            rep.err(at_where, 'step must be a mapping or a bare word, got %r' % (st,))
            continue
        op = next(iter(st))
        arg = st[op]
        if op not in STEP_OPS:
            rep.err(at_where, 'unknown step %r (known: %s)' % (op, ', '.join(sorted(STEP_OPS))))
            continue

        if op == 'goto':
            if arg not in page_names:
                rep.err(at_where, 'goto refers to unknown page %r' % (arg,))
        elif op == 'say':
            idx = arg[0] if isinstance(arg, list) else arg
            if not isinstance(idx, int) or isinstance(idx, bool):
                rep.err(at_where, 'say index must be an integer, got %r' % (idx,))
            elif nlines == 0:
                rep.err(at_where, 'say used but the scene has no narration')
            elif idx < 0 or idx >= nlines:
                rep.err(at_where, 'say %d out of range - scene has %d narration line(s)'
                        % (idx, nlines))
        elif op in ('wait', 'sleep', 'scroll'):
            if not _is_num(arg):
                rep.err(at_where, '%s needs a number, got %r' % (op, arg))
        elif op in TARGET_OPS:
            _check_target(at_where, arg, page_elements, scene.get('page'), rep, seen_at)
        elif op == 'type':
            if not isinstance(arg, str):
                rep.err(at_where, 'type needs a string')
        elif op == 'key':
            if not isinstance(arg, str) or not arg.strip():
                rep.err(at_where, 'key needs a non-empty string')
        elif op == 'for_each':
            if not isinstance(arg, dict) or 'over' not in arg or 'do' not in arg:
                rep.err(at_where, 'for_each needs {over: [...], do: [...]}')
            else:
                if not isinstance(arg['over'], list):
                    rep.err(at_where, 'for_each.over must be a list')
                check_steps(at_where + ' > do', arg['do'], scene, page_names,
                            page_elements, rep, seen_at, depth + 1)


def check_scenes(scenes, page_names, page_elements, rep):
    if not isinstance(scenes, list) or not scenes:
        rep.err('scenes.yaml', 'must contain a non-empty "scenes" list')
        return
    seen_ids = set()
    seen_at = [0]
    for i, sc in enumerate(scenes):
        where = 'scenes.yaml scene %d' % i
        if not isinstance(sc, dict):
            rep.err(where, 'scene must be a mapping')
            continue
        sid = sc.get('id')
        if not isinstance(sid, str) or not sid.strip():
            rep.err(where, 'scene needs a non-empty string id')
            sid = '?%d' % i
        else:
            where = 'scene "%s"' % sid
            if sid in seen_ids:
                rep.err(where, 'duplicate scene id')
            seen_ids.add(sid)
            if not all(c.isalnum() or c in '-_' for c in sid):
                rep.err(where, 'id should be file-name safe (letters, digits, - and _)')
        page = sc.get('page')
        if page is None:
            rep.err(where, 'scene needs a "page"')
        elif page not in page_names:
            rep.err(where, 'page %r is not defined in pages.yaml' % (page,))
        narr = sc.get('narration')
        if narr is not None:
            if not isinstance(narr, list) or not all(isinstance(x, str) for x in narr):
                rep.err(where, 'narration must be a list of strings')
            elif not narr:
                rep.warn(where, 'empty narration - the scene cannot use say, and will be silent')
        steps = sc.get('steps')
        if not isinstance(steps, list) or not steps:
            rep.err(where, 'steps must be a non-empty list')
            continue
        check_steps(where, steps, sc, page_names, page_elements, rep, seen_at)
        ops = [(s.strip() if isinstance(s, str) else next(iter(s), '')) for s in steps
               if isinstance(s, (str, dict))]
        if 'start' not in ops:
            rep.warn(where, 'no "start" step - nothing will be recorded for this scene')
        if 'stop' not in ops:
            rep.warn(where, 'no "stop" step - the recording will not be finalized')
    if seen_at[0]:
        rep.warn('scenes.yaml', '%d absolute-pixel target(s) in use; each one breaks when'
                 ' the layout shifts - prefer {el: name}' % seen_at[0])


def lint(project_dir):
    import yaml
    rep = Report()
    project_dir = os.path.abspath(project_dir)

    loaded = {}
    for fname in ('demorec.yaml', 'pages.yaml', 'scenes.yaml'):
        path = os.path.join(project_dir, fname)
        if not os.path.exists(path):
            rep.err(fname, 'missing (a demorec project needs all three files)')
            continue
        try:
            with open(path, encoding='utf-8') as f:
                loaded[fname] = yaml.safe_load(f)
        except Exception as e:
            rep.err(fname, 'not valid YAML: %s' % str(e)[:200])

    cfg = loaded.get('demorec.yaml')
    if isinstance(cfg, dict):
        check_config(cfg, rep)

    pages_doc = loaded.get('pages.yaml')
    pages = (pages_doc or {}).get('pages') if isinstance(pages_doc, dict) else None
    page_names = check_pages(pages, rep) if pages is not None else set()
    page_elements = {n: (pages[n].get('elements') or {}) for n in page_names
                     if isinstance(pages.get(n), dict)}

    scenes_doc = loaded.get('scenes.yaml')
    scenes = (scenes_doc or {}).get('scenes') if isinstance(scenes_doc, dict) else None
    if scenes is not None:
        check_scenes(scenes, page_names, page_elements, rep)

    return rep


def main(argv):
    project = argv[0] if argv else '.'
    rep = lint(project)
    print('lint %s' % os.path.abspath(project), flush=True)
    return rep.dump()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
