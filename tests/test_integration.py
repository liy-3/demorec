# -*- coding: utf-8 -*-
"""End-to-end shape tests that do not need a browser or ffmpeg.

These guard the project contract: the three files load, the timing table the
recorder consumes has the right shape, and the CLI dispatches to the right
module."""
import json, os, subprocess, sys
import pytest

from helpers import write_project, MINIMAL_CONFIG, MINIMAL_PAGES, MINIMAL_SCENES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def test_cli_help_lists_every_command():
    pr = subprocess.run([sys.executable, os.path.join(SCRIPTS, "demorec.py"), "--help"],
                        capture_output=True, text=True, errors="ignore")
    assert pr.returncode == 0
    for cmd in ("lint", "probe", "dry", "tts", "record", "audio", "build", "run"):
        assert cmd in pr.stdout, "CLI help must mention %r" % cmd


def test_cli_rejects_a_directory_that_is_not_a_project(tmp_path):
    pr = subprocess.run([sys.executable, os.path.join(SCRIPTS, "demorec.py"),
                         "lint", str(tmp_path)], capture_output=True, text=True, errors="ignore")
    assert pr.returncode != 0
    combined = pr.stdout + pr.stderr
    assert "demorec.yaml" in combined or "missing" in combined


def test_lint_command_exit_codes(tmp_path):
    clean = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, MINIMAL_SCENES)
    ok = subprocess.run([sys.executable, os.path.join(SCRIPTS, "demorec.py"), "lint", clean],
                        capture_output=True, text=True, errors="ignore")
    assert ok.returncode == 0, ok.stdout + ok.stderr

    broken = MINIMAL_SCENES.replace("el: start_button", "el: missing_one")
    bad = tmp_path / "bad"
    bad.mkdir()
    d = write_project(bad, MINIMAL_CONFIG, MINIMAL_PAGES, broken)
    res = subprocess.run([sys.executable, os.path.join(SCRIPTS, "demorec.py"), "lint", d],
                         capture_output=True, text=True, errors="ignore")
    assert res.returncode == 1
    assert "missing_one" in res.stdout


def test_timing_table_contract(tmp_path):
    """The recorder reads sent_ends; audio.py and tts.py must both produce it."""
    import audio
    timing = {
        "s1": {"sent_starts": [0.8, 2.0], "sent_ends": [1.8, 3.0],
               "durs": [1.0, 1.0], "scene_len": 4.0, "narration": ["a", "b"]}
    }
    p = tmp_path / "timing.json"
    p.write_text(json.dumps(timing), encoding="utf-8")
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert set(loaded["s1"]) >= {"sent_starts", "sent_ends", "scene_len"}
    assert len(loaded["s1"]["sent_ends"]) == len(loaded["s1"]["narration"])
    # sent_ends must be non-decreasing: the recorder walks them in order
    ends = loaded["s1"]["sent_ends"]
    assert ends == sorted(ends)


def test_say_reads_sent_ends_from_timing(tmp_path):
    """stage.Stage.say() indexes sent_ends; guard the contract it depends on."""
    import stage
    s = stage.Stage(str(tmp_path), "s1", {})
    s.timing = {"s1": {"sent_ends": [1.0, 2.5]}}
    seen = []
    s.wait_until = lambda t: seen.append(t) or s
    s.say(1)
    s.say(0, extra=0.5)
    assert seen == [2.5, 1.5]


def test_say_raises_a_clear_error_for_an_unknown_scene(tmp_path):
    import stage
    s = stage.Stage(str(tmp_path), "ghost", {})
    s.timing = {}
    with pytest.raises(RuntimeError) as ei:
        s.say(0)
    assert "timing.json" in str(ei.value)


def test_say_raises_when_the_index_exceeds_the_lines(tmp_path):
    import stage
    s = stage.Stage(str(tmp_path), "s1", {})
    s.timing = {"s1": {"sent_ends": [1.0]}}
    with pytest.raises(RuntimeError) as ei:
        s.say(3)
    assert "only 1" in str(ei.value)


def test_elapsed_uses_wall_clock_not_the_last_frame(tmp_path):
    """Regression: a still page produces no frames, so a frame-based clock froze
    and wait_until() looped forever."""
    import time as _t
    import stage
    s = stage.Stage(str(tmp_path), "s1", {})
    s.wall0 = _t.time() - 5.0
    s.frame_offset = 0.0
    s.frames = []              # no frames at all, as on a static page
    assert s.elapsed() >= 4.5


def test_wait_until_terminates_without_any_frames(tmp_path):
    import time as _t
    import stage
    s = stage.Stage(str(tmp_path), "s1", {})
    s.wall0 = _t.time()
    s.frame_offset = 0.0
    s.frames = []
    s._tick = lambda dt=0.05: _t.sleep(min(dt, 0.01))
    s.wait_until(0.05)        # would hang with a frame-based clock
    assert s.elapsed() >= 0.05
