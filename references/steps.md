# Step 参考

每条 step 是一个单词 + 可选修饰。整条剧本由 `scripts/run.py` 解释，
新增语法必须同时改解释器与本文档。

| 步骤 | 作用 | 修饰参数 |
|---|---|---|
| `goto: <page>` | 打开 `pages.yaml` 里的页面并等待就绪 | — |
| `start` | 开始 CDP 抓帧录制 | — |
| `stop` | 停止录制并编码为 mp4 | — |
| `say: N` / `say: [N, extra]` | 等到本幕第 N 句旁白念完（可再加 extra 秒） | `extra` |
| `wait: T` | 等到录制开始后第 T 秒（绝对时间） | — |
| `sleep: S` | 相对等待 S 秒（按录制时钟） | — |
| `move: <target>` | 光标平滑移动过去 | `dur` |
| `click: <target>` | 移动 → 停顿 → 按下 → 抬起 | `hover` `after` `dur` |
| `hover: <target>` | 移动过去并停留 | `hold` `dur` |
| `type: <text>` | 真人节奏输入到当前焦点 | `cps` |
| `key: <combo>` | 按键，如 `Enter` / `Control+A` | — |
| `scroll: <dy>` | 平滑滚轮滚动（正数向下） | `steps` `settle` |
| `shot: <name>` | 存一张 PNG 到 `shots/` 供人工复核 | — |
| `for_each: {over: [...], do: [...]}` | 对一组坐标循环执行子步骤 | — |

## 目标写法

优先级从高到低：

1. `{el: name}` —— `pages.yaml` 里的语义名。**首选**，站点改版只改选择器表。
2. `{sel: "css 或 playwright 选择器"}` —— 一次性、不值得命名的临时目标。
3. `{at: [x, y]}` —— 画面绝对像素。**最后手段**：布局一变就失效，也是
   "换一个项目就得重写剧本" 的主要成因。

## 为什么要用 say 而不是秒数

```yaml
- click: {el: role_button}
- say: 3          # 而不是 - sleep: 7.2
```

旁白改成更长的句子时，`say` 会自动跟着变；`sleep: 7.2` 会让动作和声音错位，
而错位在成片里才看得出来，返工成本很高。
