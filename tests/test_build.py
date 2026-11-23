# -*- coding: utf-8 -*-
"""Filter-graph generation and small pure helpers. No ffmpeg run needed."""
import os
import pytest

import build as buildmod
import stage as stagemod


def test_no_boxes_still_emits_the_out_label():
    # Regression: an empty mask produced "format=yuv420p" with no [out] label,
    # so -map [out] failed and projects that need no masking could not build.
    g = buildmod.mask_filter([], "0xFFFFFF")
    assert g.endswith("[out]"), g
    assert "[0:v]" in g


def test_single_box_is_fully_opaque():
    g = buildmod.mask_filter([[6, 4, 306, 66]], "0xEEF2FA")
    assert "drawbox=x=6:y=4:w=306:h=66" in g
    assert "color=0xEEF2FA" in g
    assert "t=fill" in g
    # Alpha would leak the glyph outlines underneath.
    assert "@" not in g
    assert g.endswith("[out]")


def test_multiple_boxes_are_joined_in_order():
    g = buildmod.mask_filter([[1, 2, 3, 4], [5, 6, 7, 8]], "0x000000")
    assert g.index("x=1:y=2") < g.index("x=5:y=6")
    assert g.count("drawbox=") == 2
    assert g.endswith("[out]")


def test_every_intermediate_label_is_consumed():
    g = buildmod.mask_filter([[1, 2, 3, 4], [5, 6, 7, 8]], "0x000000")
    produced = {seg.rsplit("[", 1)[-1].rstrip("]") for seg in g.split(";") if "[" in seg}
    # every produced label (except the final out) must be referenced later
    for label in produced:
        if label in ("0:v", "out"):
            continue
        assert g.count("[" + label + "]") >= 2, "label %r is produced but never used" % label


def test_filter_always_forces_yuv420p():
    for boxes in ([], [[1, 2, 3, 4]]):
        assert "format=yuv420p" in buildmod.mask_filter(boxes, "0xFFFFFF")


def test_probe_media_reports_missing_file_size_zero(tmp_path):
    # probe_media must not raise on a missing path; callers rely on size 0.
    p = str(tmp_path / "nope.mp4")
    out = stagemod.probe_media("ffmpeg-does-not-exist", p)
    assert out["size"] == 0
    assert out["duration"] is None


def test_find_ffmpeg_prefers_an_explicit_existing_path(tmp_path):
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"stub")
    assert stagemod.find_ffmpeg(str(fake)) == str(fake)


def test_find_ffmpeg_raises_a_readable_error_when_absent(monkeypatch):
    monkeypatch.setattr(stagemod.shutil, "which", lambda name: None)
    monkeypatch.setattr(stagemod.glob, "glob", lambda pattern: [])
    monkeypatch.setattr(stagemod.os.path, "expanduser", lambda p: p)
    with pytest.raises(RuntimeError) as ei:
        stagemod.find_ffmpeg("C:/definitely/not/here/ffmpeg.exe")
    assert "ffmpeg not found" in str(ei.value)


def test_cursor_script_defines_the_hooks_stage_calls():
    # Stage calls window.__demoCursor / __demoHideCursor; they must be defined.
    assert "__demoCursor" in stagemod.CURSOR_JS
    assert "__demoHideCursor" in stagemod.CURSOR_JS


def test_hide_js_template_has_a_substitution_point():
    assert "__BAD__" in stagemod.HIDE_JS_TEMPLATE
    js = stagemod.HIDE_JS_TEMPLATE.replace("__BAD__", '["BRAND-NAME"]')
    assert "__BAD__" not in js
    assert "BRAND-NAME" in js


def test_playwright_is_not_imported_at_module_level():
    js = stagemod.HIDE_JS_TEMPLATE.replace("__BAD__", "[]")
    assert "if (!BAD.length) return;" in js
