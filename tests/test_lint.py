# -*- coding: utf-8 -*-
"""Static checks: the fast feedback loop that needs no browser."""
import pytest

import lint as lintmod
from helpers import (write_project, MINIMAL_CONFIG, MINIMAL_PAGES, MINIMAL_SCENES)


def test_clean_project_has_no_errors(tmp_path):
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, MINIMAL_SCENES)
    rep = lintmod.lint(d)
    assert rep.errors == []


def test_missing_file_is_reported(tmp_path):
    write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, MINIMAL_SCENES)
    (tmp_path / "scenes.yaml").unlink()
    rep = lintmod.lint(str(tmp_path))
    assert any("scenes.yaml" in e and "missing" in e for e in rep.errors)


def test_invalid_yaml_is_reported(tmp_path):
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, MINIMAL_SCENES)
    with open(d + "/scenes.yaml", "w", encoding="utf-8") as f:
        f.write("scenes: [unclosed")
    rep = lintmod.lint(d)
    assert any("not valid YAML" in e for e in rep.errors)


def test_unknown_element_name_is_an_error(tmp_path):
    scenes = MINIMAL_SCENES.replace("el: start_button", "el: typo_button")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("typo_button" in e and "not defined" in e for e in rep.errors)


def test_say_index_past_last_line_is_an_error(tmp_path):
    scenes = MINIMAL_SCENES.replace("say: 0", "say: 5")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("out of range" in e for e in rep.errors)


def test_negative_say_index_is_an_error(tmp_path):
    scenes = MINIMAL_SCENES.replace("say: 0", "say: -1")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("out of range" in e for e in rep.errors)


def test_say_without_narration_is_an_error(tmp_path):
    scenes = MINIMAL_SCENES.replace("    narration:\n      - one\n      - two\n", "")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("no narration" in e for e in rep.errors)


def test_unknown_step_is_an_error(tmp_path):
    scenes = MINIMAL_SCENES.replace("- say: 0", "- teleport: 3")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("unknown step" in e and "teleport" in e for e in rep.errors)


def test_goto_unknown_page_is_an_error(tmp_path):
    scenes = MINIMAL_SCENES.replace("goto: home", "goto: nowhere")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("unknown page" in e for e in rep.errors)


def test_scene_page_missing_from_pages(tmp_path):
    scenes = MINIMAL_SCENES.replace("page: home", "page: dashboard")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("dashboard" in e for e in rep.errors)


@pytest.mark.parametrize("boxes,expect_error", [
    ("[[6, 4, 306, 66]]", False),
    ("[[900, 4, 500, 66]]", True),          # x+w exceeds a 1280 frame
    ("[[6, 4, 0, 66]]", True),              # non-positive width
    ("[[6, 4, 306]]", True),                # wrong arity
    ("[[6, -4, 306, 66]]", True),           # negative origin
])
def test_mask_box_geometry(tmp_path, boxes, expect_error):
    cfg = MINIMAL_CONFIG.replace("boxes: []", "boxes: " + boxes)
    d = write_project(tmp_path, cfg, MINIMAL_PAGES, MINIMAL_SCENES)
    rep = lintmod.lint(d)
    assert bool(rep.errors) is expect_error


def test_duplicate_scene_id_is_an_error(tmp_path):
    scenes = MINIMAL_SCENES + MINIMAL_SCENES.split("scenes:\n", 1)[1]
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("duplicate scene id" in e for e in rep.errors)


def test_missing_start_and_stop_are_warnings(tmp_path):
    scenes = MINIMAL_SCENES.replace("      - start\n", "").replace("      - stop\n", "")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert rep.errors == []
    assert any("no \"start\"" in w for w in rep.warnings)
    assert any("no \"stop\"" in w for w in rep.warnings)


def test_absolute_pixel_targets_are_discouraged(tmp_path):
    scenes = MINIMAL_SCENES.replace("click: {el: start_button}", "click: {at: [10, 20]}")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert rep.errors == []
    assert any("absolute-pixel" in w for w in rep.warnings)


def test_target_needs_exactly_one_key(tmp_path):
    scenes = MINIMAL_SCENES.replace("click: {el: start_button}",
                                    "click: {el: start_button, sel: \"button\"}")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("exactly one of el/sel/at" in e for e in rep.errors)


def test_for_each_validates_inner_steps(tmp_path):
    block = ('      - for_each:\n'
             '          over: [[1, 2], [3, 4]]\n'
             '          do:\n'
             '            - click: {el: nope}\n')
    scenes = MINIMAL_SCENES.replace("      - say: 0\n", block + "      - say: 0\n")
    d = write_project(tmp_path, MINIMAL_CONFIG, MINIMAL_PAGES, scenes)
    rep = lintmod.lint(d)
    assert any("nope" in e for e in rep.errors)


def test_lint_module_has_no_heavy_dependencies():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ex = os.path.join(root, "examples", "todomvc")
    if not os.path.isdir(ex):
        pytest.skip("example project not present")
    rep = lintmod.lint(ex)
    assert rep.errors == [], "example project must lint clean: %r" % (rep.errors,)
