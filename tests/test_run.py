# -*- coding: utf-8 -*-
"""Step interpreter semantics, tested against a fake Stage (no browser)."""
import pytest

import run as runmod


class FakeStage:
    """Records every call so tests can assert on the interpreted program."""

    def __init__(self):
        self.calls = []
        self.scene = "s1"
        self.pages = {"home": "https://example.com/"}
        self.elements = {"btn": ["button.x"], "other": "a.y"}
        self.timing = {"s1": {"sent_ends": [1.0, 2.5, 4.0]}}
        self.t = 0.0

    def elapsed(self):
        return self.t

    def goto(self, url):
        self.calls.append(("goto", url))

    def start(self):
        self.calls.append(("start",))

    def stop(self, **kw):
        self.calls.append(("stop",))

    def wait_until(self, t):
        self.calls.append(("wait_until", t))
        self.t = t

    def sleep(self, sec):
        self.calls.append(("sleep", sec))

    def say(self, idx, extra=0.0):
        self.calls.append(("say", idx, extra))

    def resolve(self, spec):
        self.calls.append(("resolve", spec))
        # Mirror stage.Stage.resolve: bare [x, y] and {"at": [x, y]} both work.
        if isinstance(spec, (list, tuple)):
            return float(spec[0]), float(spec[1])
        if isinstance(spec, dict) and "at" in spec:
            return float(spec["at"][0]), float(spec["at"][1])
        return (10.0, 20.0)

    def move(self, x, y, dur=0.55):
        self.calls.append(("move", x, y, dur))

    def click_at(self, x, y, hover=0.35, after=0.6, dur=0.55):
        self.calls.append(("click_at", x, y, hover, after, dur))

    def type_text(self, text, cps=6.0):
        self.calls.append(("type", text, cps))

    def key(self, combo):
        self.calls.append(("key", combo))

    def scroll(self, dy, steps=16, settle=0.25):
        self.calls.append(("scroll", dy, steps, settle))

    def shot(self, name):
        self.calls.append(("shot", name))


def runner():
    return runmod.StepRunner(FakeStage())


def test_bare_string_step_is_a_noarg_step():
    r = runner()
    r.run(["start", "stop"])
    assert r.s.calls == [("start",), ("stop",)]


def test_bare_string_that_needs_an_argument_is_rejected():
    r = runner()
    with pytest.raises(ValueError):
        r.run(["say"])


def test_unknown_step_is_rejected_with_a_helpful_message():
    r = runner()
    with pytest.raises(ValueError) as ei:
        r.run([{"teleport": 1}])
    assert "teleport" in str(ei.value)
    assert "supported" in str(ei.value)


def test_empty_step_is_rejected():
    r = runner()
    with pytest.raises(ValueError):
        r.run([{}])


def test_say_scalar_and_pair_forms():
    r = runner()
    r.run([{"say": 1}, {"say": [2, 0.4]}])
    assert ("say", 1, 0.0) in r.s.calls
    assert ("say", 2, 0.4) in r.s.calls


def test_say_accepts_extra_modifier():
    r = runner()
    r.run([{"say": 0, "extra": 0.25}])
    assert ("say", 0, 0.25) in r.s.calls


def test_click_passes_modifiers_through():
    r = runner()
    r.run([{"click": {"el": "btn"}, "hover": 0.5, "after": 1.1, "dur": 0.3}])
    assert ("click_at", 10.0, 20.0, 0.5, 1.1, 0.3) in r.s.calls


def test_click_defaults_when_modifiers_are_absent():
    r = runner()
    r.run([{"click": {"el": "btn"}}])
    assert ("click_at", 10.0, 20.0, 0.35, 0.6, 0.55) in r.s.calls


def test_positional_tuple_target_is_accepted():
    r = runner()
    r.run([{"move": [5, 6], "dur": 0.2}])
    assert ("move", 5.0, 6.0, 0.2) in r.s.calls


def test_flag_step_updates_its_argument():
    r = runner()
    r.run([{"start": None}, {"stop": None}])
    assert ("start",) in r.s.calls and ("stop",) in r.s.calls


def test_for_each_substitutes_each_item_into_the_body():
    r = runner()
    r.run([{"for_each": {"over": [[1, 2], [3, 4]],
                           "do": [{"click": {"at": [0, 0]}}]}}])
    clicks = [c for c in r.s.calls if c[0] == "click_at"]
    assert len(clicks) == 2
    assert clicks[0][1:3] == (1.0, 2.0)
    assert clicks[1][1:3] == (3.0, 4.0)


def test_for_each_keeps_other_modifiers():
    r = runner()
    r.run([{"for_each": {"over": [[1, 2]],
                           "do": [{"click": {"at": [0, 0]}, "after": 2.0}]}}])
    click = [c for c in r.s.calls if c[0] == "click_at"][0]
    assert click[4] == 2.0


def test_wait_and_sleep_map_to_the_right_clock_calls():
    r = runner()
    r.run([{"wait": 3.5}, {"sleep": 1.25}])
    assert ("wait_until", 3.5) in r.s.calls
    assert ("sleep", 1.25) in r.s.calls


def test_type_uses_cps_modifier():
    r = runner()
    r.run([{"type": "hello", "cps": 12}])
    assert ("type", "hello", 12.0) in r.s.calls


def test_scroll_uses_steps_and_settle():
    r = runner()
    r.run([{"scroll": 400, "steps": 8, "settle": 0.1}])
    assert ("scroll", 400.0, 8, 0.1) in r.s.calls


def test_failure_reports_the_step_that_broke():
    r = runner()
    with pytest.raises(ValueError) as ei:
        r.run([{"start": None}, {"nope": 1}])
    assert "nope" in str(ei.value)
