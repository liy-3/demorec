# Step reference

Every step is one key plus optional modifiers. `scripts/run.py` interprets the whole
storyboard; when you add syntax, change the interpreter and this file together.

| Step | Effect | Modifiers |
|---|---|---|
| `goto: <page>` | open a page from `pages.yaml` and wait for it to be ready | — |
| `start` | begin CDP frame capture | — |
| `stop` | stop capture, encode the scene to mp4 | — |
| `say: N` / `say: [N, extra]` | block until narration line N of this scene has finished, plus `extra` seconds | `extra` |
| `wait: T` | block until t = T seconds of the recording (absolute) | — |
| `sleep: S` | block for S seconds on the recording clock (relative) | `seconds` |
| `move: <target>` | glide the synthetic cursor there | `dur` |
| `click: <target>` | move → settle → press → release | `hover` `after` `dur` |
| `hover: <target>` | move there and hold | `hold` `dur` |
| `type: <text>` | type into the focused field at a human pace | `cps` |
| `key: <combo>` | press a key or chord, e.g. `Enter`, `Control+A` | — |
| `scroll: <dy>` | smooth wheel scroll, positive scrolls down | `steps` `settle` |
| `shot: <name>` | save a PNG to `shots/` for manual review | — |
| `for_each: {over: [...], do: [...]}` | run sub-steps once per item in `over` | — |

Step modifiers are ordinary siblings of the step key, e.g.
`- click: {el: save_button, after: 1.2}`.

`start` and `stop` are the only steps that may be written bare, because in YAML a
bare scalar is a string rather than a mapping:

```yaml
- start            # same as - start: null
- say              # invalid: say needs an index
```

## Targets

Priority, highest first:

1. `{el: name}` — a semantic name from `pages.yaml`. **Preferred**: when the site
   is redesigned, only the selector table changes.
2. `{sel: "css or playwright selector"}` — a one-off target not worth naming.
3. `{at: [x, y]}` — absolute pixel in the frame. **Last resort**: it breaks as soon
   as the layout shifts, and it is the main reason a second project feels like
   rewriting the storyboard.

A bare `[x, y]` is accepted as shorthand for `{at: [x, y]}`, so `- move: [960, 480]`
works. A target must contain **exactly one** of `el` / `sel` / `at`; `lint` reports
anything else.

## Why `say` instead of seconds

```yaml
- click: {el: submit_button}
- say: 3          # instead of - sleep: 7.2
```

When a narration line is rewritten, `say` follows it automatically. `sleep: 7.2`
silently desynchronises the action from the voice, and the mismatch only shows up
in the rendered file, where fixing it is expensive.
