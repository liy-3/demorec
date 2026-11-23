---
name: demorec
description: Record scripted software demo videos (screencast + AI narration + masking) driven entirely by YAML. Use when the user asks to record a product demo, walkthrough, or screen capture of a web application; to produce a narrated demo video; to mask or hide branding in a recording; or to maintain an existing demorec project. Not for editing existing video files or for general screen recording of the desktop.
---

# demorec — YAML-driven demo recording

Record a narrated product demo from three YAML files. No project Python is needed:
pages, scenes and pacing are all data. Changing a project means editing YAML, not code.

## When to load this

- The user wants a **demo video / walkthrough / screencast** of a web app.
- The user wants narration, pacing, or masking applied to a recording.
- The user wants to **maintain** an existing demorec project. Run `dry` before anything else.

Do **not** load this to edit an existing mp4, or to screen-capture a desktop app.

## Requirements (check first, they are the usual blocker)

```
python 3.11+        playwright  (browser automation)
                    pyyaml      (project files)
                    edge-tts    (narration)
                    mutagen     (mp3 duration)
ffmpeg on PATH      or set build.ffmpeg in demorec.yaml
Chrome / Chromium   playwright install chromium, or set browser_channel: chrome
```

Recording needs the site to be reachable from this machine. If it is not, stop
and tell the user: there is no offline mode.

## Project layout

```
<project>/
  demorec.yaml    # viewport, fps, voice, pacing, mask, ffmpeg, output name
  pages.yaml      # pages + SEMANTIC element names -> selectors
  scenes.yaml     # storyboard: narration lines + YAML steps
```

Start from `templates/` (see `templates/README.md`). Copy the three files and fill them in.

## Commands

```
python scripts/demorec.py lint   <project>          # static check, no browser needed
python scripts/demorec.py probe  <project> [page]   # suggest brand mask boxes
python scripts/demorec.py dry    <project>          # validate every selector, no recording
python scripts/demorec.py tts    <project>          # narration -> timing.json
python scripts/demorec.py record <project> [scene]  # record scenes
python scripts/demorec.py audio  <project>          # align narration to recordings
python scripts/demorec.py build  <project>          # mask + concat + mux -> out/
python scripts/demorec.py run    <project>          # all four in order
```

**Run `lint` first.** It needs no browser and takes milliseconds: it catches a
typo'd element name, a `say` index past the last line, an unknown step, or a
mask box outside the frame. Run `dry` next when the site is reachable.

**Always run `dry` before `record`.** It exercises the real click path, so a
broken selector fails in seconds instead of after a 10-minute recording.

## Authoring a scene

Narration is a list of lines; each step refers to a line by index:

```yaml
steps:
  - goto: home
  - start
  - click: {el: role_button, after: 1.1}   # el = name from pages.yaml
  - say: 0                                 # block until line 0 has finished
  - say: [2, 0.6]                          # ... plus 0.6s of breathing room
  - stop
```

`say: N` is what keeps a scene maintainable: when a line is rewritten, the
rhythm re-flows automatically. Never hard-code seconds that depend on speech.

Step vocabulary: `goto start stop say wait sleep move click hover type key scroll shot for_each`.
Targets: `{el: name}` (preferred) > `{sel: css}` > `{at: [x, y]}` (last resort).
See `references/steps.md` for every modifier.

Prefer `el` over `at`: absolute pixels break the moment a layout shifts, and they
are the main reason a second project feels like rewriting everything.

## Masking

Two mechanisms, both declared in `demorec.yaml`; the source site is never modified.

- `mask.boxes` — static rectangles painted opaque. Run `probe` to get candidates,
  then **confirm them on the screenshot**. An undersized box leaks the brand
  silently instead of failing loudly.
- `mask.hide_text` — keywords hidden at runtime by an injected script. Use this for
  watermarks that move with scrolling, which a fixed box cannot cover.

## Pitfalls (each one cost real debugging time)

`references/pitfalls.md` has the full list with symptoms. The three that matter most:

1. **Playwright sync API stalls the screencast under `time.sleep`.** CDP frame events
   are dispatched only while Playwright owns the event loop. All internal waits go
   through `Stage._tick()`; do not add `time.sleep()` to a stage method.
2. **Never concatenate mixed-format audio.** Mixing 24 kHz mono mp3 with 48 kHz stereo
   wav corrupts timestamps; scenes ended up ~6s instead of ~90s and the video was 30s
   out of sync. `audio.py` transcodes every clip to one format first.
3. **Mask fill must be fully opaque.** A `@0.97` alpha still shows the glyph outlines.

## Verify before delivering

1. Metadata: duration, `1920x1080`, 30 fps, aac stereo.
2. Extract 2-3 frames with `ffmpeg -ss T -frames:v 1` and **look at them**: mask covers
   the brand, no watermark, no browser chrome, no system UI.
3. Per-scene `video` vs `audio` duration from the `audio` step: keep the difference
   under ~0.05s per scene.

## Notes

- A scene without narration is fine; `tts` skips it, but then it cannot use `say`.
- The recording clock is real; a 9-minute demo takes ~15 minutes to record.
- Output naming comes from `build.output_name`; intermediate files stay in the project.
