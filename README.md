# 隐藏天赋发现 · Hidden Talent Finder

一个给 AI 助手用的 Skill：用 46 道选择题（约 12 分钟，全程点按钮，不用打字），帮人看见自己没意识到的天赋。

答完得到：

- 一个带名字的画像，和一句话描述（例如“定调者”）
- 最意外的一点、让你来劲的发动机、你的本事、你的底色、要留意的地方
- 3 到 5 个适合的职业、4 座适合的城市（只列名字）
- 一款“奶茶人格”（16 款之一）和一张可以发朋友圈的分享图
- 一份手机上好读的报告（自包含 HTML）；所有题号依据折叠在最后的附录里

报告只放结论，不放推导。它不是心理诊断，不预测成败，也不用于招聘或筛选。

## 效果

![分享图示例](examples/preview.jpg)

`examples/` 里有一份虚构人物的示例：

- `examples/示例-隐藏天赋报告.html`：完整报告，下载后用浏览器打开
- `examples/preview.jpg`：分享图的缩略预览（实际生成的是 1080×1440 的 PNG）
- `examples/sample-result.json`：生成它们用的结果文件

自己生成：`python3 scripts/hidden_talent.py render examples/sample-result.json --out out --png`

## 怎么用

这个目录就是一个标准的 Skill（入口是 `SKILL.md`）。把整个目录放进你的 AI 助手的 skills 目录里，然后对助手说“帮我测测隐藏天赋”即可。

例如在 Claude Code 里：

```bash
git clone https://github.com/yyue5578-coder/hidden-talent-finder ~/.claude/skills/hidden-talent-finder
```

其他支持 Skill 的助手（包括 Cindy），按它们各自的方式导入这个目录。

### 运行环境

| 需要 | 说明 |
|---|---|
| Python 3.9 及以上（在 3.9 上测试过） | 只用标准库，不用 `pip install` |
| Chrome、Edge 或 Chromium（可选） | 只用来导出分享图 PNG。没有也能出报告 HTML。找不到时可以用环境变量 `CHROME_PATH` 指到它 |

### 答题界面

- 支持 `cindy-ui` 组件的界面（如 Cindy）：每题是按钮，选完一段点“发送”。
- 其他界面（终端、外部聊天）：用文字版，助手会把题目贴出来，你回 `17B 18A …`。

### 单独用脚本

```bash
python3 scripts/hidden_talent.py ask 1 --text      # 第 1 段题目（文字版）
python3 scripts/hidden_talent.py score "<46个字母>" --text   # 算分摘要
python3 scripts/hidden_talent.py render result.json --out out --png   # 生成报告和分享图
python3 scripts/hidden_talent.py simulate           # 随机作答 2000 组，看各类型和城市的分布
```

写画像和结论的部分由 AI 助手完成（规则在 `references/reframes.md` 和 `references/advice.md`），脚本负责出题、计分和排版。

## 目录

```
SKILL.md                 助手读的主流程
scripts/hidden_talent.py 题库、计分、报告和分享图（单文件）
references/              题库全文、写法规则、16 款奶茶人格、城市印象库
examples/                虚构的完整示例
```

## 隐私

答案和报告只在运行它的那台电脑上，脚本不联网，也不上传任何内容。

## 已知局限

- 城市库里的特点只是常识印象，没有联网核实，不是建议搬家。
- 题目用中文，针对中文语境的成长经历设计。
- 随机乱答也会算出一些结论，所以脚本有一致性检查：几乎全选同一个字母、按规律点、换说法再问的题前后对不上，都会降低可信度，严重时不出报告。
- 名字和类型是“目前的样子”，不是定论。

## 许可证

[PolyForm Noncommercial 1.0.0](LICENSE)：允许个人学习、研究、非商业使用和分享（需保留许可证和署名），**不允许商业使用**。这不是 OSI 意义上的开源许可证。如需商业使用，请联系作者。
