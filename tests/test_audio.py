# -*- coding: utf-8 -*-
"""Audio pacing maths: the scene track must end up exactly as long as the video.

These tests use a fake ffmpeg and stubbed durations, so they run in milliseconds
and do not need media files."""
import os
import pytest

import audio as audiomod


class FakeAudioBuilder(audiomod.AudioBuilder):
    """Replaces the real transcode/measure calls with deterministic stubs."""

    def __init__(self, workdir, durs, video_duration):
        super().__init__(workdir, "ffmpeg-stub")
        self._durs = durs
        self._video_duration = video_duration
        self.calls = []

    def to_wav(self, src, dst):
        self.calls.append(("to_wav", os.path.basename(src)))
        open(dst, "wb").close()

    def silence(self, sec, dst):
        self.calls.append(("silence", round(sec, 4)))
        open(dst, "wb").close()

    def concat(self, parts, dst):
        self.calls.append(("concat", len(parts)))
        open(dst, "wb").close()


def make_builder(tmp_path, sent_durs, video_dur):
    b = FakeAudioBuilder(str(tmp_path), sent_durs, video_dur)
    seq = list(sent_durs)
    real_probe = audiomod.probe_media

    def fake_probe(ff, path):
        name = os.path.basename(path)
        if "_scene_" in name:
            return {"duration": b._last_len, "size": 1}
        if name.endswith(".wav") and "_" in name and name[0].isdigit() is False:
            return {"duration": seq.pop(0) if seq else 1.0, "size": 1}
        if name.endswith(".wav"):
            return {"duration": seq.pop(0) if seq else 1.0, "size": 1}
        return {"duration": video_dur, "size": 1}

    return b, fake_probe


def test_scene_track_length_matches_video_when_narration_is_shorter(tmp_path, monkeypatch):
    """4 lines of 1s with 0.38 gaps under a 10s video: the tail absorbs the rest."""
    b = FakeAudioBuilder(str(tmp_path), [1.0] * 4, 10.0)
    lens = []

    def fake_concat(parts, dst):
        # lead + lines + gaps + tail
        lens.append(parts)
        open(dst, "wb").close()

    b.concat = fake_concat
    durations = iter([1.0] * 4 + [10.0])
    monkeypatch.setattr(audiomod, "probe_media",
                        lambda ff, p: {"duration": next(durations, 1.0), "size": 1})
    wav, durs, pace, got, vdur = b.build_scene("s1", "video.mp4", 4,
                                              {"lead_in": 0.8, "gap": 0.38, "tail": 1.6})
    lead, gap, tail = pace
    expected_tail = 10.0 - (lead + sum(durs) + gap * 3)
    assert tail == pytest.approx(expected_tail, abs=1e-6)
    assert tail > 0


def test_scene_track_shrinks_gaps_when_narration_overruns(tmp_path, monkeypatch):
    """Narration longer than the video: gaps must compress instead of overflowing."""
    b = FakeAudioBuilder(str(tmp_path), [0.0], 5.0)
    b.concat = lambda parts, dst: open(dst, "wb").close()
    # 4 lines x 2s = 8s of speech already exceeds a 5s video
    durations = iter([2.0, 2.0, 2.0, 2.0, 5.0])
    monkeypatch.setattr(audiomod, "probe_media",
                        lambda ff, p: {"duration": next(durations, 1.0), "size": 1})
    wav, durs, pace, got, vdur = b.build_scene("s1", "video.mp4", 4,
                                              {"lead_in": 0.8, "gap": 0.38, "tail": 1.6})
    lead, gap, tail = pace
    assert gap < 0.38, "gaps must compress when narration overruns the video"
    assert gap >= 0.10, "gaps must not collapse below the floor"
    assert lead <= 0.8
    assert tail >= 0.25, "there must always be some tail"


def test_pace_covers_every_line_with_a_gap_between(tmp_path, monkeypatch):
    b = FakeAudioBuilder(str(tmp_path), [0.0], 20.0)
    parts_seen = {}

    def fake_concat(parts, dst):
        parts_seen["n"] = len(parts)
        open(dst, "wb").close()

    b.concat = fake_concat
    durations = iter([1.0, 1.0, 1.0, 20.0])
    monkeypatch.setattr(audiomod, "probe_media",
                        lambda ff, p: {"duration": next(durations, 1.0), "size": 1})
    b.build_scene("s1", "video.mp4", 3, {"lead_in": 0.8, "gap": 0.38, "tail": 1.6})
    # lead + 3 lines + 2 gaps + tail
    assert parts_seen["n"] == 1 + 3 + 2 + 1


def test_single_line_needs_no_gap(tmp_path, monkeypatch):
    b = FakeAudioBuilder(str(tmp_path), [0.0], 10.0)
    parts_seen = {}

    def fake_concat(parts, dst):
        parts_seen["n"] = len(parts)
        open(dst, "wb").close()

    b.concat = fake_concat
    durations = iter([2.0, 10.0])
    monkeypatch.setattr(audiomod, "probe_media",
                        lambda ff, p: {"duration": next(durations, 1.0), "size": 1})
    b.build_scene("s1", "video.mp4", 1, {"lead_in": 0.8, "gap": 0.38, "tail": 1.6})
    assert parts_seen["n"] == 3, "lead + 1 line + tail"
