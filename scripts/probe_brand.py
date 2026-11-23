# -*- coding: utf-8 -*-
"""demorec probe — suggest brand-mask boxes for a page instead of eyeballing them.

Mask coordinates are the one thing that cannot be inherited from another
project: the brand block sits at a different place on every site. This tool
opens the page, looks for the top-bar block that carries the logo and the
product name, and prints candidate rectangles to paste into demorec.yaml.

It only suggests. A human confirms the box before the real recording, because
an under-sized box silently leaks the brand instead of failing loudly.
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

FIND_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const vw = window.innerWidth;
  const push = (el, why) => {
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 18) return;
    if (r.top > 140) return;                 // only the top bar
    if (r.left > vw * 0.6) return;           // only the left brand zone
    const key = Math.round(r.left) + ':' + Math.round(r.top) + ':' +
                Math.round(r.width) + ':' + Math.round(r.height);
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      why: why,
      tag: el.tagName,
      cls: String(el.className || '').slice(0, 60),
      text: (el.innerText || '').trim().slice(0, 40),
      box: [Math.round(r.left), Math.round(r.top),
            Math.round(r.width), Math.round(r.height)]
    });
  };
  document.querySelectorAll('img,svg').forEach(el => push(el, 'logo-image'));
  document.querySelectorAll('*' ).forEach(el => {
    const t = (el.innerText || '').trim();
    if (!t || t.length > 40 || t.indexOf('\n') >= 0) return;
    if (el.children.length > 2) return;
    const r = el.getBoundingClientRect();
    if (r.top > 140 || r.left > window.innerWidth * 0.6) return;
    if (r.width < 60 || r.height < 18) return;
    push(el, 'topbar-text');
  });
  return out.sort((a, b) => a.box[1] - b.box[1] || a.box[0] - b.box[0]).slice(0, 20);
}
"""


def main(argv):
    import yaml
    project = os.path.abspath(argv[0]) if argv else os.getcwd()
    page_name = argv[1] if len(argv) > 1 else None

    with open(os.path.join(project, 'demorec.yaml'), encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    with open(os.path.join(project, 'pages.yaml'), encoding='utf-8') as f:
        pages = yaml.safe_load(f)['pages']

    from playwright.sync_api import sync_playwright
    from stage import find_ffmpeg  # noqa: F401  (ensures deps import cleanly)

    targets = [(page_name, pages[page_name])] if page_name else list(pages.items())
    results = {}
    with sync_playwright() as p:
        launch = {'headless': True}
        if cfg.get('browser_channel'):
            launch['channel'] = cfg['browser_channel']
        browser = p.chromium.launch(**launch)
        w, h = cfg.get('viewport', (1920, 1080))
        ctx = browser.new_context(viewport={'width': w, 'height': h},
                                  device_scale_factor=1,
                                  locale=cfg.get('locale', 'zh-CN'),
                                  ignore_https_errors=True)
        root = (cfg.get('root_url') or '').strip()
        for name, page in targets:
            url = page['url'] if str(page['url']).startswith(('http://', 'https://')) \
                else root.rstrip('/') + '/' + str(page['url']).lstrip('/')
            pg = ctx.new_page()
            try:
                pg.goto(url, wait_until='domcontentloaded', timeout=120000)
                gone = (cfg.get('ready_gone_text') or '').strip()
                for _ in range(120):
                    txt = pg.evaluate("() => document.body ? document.body.innerText : ''")
                    if len(txt.strip()) > 60 and (not gone or gone not in txt) \
                            and 'loading' not in txt.lower():
                        break
                    pg.wait_for_timeout(500)
                pg.wait_for_timeout(1200)
                results[name] = pg.evaluate(FIND_JS)
                shot = os.path.join(project, 'shots', 'probe_%s.png' % name)
                os.makedirs(os.path.dirname(shot), exist_ok=True)
                pg.screenshot(path=shot)
            except Exception as e:
                results[name] = [{'error': str(e)[:160]}]
            finally:
                pg.close()
        ctx.close()
        browser.close()

    print('\nCandidate mask boxes (x, y, w, h) — confirm against the screenshot,\n'
          'then paste the union into demorec.yaml under mask.boxes.\n', flush=True)
    for name, cands in results.items():
        print('page %s' % name, flush=True)
        if not cands:
            print('  (no candidates — the header may not be rendered yet)', flush=True)
        boxes = []
        for c in cands:
            if 'error' in c:
                print('  error: %s' % c['error'], flush=True)
                continue
            b = c['box']
            print('  %-12s %-18s %-26s box=%s' % (c['why'], c['tag'], c['text'], b), flush=True)
            boxes.append(b)
        if boxes:
            x0 = min(b[0] for b in boxes)
            y0 = min(b[1] for b in boxes)
            x1 = max(b[0] + b[2] for b in boxes)
            y1 = max(b[1] + b[3] for b in boxes)
            print('  -> union: [%d, %d, %d, %d]' % (x0, y0, x1 - x0, y1 - y0), flush=True)
        print('  screenshot: shots/probe_%s.png' % name, flush=True)
    print('\nReminder: leave a few pixels of slack, and verify one exported frame,\n'
          'because an undersized box leaks the brand silently.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]) or 0)
