# 从模板开始一个新项目

1. 新建一个工程目录，把这三个文件拷进去：

   ```
   demorec.yaml   # 画面、语音、节奏、打码
   pages.yaml     # 页面地址 + 语义元素名
   scenes.yaml    # 旁白 + 分镜步骤
   ```

2. 先在 `demorec.yaml` 里写好 `root_url`，在 `pages.yaml` 里写好第一个页面。

3. 探测打码区（有品牌区才需要）：

   ```
   python scripts/demorec.py probe <工程目录>
   ```

   看 `shots/probe_*.png` 确认范围，把并集填进 `mask.boxes`。

4. 校验选择器 —— **录之前一定要跑**：

   ```
   python scripts/demorec.py dry <工程目录>
   ```

   它真实走完导航与点击，选择器坏了会在几秒内报错，而不是等录完十分钟才发现。

5. 录：

   ```
   python scripts/demorec.py run <工程目录>
   ```

   等价于依次执行 tts → record → audio → build。

6. 抽帧自检：

   ```
   ffmpeg -ss 3 -i out/<output_name> -frames:v 1 check.png
   ```

   确认打码盖住、无水印、无浏览器边框。

参考实现见 `examples/todomvc/`：两幕公开示例（Playwright TodoMVC），全部是 YAML，可直接跑通对照。
