# -*- coding: utf-8 -*-
"""demorec — record scripted software demos from YAML, no project Python needed.

    python scripts/demorec.py lint    <project>            # static check, no browser needed
    python scripts/demorec.py probe   <project>            # suggest brand mask boxes
    python scripts/demorec.py dry     <project> [scene...] # validate selectors, no recording
    python scripts/demorec.py tts     <project> [--force]  # synthesize narration -> timing.json
    python scripts/demorec.py record  <project> [scene...] # record scenes (--all for every scene)
    python scripts/demorec.py audio   <project>            # align narration to recordings
    python scripts/demorec.py build   <project>            # mask + concat + mux -> deliverable
    python scripts/demorec.py run     <project>            # tts -> record -> audio -> build

A project is any directory containing demorec.yaml, pages.yaml and scenes.yaml.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

USAGE = __doc__


def load_project(project_dir):
    import yaml
    project_dir = os.path.abspath(project_dir)
    required = ['demorec.yaml', 'pages.yaml', 'scenes.yaml']
    missing = [f for f in required if not os.path.exists(os.path.join(project_dir, f))]
    if missing:
        raise SystemExit('%s is not a demorec project (missing: %s)'
                         % (project_dir, ', '.join(missing)))
    with open(os.path.join(project_dir, 'demorec.yaml'), encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    with open(os.path.join(project_dir, 'scenes.yaml'), encoding='utf-8') as f:
        scenes = yaml.safe_load(f)['scenes']
    return project_dir, cfg, scenes


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(USAGE)
        return 0
    cmd, project = argv[0], (argv[1] if len(argv) > 1 else '.')
    rest = argv[2:]

    if cmd == 'lint':
        import lint
        return lint.main([project] + rest)

    if cmd == 'probe':
        import probe_brand
        return probe_brand.main([project] + rest)

    if cmd == 'dry':
        import run
        return run.main([project, '--dry', '--all'] + rest)

    if cmd == 'tts':
        import tts
        return tts.main([project] + rest)

    if cmd == 'record':
        import run
        return run.main([project, '--all'] + rest)

    if cmd == 'audio':
        import audio
        return audio.main([project] + rest)

    if cmd == 'build':
        import build
        return build.main([project] + rest)

    if cmd == 'run':
        import tts, run, audio, build
        p, cfg, scenes = load_project(project)
        import lint
        rep = lint.lint(p)
        if rep.errors:
            rep.dump()
            raise SystemExit('lint failed - fix the errors above before recording')
        print('=== 1/4 narration', flush=True)
        tts.main([p])
        print('=== 2/4 record', flush=True)
        run.main([p, '--all'] + ([r for r in rest if not r.startswith('-')] or []))
        print('=== 3/4 audio', flush=True)
        audio.main([p])
        print('=== 4/4 build', flush=True)
        build.main([p])
        return 0

    raise SystemExit('unknown command "%s"\n\n%s' % (cmd, USAGE))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]) or 0)
