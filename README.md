# demorec

[![ci](https://github.com/liy-3/demorec/actions/workflows/ci.yml/badge.svg)](https://github.com/liy-3/demorec/actions/workflows/ci.yml)

**YAML-driven demo recording**: scripted screencast + AI narration + masking, with no
project-specific Python. Change a project by editing YAML, not code.

Two ways to use it, one codebase:

- **Standalone CLI** — install the dependencies and run it directly. No agent
  framework required: `python scripts/demorec.py run <project>`.
- **Agent skill** — drop the directory into `~/.dsh/skills/demorec/` (or any skill
  directory that reads `SKILL.md`). `SKILL.md` tells an agent when to use it and
  what to check first. The CLI itself knows nothing about agents; the skill is
  only a description layer and does not change behaviour.

[中文说明](README.zh-CN.md)

## What it solves

Recording a narrated product demo by hand is mostly rework: re-record everything
after a script change, re-align narration to clicks, mask every frame that shows
a brand, then stitch it together. Move to the next project and the whole thing
starts over.

demorec turns it into **three YAML files and one command**:

```bash
python scripts/demorec.py dry <project>   # validate selectors, takes seconds
python scripts/demorec.py run <project>   # narration → record → align → render
```

## Design decisions

Each of these was measured, not assumed.

| Decision | Why |
|---|---|
| **Record the rendered frame over CDP**, not the desktop | The output is always the page at the configured viewport, so it does not depend on screen resolution, display scaling, window stacking, the taskbar, or the real mouse. A laptop with a smaller screen still produces 1080p. |
| **Scenes align with `say: N`**, not seconds | Rewrite a narration line and the scene rhythm re-flows on its own. Hard-coded `sleep` values drift out of sync, and you only notice it in the rendered file. |
| **Elements use semantic names** (`el`), not pixel coordinates | When the site is redesigned you edit `pages.yaml` only; the storyboard is untouched. Pixel targets are the main reason a second project feels like starting from scratch. |
| **Audio is normalised before concatenation** | Concatenating mixed formats (24 kHz mono mp3 + 48 kHz stereo wav) corrupts timestamps: each scene was cut to ~6 s of a ~90 s recording and the finished video was 30 s out of sync. |
| **Masking happens at render time** | The source site is never modified. Scrolling watermarks use runtime text hiding instead, because a fixed box cannot follow them. |

## Layout

```
demorec/
  SKILL.md              # instructions an agent reads
  scripts/              # the pipeline; project-agnostic
    demorec.py          # CLI entry point
    stage.py            # CDP screencast + synthetic cursor
    run.py              # YAML step interpreter
    tts.py              # narration → timing.json
    audio.py            # align narration to each scene's recording
    build.py            # mask + concatenate + mux
    probe_brand.py      # suggest brand-mask boxes
  templates/            # starter project, copy and fill in
  references/           # steps.md / pitfalls.md
  examples/todomvc/     # two-scene public example (Playwright TodoMVC), runs as-is
```

## Standalone use

```bash
git clone https://github.com/liy-3/demorec.git
cd demorec
python -m pip install -r requirements.txt
playwright install chromium        # or use a local Chrome: set browser_channel: chrome

cp -r templates my-demo            # start from the skeleton
# edit the three YAML files under my-demo, then:
python scripts/demorec.py dry my-demo    # validate selectors first
python scripts/demorec.py run my-demo    # narration → record → align → render
```

## Requirements

```
python 3.11+     playwright  pyyaml  edge-tts  mutagen
ffmpeg           on PATH, or set build.ffmpeg in demorec.yaml
Chrome/Chromium  playwright install chromium
```

`playwright install chromium` is optional if a local Chrome is present and
`browser_channel: chrome` is set. Recording requires network access to the target
site — there is no offline mode.

## Tests

63 tests, ~0.7 s, **no browser and no ffmpeg required**:

```bash
python -m pip install pytest pyyaml
python -m pytest tests/ -q
```

| File | Count | Coverage |
|---|---|---|
| `test_lint.py` | 21 | static validation: misspelled element names, `say` out of range, unknown steps, mask boxes outside the frame, duplicate ids |
| `test_run.py` | 16 | step interpreter: bare-word steps, modifier defaults, `for_each` substitution |
| `test_build.py` | 11 | filter-graph generation (including the empty-mask case), ffmpeg discovery, cursor-script contract |
| `test_integration.py` | 11 | timing-table contract, `say` boundaries, **wall clock rather than frame clock** (the frozen-frame regression), CLI scene selection |
| `test_audio.py` | 4 | track-duration alignment: pad the tail when narration is short, tighten gaps when it overruns |

CI runs the same suite on Ubuntu and Windows with Python 3.11 and 3.12, plus
`demorec.py lint examples/todomvc` and `compileall`.

**The suite deliberately avoids Playwright and ffmpeg.** Two guard tests assert
this via AST inspection, so a browser import cannot quietly move to module level
and break CI months later.

## Adapting it to a new project

1. `demorec.yaml` — site root, viewport, voice, mask regions
2. `pages.yaml` — page URLs plus semantic element names (most of the work)
3. `scenes.yaml` — narration and storyboard steps

**No Python required.** `examples/todomvc/` is exactly this: a YAML-only project
that `demorec.py run` renders end to end, for comparison.

## Known limitations

- The target site must be reachable; there is no offline mode.
- Recording runs in real time: a 9-minute demo takes roughly 15 minutes.
- Mask-box probing only suggests candidates — **confirm them on a screenshot**.
  An undersized box leaks the brand silently instead of failing loudly.
- Web pages only. Desktop application capture is out of scope.
- There is no editor. Some comparable tools offer a timeline you can trim, zoom
  and caption in; demorec is one-shot, so a late zoom request means editing the
  script and re-recording that scene.

Details in `SKILL.md`; traps in `references/pitfalls.md`.
