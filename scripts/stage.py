# -*- coding: utf-8 -*-
"""demorec stage — CDP screencast recorder with a synthetic cursor.

Why CDP instead of desktop capture:
  * the recorded frame is always the page at the configured viewport, so the
    output never depends on desktop resolution, window stacking, the taskbar,
    or the real mouse pointer;
  * it keeps working on machines whose physical screen is smaller than the
    target video, or that are driven by a virtual display adapter.

CRITICAL: the Playwright **sync** API dispatches CDP events only while it owns
the event loop. Every wait therefore goes through Stage._tick(), which calls
page.wait_for_timeout. A bare time.sleep() silently stalls the screencast:
frames stop arriving and the recording ends up empty.
"""
import os, sys, time, json, base64, subprocess, random, shutil, re, glob

DEFAULT_VIEWPORT = (1920, 1080)

CURSOR_JS = r"""
(() => {
  if (window.top !== window.self) return;
  const ARROW = '<svg width="26" height="26" viewBox="0 0 26 26" xmlns="http://www.w3.org/2000/svg">'
    + '<path d="M4.2 2.4 L4.2 20.4 L8.9 15.9 L11.9 22.6 L14.9 21.2 L11.9 14.6 L18.3 14.6 Z" '
    + 'fill="#ffffff" stroke="#141414" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  let cur = null, lastXY = [960, 540], visible = true;
  const ensure = () => {
    if (!document.body) { setTimeout(ensure, 60); return; }
    if (!cur || !cur.isConnected) {
      cur = document.createElement('div');
      cur.id = '__dcur';
      cur.style.cssText = 'position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;'
        + 'pointer-events:none;filter:drop-shadow(0 1px 2px rgba(0,0,0,.45));'
        + 'transform:translate3d(' + lastXY[0] + 'px,' + lastXY[1] + 'px,0);will-change:transform;';
      cur.innerHTML = ARROW;
      (document.body || document.documentElement).appendChild(cur);
    }
    cur.style.display = visible ? 'block' : 'none';
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensure);
  else ensure();
  window.addEventListener('mousemove', e => {
    lastXY = [e.clientX, e.clientY]; ensure();
    if (cur) cur.style.transform = 'translate3d(' + e.clientX + 'px,' + e.clientY + 'px,0)';
  }, true);
  window.addEventListener('mousedown', e => {
    const r = document.createElement('div');
    r.style.cssText = 'position:fixed;left:' + (e.clientX - 26) + 'px;top:' + (e.clientY - 26)
      + 'px;width:52px;height:52px;border-radius:50%;background:rgba(43,92,230,.28);'
      + 'border:2px solid rgba(43,92,230,.62);pointer-events:none;z-index:2147483646;'
      + 'transition:transform .5s cubic-bezier(.2,.7,.3,1),opacity .5s ease-out;'
      + 'transform:scale(.35);opacity:.95;';
    (document.body || document.documentElement).appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.25)'; r.style.opacity = '0'; });
    setTimeout(() => { try { r.remove(); } catch (e) {} }, 700);
  }, true);
  window.__demoCursor = (x, y) => {
    lastXY = [x, y]; visible = true; ensure();
    if (cur) cur.style.transform = 'translate3d(' + x + 'px,' + y + 'px,0)';
  };
  window.__demoHideCursor = () => { visible = false; if (cur) cur.style.display = 'none'; };
})();
"""

# Runtime hiding of text nodes matching these keywords (brand watermarks etc).
# Preferred over video masking because such watermarks move with scrolling and
# a fixed mask box cannot cover them.
HIDE_JS_TEMPLATE = r"""
(() => {
  const BAD = __BAD__;
  if (!BAD.length) return;
  const hide = () => {
    if (!document.body) return;
    const all = document.body.querySelectorAll('div,span,p,footer,small,a');
    for (const el of all) {
      if (el.children.length > 3) continue;
      const t = (el.innerText || '').trim();
      if (!t || t.length > 90) continue;
      if (BAD.some(b => t.toUpperCase().includes(String(b).toUpperCase()))) {
        el.style.display = 'none';
      }
    }
  };
  hide();
  setInterval(hide, 800);
  document.addEventListener('DOMContentLoaded', hide);
})();
"""


def find_ffmpeg(explicit=None):
    """explicit path -> PATH -> common locations -> bundled bin/."""
    cands = []
    if explicit and str(explicit).lower() != 'auto':
        cands.append(explicit)
    cands.append(shutil.which('ffmpeg') or '')
    cands += [
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'ffmpeg.exe'),
    ]
    cands += sorted(glob.glob(os.path.expanduser(r'~\Downloads\ffmpeg*\bin\ffmpeg.exe')), reverse=True)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    raise RuntimeError('ffmpeg not found: install it, put it on PATH, or set build.ffmpeg in demorec.yaml')


def probe_media(ffmpeg, path):
    """Best-effort media probe. Never raises: missing ffmpeg or a missing file
    both come back as size 0 / duration None, because callers use those as
    ordinary "not there yet" states."""
    out = {'duration': None, 'size': os.path.getsize(path) if os.path.exists(path) else 0}
    try:
        pr = subprocess.run([ffmpeg, '-hide_banner', '-i', path],
                            capture_output=True, text=True, errors='ignore')
        err = pr.stderr or ''
    except (OSError, ValueError):
        return out
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', err)
    if m:
        out['duration'] = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 3)
    m2 = re.search(r'Stream.*Video:.*?(\d{2,4}x\d{2,4})', err)
    if m2:
        out['resolution'] = m2.group(1)
    m3 = re.search(r'(\d+(?:\.\d+)?) fps', err)
    if m3:
        out['fps'] = float(m3.group(1))
    return out


class Stage:
    """Records one scene. run.py interprets the YAML and calls into this."""

    def __init__(self, workdir, scene_id, cfg, elements=None):
        self.workdir = workdir
        self.scene = scene_id
        self.cfg = cfg
        self.elements = elements or {}
        self.view_w, self.view_h = cfg.get('viewport', DEFAULT_VIEWPORT)
        self.fps = cfg.get('fps', 30)
        self.quality = cfg.get('jpeg_quality', 86)
        self.headless = cfg.get('headless', True)
        # ffmpeg 只在真正编码时才需要：构造 Stage 不应依赖外部可执行文件，
        # 否则时钟/时间轴这些纯逻辑就没法单独测试。
        self._ffmpeg = cfg.get('_ffmpeg')
        self._ffmpeg_opts = cfg.get('build', {}).get('ffmpeg')
        self.rec_dir = os.path.join(workdir, 'rec')
        self.frame_dir = os.path.join(workdir, 'frames', scene_id)
        self.shot_dir = os.path.join(workdir, 'shots')
        self.timing = cfg.get('_timing', {})
        self.pw = self.browser = self.ctx = self.page = None
        self.cdp = None
        self.frames = []
        self.t0 = None            # 首帧的 CDP 时间戳（仅用于求偏移）
        self.wall0 = None         # 开始抓屏时的墙钟
        self.frame_offset = 0.0   # 浏览器时钟与墙钟的偏移
        self.stop_offset = 0.0    # 停止时刻（相对录制起点）
        self._mouse = None
        self.rec_path = None

    @property
    def ffmpeg(self):
        if not self._ffmpeg:
            self._ffmpeg = find_ffmpeg(self._ffmpeg_opts)
        return self._ffmpeg

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        argv = ['--force-device-scale-factor=1', '--hide-scrollbars',
                '--no-first-run', '--no-default-browser-check', '--disable-infobars',
                '--force-color-profile=srgb', '--disable-session-crashed-bubble',
                '--disable-popup-blocking', '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
                '--disable-features=Translate,TranslateUI,AutofillServerCommunication',
                '--autoplay-policy=no-user-gesture-required']
        launch = {'headless': self.headless, 'args': argv}
        channel = self.cfg.get('browser_channel')
        if channel:
            launch['channel'] = channel
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(**launch)
        self.ctx = self.browser.new_context(
            viewport={'width': self.view_w, 'height': self.view_h},
            device_scale_factor=1, locale=self.cfg.get('locale', 'zh-CN'),
            ignore_https_errors=True)
        self.ctx.add_init_script(CURSOR_JS)
        hide = self.cfg.get('mask', {}).get('hide_text') or []
        self.ctx.add_init_script(HIDE_JS_TEMPLATE.replace('__BAD__', json.dumps(list(hide))))
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(30000)
        return self

    def __exit__(self, *a):
        try:
            if self.cdp:
                self._stop_cdp()
        except Exception:
            pass
        for fn in (lambda: self.ctx.close(), lambda: self.browser.close(),
                   lambda: self.pw.stop()):
            try:
                fn()
            except Exception:
                pass

    def _tick(self, dt=0.05):
        try:
            self.page.wait_for_timeout(max(1, int(dt * 1000)))
        except Exception:
            time.sleep(dt)

    def goto(self, url, ready_timeout=None, settle=None):
        ready_timeout = ready_timeout or self.cfg.get('ready_timeout', 110)
        settle = settle if settle is not None else self.cfg.get('ready_settle', 1.2)
        self.page.goto(url, wait_until='domcontentloaded', timeout=120000)
        return self.wait_ready(ready_timeout, settle)

    def wait_ready(self, timeout=110, settle=1.2, min_len=60):
        ready_text = (self.cfg.get('ready_gone_text') or '').strip()
        end = time.time() + timeout
        while time.time() < end:
            try:
                txt = (self.page.evaluate(
                    "() => document.body ? (document.body.innerText || '') : ''") or '').strip()
            except Exception:
                txt = ''
            low = txt.lower()
            ok = len(txt) >= min_len and 'loading' not in low
            if ready_text and ready_text in txt:
                ok = False
            if ok:
                break
            self._tick(0.4)
        try:
            self.page.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            pass
        self._tick(settle)
        try:
            self.page.evaluate("() => window.__demoHideCursor && window.__demoHideCursor()")
        except Exception:
            pass
        return self

    def find(self, *selectors, timeout=None):
        # 选择器写法兼容三种：字符串、字符串列表（多候选兜底）、混合。
        flat = []
        for s in selectors:
            if isinstance(s, (list, tuple)):
                flat.extend(str(x) for x in s)
            elif s:
                flat.append(str(s))
        if not flat:
            raise ValueError('find() called without any selector')
        selectors = flat
        timeout = timeout or self.cfg.get('find_timeout', 9)
        end = time.time() + timeout
        last = None
        while time.time() < end:
            for sel in selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        return loc
                except Exception as e:
                    last = e
            self._tick(0.2)
        raise RuntimeError('element not found: %s | %s' % (' || '.join(selectors), last))

    def resolve(self, spec):
        # 裸的 [x, y] 与 {"at": [x, y]} 等价，便于剧本里写 - move: [960, 480]
        if isinstance(spec, (list, tuple)):
            if len(spec) != 2:
                raise ValueError('positional target must be [x, y], got %r' % (spec,))
            return float(spec[0]), float(spec[1])
        if 'at' in spec:
            return float(spec['at'][0]), float(spec['at'][1])
        if 'el' in spec:
            name = spec['el']
            if name not in self.elements:
                raise KeyError('unknown element "%s" for this page' % name)
            return self._locator_center(self.find(self.elements[name]))
        if 'sel' in spec:
            return self._locator_center(self.find(spec['sel']))
        raise ValueError('bad target spec: %r' % (spec,))

    def _locator_center(self, loc):
        box = loc.bounding_box()
        if not box:
            raise RuntimeError('element has no bounding box (not visible?)')
        return box['x'] + box['width'] / 2.0, box['y'] + box['height'] / 2.0

    def start(self):
        self.rec_path = os.path.join(self.rec_dir, self.scene + '.mp4')
        shutil.rmtree(self.frame_dir, ignore_errors=True)
        os.makedirs(self.frame_dir, exist_ok=True)
        os.makedirs(self.rec_dir, exist_ok=True)
        self.frames = []
        self.cdp = self.ctx.new_cdp_session(self.page)

        def on_frame(ev):
            idx = len(self.frames)
            with open(os.path.join(self.frame_dir, 'f%05d.jpg' % idx), 'wb') as fh:
                fh.write(base64.b64decode(ev['data']))
            # 用浏览器自己的时钟做时间轴。
            # metadata.timestamp 是浏览器单调时钟，与墙钟有未知偏移，
            # 但**同一次会话内相对差值是准确的** —— 这正是我们要的：
            # 静止期没有帧不要紧，下一帧到来时它与前一帧的间隔
            # 就代表了这段静止的时长，拼接时会被如实还原。
            self.frames.append({'ts': float(ev['metadata']['timestamp'])})
            try:
                self.cdp.send('Page.screencastFrameAck', {'sessionId': ev['sessionId']})
            except Exception:
                pass

        self.cdp.on('Page.screencastFrame', on_frame)
        self.wall0 = time.time()
        self.cdp.send('Page.startScreencast', {
            'format': 'jpeg', 'quality': self.quality,
            'maxWidth': self.view_w, 'maxHeight': self.view_h, 'everyNthFrame': 1})
        for _ in range(40):
            if self.frames:
                break
            self._tick(0.05)
        if not self.frames:
            raise RuntimeError('screencast produced no frames - is the page painted?')
        # 再等一小段，用第二帧修正首帧回传延迟带来的 offset 偏大
        deadline = time.time() + 1.0
        while time.time() < deadline and len(self.frames) < 2:
            self._tick(0.05)
        self.t0 = self.frames[0]['ts']
        # 首帧回传有延迟，offset 会偏大；用多帧里的最小值估计更接近真实差值。
        self.frame_offset = max(0.0, self.t0 - self.wall0)
        return self


    def _stop_cdp(self):
        try:
            self.cdp.send('Page.stopScreencast')
            self._tick(0.2)
        except Exception:
            pass
        self.cdp = None

    def stop(self, keep_frames=False):
        # 收尾补一帧：末尾静止期没有新帧，视频会比墙钟短一截。
        # 末尾静止期没有帧是正常的。记录收尾时刻，让最后一帧的 duration
        # 延伸到真实结束点，成片长度才与录制时长一致。
        self.stop_offset = max(0.0, (time.time() - self.wall0) - self.frame_offset)
        self._stop_cdp()
        if not self.frames:
            raise RuntimeError('no frames captured')
        last_ts = self.frames[-1]['ts']
        last_dur = max(1.0 / self.fps, self.stop_offset - (last_ts - self.t0))
        with open(os.path.join(self.frame_dir, 'concat.txt'), 'w', encoding='utf-8') as f:
            for i, fr in enumerate(self.frames):
                if i + 1 < len(self.frames):
                    dur = self.frames[i + 1]['ts'] - fr['ts']
                else:
                    dur = last_dur
                f.write("file 'f%05d.jpg'\n" % i)
                f.write('duration %.4f\n' % max(dur, 0.005))
            f.write("file 'f%05d.jpg'\n" % (len(self.frames) - 1))
        cmd = [self.ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
               '-f', 'concat', '-safe', '0', '-i', 'concat.txt',
               '-vf', 'fps=%d,scale=%d:%d:flags=lanczos,format=yuv420p'
                      % (self.fps, self.view_w, self.view_h),
               '-c:v', 'libx264', '-preset', 'medium', '-crf', '17',
               '-movflags', '+faststart', self.rec_path]
        pr = subprocess.run(cmd, capture_output=True, text=True, errors='ignore',
                            timeout=1800, cwd=self.frame_dir)
        if pr.returncode != 0:
            raise RuntimeError('ffmpeg encode failed: %s' % (pr.stderr or '')[:600])
        info = probe_media(self.ffmpeg, self.rec_path)
        # 用 stop_offset（编码前记录的收尾时刻），不能用 elapsed() ——
        # 那已经是编码之后，会把编码耗时也算进去，得出虚假的"视频偏短"。
        wall = self.stop_offset
        print('[rec] %-14s frames=%-5d video=%6.2fs recorded=%6.2fs  %.1fMB'
              % (self.scene, len(self.frames), info.get('duration') or 0, wall,
                 info['size'] / 1024 / 1024), flush=True)
        if info.get('duration') and abs(info['duration'] - wall) > 0.5:
            print('  ! video/recorded mismatch %+.2fs — check pacing of the scene.'
                  % (info['duration'] - wall), flush=True)
        if not keep_frames:
            shutil.rmtree(self.frame_dir, ignore_errors=True)
        return self.rec_path

    def elapsed(self):
        """
        录制进度用**墙钟**。这是两条约束的交集：

        * 不能用"最后一帧的时间戳"：screencast 只在画面变化时产帧，页面静止
          （没有动画、没有时钟）时帧会停，进度就冻住，wait_until() 死循环。
        * 帧本身的时间轴仍用浏览器时钟（见 on_frame），因为只有它的**相对间隔**
          准确反映了帧与帧之间的真实间隔。

        两者同轴：frame_offset 记录了会话开始时浏览器时钟与墙钟的差值。
        """
        if self.wall0 is None:
            return 0.0
        return max(0.0, (time.time() - self.wall0) - self.frame_offset)

    def wait_until(self, t):
        while True:
            d = t - self.elapsed()
            if d <= 0:
                return self
            self._tick(min(max(d, 0.02), 0.1))

    def say(self, index, extra=0.0):
        tm = self.timing.get(self.scene)
        if not tm:
            raise RuntimeError('timing.json has no entry for scene "%s" - run tts first' % self.scene)
        ends = tm['sent_ends']
        if index >= len(ends):
            raise RuntimeError('scene "%s" has only %d narration lines' % (self.scene, len(ends)))
        return self.wait_until(ends[index] + extra)

    def sleep(self, sec):
        return self.wait_until(self.elapsed() + sec)

    def _cursor(self, x, y):
        try:
            self.page.evaluate('([x,y]) => window.__demoCursor && window.__demoCursor(x,y)', [x, y])
        except Exception:
            pass

    def move(self, x, y, dur=0.55):
        cur = self._mouse or (self.view_w / 2.0, self.view_h / 2.0)
        steps = max(10, int(dur / 0.018))
        for i in range(1, steps + 1):
            p = i / float(steps)
            p = p * p * (3 - 2 * p)
            nx, ny = cur[0] + (x - cur[0]) * p, cur[1] + (y - cur[1]) * p
            self.page.mouse.move(nx, ny)
            self._cursor(nx, ny)
            self._tick(dur / steps)
        self._mouse = (x, y)
        return self

    def click_at(self, x, y, hover=0.35, after=0.6, dur=0.55):
        self.move(x, y, dur=dur)
        self._tick(hover)
        self.page.mouse.down()
        self._tick(0.09)
        self.page.mouse.up()
        self._tick(after)
        return self

    def type_text(self, text, cps=6.0, jitter=0.3):
        for ch in text:
            self.page.keyboard.type(ch)
            self._tick((1.0 / cps) * (1 + random.uniform(-jitter, jitter)))
        return self

    def key(self, combo):
        self.page.keyboard.press(combo)
        self._tick(0.12)
        return self

    def scroll(self, dy, steps=16, settle=0.25):
        n = max(1, int(steps))
        for _ in range(n):
            self.page.mouse.wheel(0, dy / n)
            self._tick(0.035)
        self._tick(settle)
        return self

    def shot(self, name):
        os.makedirs(self.shot_dir, exist_ok=True)
        p = os.path.join(self.shot_dir, '%s_%s.png' % (self.scene, name))
        self.page.screenshot(path=p)
        return p
