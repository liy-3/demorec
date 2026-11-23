# Pitfall list

Each entry leads with the symptom, so you can start from what you are seeing.

## 1. No frames after a few seconds of recording

**Symptom**: `[rec] ... frames=0`, or `screencast produced no frames`.

**Cause**: the Playwright **sync** API dispatches CDP events only while it is
driving the event loop. A `time.sleep()` inside a scene stalls
`Page.screencastFrame` completely.

**Fix**: every wait goes through `Stage._tick()` / `wait_until()` / `sleep()`,
which call `page.wait_for_timeout` internally. Never add a bare `time.sleep` to a
stage method.

## 2. Picture and narration drift apart

**Symptom**: video 520 s, audio track 491 s, and the gap grows towards the end.

**Cause**: concatenating **mixed-format** audio with the ffmpeg concat demuxer
(24 kHz mono mp3 next to 48 kHz stereo wav) corrupts timestamps; each scene track
was cut to about 6 s.

**Fix**: `scripts/audio.py` transcodes every clip to a uniform 48 kHz stereo wav
before concatenating, then forces each scene track to the recorded video length
(padding the tail, or tightening the gaps between lines).

## 3. The mask still shows the glyph outlines underneath

**Symptom**: the box covers the area, but the text is faintly legible.

**Cause**: the fill colour carries alpha (e.g. `0xEEF2FA@0.97`).

**Fix**: `t=fill` and a colour with no transparency. Prefer a few pixels of
overshoot to an exact fit.

## 4. A footer watermark sits somewhere different in every frame

**Symptom**: a fixed mask box covers it in some frames and not others.

**Cause**: the watermark moves with the scrolling content.

**Fix**: hide it at runtime with `mask.hide_text` (an injected script matches text
nodes by keyword). A fixed coordinate cannot work.

## 5. A panel renders empty after you click into it

**Symptom**: you switch to a tab and the frame is blank, while the narration talks
about content that should be there.

**Cause**: such panels start empty by design and render only after they are told
to load — a "generate", "import" or "run" control has to be triggered first.

**Fix**: put the triggering click in the storyboard. After `dry`, extract a frame
and look at it; do not rely on selectors merely resolving.

## 6. A generated answer comes back as "not enough information"

**Symptom**: the demo asks a system a question and it answers that it cannot
confirm anything from the available material.

**Cause**: retrieval over a knowledge base has a hit rate; plenty of natural
phrasings find nothing.

**Fix**: try candidate questions before recording and pick one that produces a
substantive answer, ideally with a number or a concrete value in it. Do not record
a question whose answer you have not seen.

## 7. `dry` passed but the real recording fails

**Symptom**: the dry run completes, then a step times out during recording.

**Cause**: usually animation or loading timing, or the element not being visible
at the scroll position the recording reaches.

**Fix**: `dry` already clicks through for real. If a step is still flaky, add
`after` to that step, or insert a `scroll` before it to bring the target into view.

## 8. Browser chrome, address bar or taskbar in the frame

**Symptom**: system UI around the edge of the output.

**Cause**: desktop capture (gdigrab, OBS display capture).

**Fix**: this tool captures rendered frames over CDP, so those never appear. If
you switch to desktop capture, crop to the page area and account for display
scaling (window size and CSS pixels diverge under high DPI).

## 9. A static page hangs the recording clock

**Symptom**: `wait_until()` never returns and the recording stalls, typically on a
page with no animation and no ticking clock.

**Cause**: CDP screencast only emits frames when the picture changes. On a still
page the frames stop, so the timestamp of the last frame freezes — and progress
measured from frame timestamps can never reach the target time.

**Fix**: recording progress is measured on the **wall clock** (`Stage.elapsed()`,
corrected by `frame_offset` once at startup). Frame spacing still uses the browser
clock, because only its relative deltas are accurate. A page that repaints its
clock every second never exposes this; a static page fails immediately.

## 10. The finished video is shorter than the recording

**Symptom**: `recorded=120.4s` but `video=117.9s`, and the mismatch warning fires
on stop.

**Cause**: the tail of a scene is static, so no frames arrive after the last
change and the final frame would otherwise end early.

**Fix**: this is handled — `stop()` records `stop_offset` and extends the last
frame's duration to the real end. A warning means the gap exceeds 0.5 s, so look
for genuinely idle time or a scene that never reached `stop`.
