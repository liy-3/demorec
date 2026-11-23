# demorec

[![ci](https://github.com/liy-3/demorec/actions/workflows/ci.yml/badge.svg)](https://github.com/liy-3/demorec/actions/workflows/ci.yml)

**YAML-driven demo recording**: scripted screencast + AI narration + masking, with no
project-specific Python. Change a project by editing YAML, not code.

两条使用路径，同一套代码：

- **独立命令行工具** —— 装了依赖就能直接用，不需要任何 agent 框架：
  `python scripts/demorec.py run <project>`
- **agent skill** —— 把整个目录放进 `~/.dsh/skills/demorec/`（或任何支持 `SKILL.md`
  的 agent 技能目录），`SKILL.md` 里写好了 agent 什么时候该用、先检查什么。
  CLI 本身不认识 agent，skill 只是一层说明，不改变行为。

## 它解决什么

手工录一条带旁白的产品演示视频，通常要：反复重录、手动对齐旁白、逐个打码、
再拼起来。换一个项目这些又都要重来一遍。

demorec 把这件事变成**三个 YAML 文件 + 一条命令**：

```
python scripts/demorec.py dry    <project>   # 先校验，几秒钟发现问题
python scripts/demorec.py run    <project>   # 旁白 → 录制 → 对齐 → 成片
```

## 关键设计

| 决定 | 原因 |
|---|---|
| **CDP 抓渲染帧**，不抓桌面 | 画面恒定等于 viewport，不受分辨率、缩放、窗口层级、任务栏、真实鼠标影响；小屏机器也能出 1080p |
| **场景用 `say: N` 对齐**，不写秒数 | 改一句旁白，整幕节奏自动重排，不需要手调时间轴 |
| **元素用语义名**（`el`），不写像素 | 站点改版只改 `pages.yaml`，分镜剧本不动 |
| **音频先统一转码再拼接** | 混合格式拼接会错乱时间戳，成片音画错位几十秒 |
| **打码在成片阶段做** | 源站一行不改；水印另用运行时隐藏，因为位置会随滚动漂移 |

## 目录

```
demorec/
  SKILL.md              # agent 读取的说明
  scripts/              # 通用管线，项目无关
    demorec.py          # CLI 入口
    stage.py            # CDP 录制 + 合成光标
    run.py              # YAML 步骤解释器
    tts.py              # 旁白合成 → timing.json
    audio.py            # 音轨按幕对齐
    build.py            # 打码 + 拼接 + 合流
    probe_brand.py      # 打码区自动探测
  templates/            # 新项目骨架，拷走即用
  references/           # steps.md / pitfalls.md
  examples/todomvc/    # 两幕公开示例（Playwright TodoMVC，可直接跑）
```

## 独立使用（不用 agent）

```bash
git clone https://github.com/liy-3/demorec.git
cd demorec
python -m pip install -r requirements.txt
playwright install chromium        # 或用本机 Chrome：浏览器配置里写 browser_channel: chrome

cp -r templates my-demo            # 从骨架起一个新工程
# 编辑 my-demo 下三个 yaml，然后：
python scripts/demorec.py dry my-demo    # 先校验选择器，几秒钟
python scripts/demorec.py run my-demo    # 旁白 → 录制 → 对齐 → 成片
```

## 依赖

```
python 3.11+   playwright  pyyaml  edge-tts  mutagen
ffmpeg         在 PATH 上，或设置 build.ffmpeg
Chrome/Chromium  playwright install chromium
```

## 测试

61 个测试，0.6 秒跑完，**不需要浏览器、不需要 ffmpeg**：

    python -m pip install pytest pyyaml
    python -m pytest tests/ -q

| 文件 | 数量 | 覆盖 |
|---|---|---|
| `test_lint.py` | 21 | 静态校验：元素名拼错、`say` 越界、未知步骤、打码框越界、重复 id |
| `test_run.py` | 16 | 步骤解释器：裸词步骤、修饰参数默认值、`for_each` 替换 |
| `test_build.py` | 11 | 滤镜链生成（含空打码框）、ffmpeg 探测、光标脚本契约 |
| `test_integration.py` | 9 | 计时表契约、`say` 边界、**墙钟而非帧时间**（静止页死循环回归） |
| `test_audio.py` | 4 | 音轨时长对齐：旁白过短补尾、旁白过长压缩句间停顿 |

CI 在 Ubuntu 与 Windows、Python 3.11 与 3.12 上跑同一套测试，并额外执行
`demorec.py lint examples/todomvc` 与 `compileall`。

**测试刻意不依赖 Playwright 与 ffmpeg** —— 有两条守护测试专门断言这点，
防止有人把浏览器导入挪到模块顶层。

# 换一个项目要改什么

1. `demorec.yaml` —— 站点根地址、viewport、语音、打码区
2. `pages.yaml` —— 页面地址 + 语义元素名（这是主要工作量）
3. `scenes.yaml` —— 旁白与分镜步骤

**不需要写 Python。** `examples/todomvc/` 就是这样一个纯 YAML 工程，`demorec.py run` 可直接跑通，可对照。

## 已知限制

- 需要能访问目标站点，没有离线模式。
- 录制是真实时长，9 分钟的片要录约 15 分钟。
- 打码区探测只给建议，**必须人工看截图确认**：框小了是静默泄漏，不会报错。
- 只做网页；桌面程序的录屏不在范围内。

细节见 `SKILL.md`，坑见 `references/pitfalls.md`。
