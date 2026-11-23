# -*- coding: utf-8 -*-
"""Shared helpers for the tests."""
import os, textwrap


def write_project(tmp_path, config, pages, scenes):
    """Write the three project files into tmp_path and return the directory."""
    d = str(tmp_path)
    (tmp_path / "demorec.yaml").write_text(textwrap.dedent(config), encoding="utf-8")
    (tmp_path / "pages.yaml").write_text(textwrap.dedent(pages), encoding="utf-8")
    (tmp_path / "scenes.yaml").write_text(textwrap.dedent(scenes), encoding="utf-8")
    return d


MINIMAL_CONFIG = """
project: test
viewport: [1280, 720]
fps: 30
root_url: https://example.com/app/
mask:
  boxes: []
build:
  output_name: out.mp4
"""

MINIMAL_PAGES = """
pages:
  home:
    url: index.html
    elements:
      start_button: "button.start"
      field:
        - "input[name=q]"
        - "textarea"
"""

MINIMAL_SCENES = """
scenes:
  - id: s1
    title: first
    page: home
    narration:
      - one
      - two
    steps:
      - goto: home
      - start
      - click: {el: start_button}
      - say: 0
      - stop
"""
