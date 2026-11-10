#!/usr/bin/env python3
"""歌词校验：押韵、句长、字数、AI 味、直白情绪句。

用法：
    python3 check_lyrics.py 歌词定稿.md
    python3 check_lyrics.py 歌词定稿.md --min-rate 0.6 --max-len 11 --min-total 250

输入：带段落标签的歌词文件，标签写成 [Verse 1] 或 【主歌】。
如果文件里有 ``` 代码块，只检查第一个含标签的代码块；没有代码块就检查整个文件。
依赖：pypinyin（pip3 install --user pypinyin）。
脚本只做可计算的检查，提示仅供参考，最终由人判断。
输出末尾有「读音风险」清单：全词里容易被 AI 唱错的多音字，生成后重点听这几句。
"""
import argparse
import re
import sys
from collections import Counter

try:
    from pypinyin import pinyin, Style
except ImportError:
    sys.exit("缺少 pypinyin，请先运行：pip3 install --user pypinyin")

# 韵母 → 韵组。i 与 ü 按一七辙算同组；en/in、eng/ing/ong 现代听感不同，分开。
GROUPS = {}
for name, finals in {
    "a": "a ia ua",
    "o/e/uo": "o e uo",
    "ie/üe": "ie ve",
    "i/ü": "i v",
    "er": "er",
    "ai": "ai uai",
    "ei/ui": "ei uei",
    "ao": "ao iao",
    "ou/iu": "ou iou",
    "an": "an ian uan van",
    "en/un": "en uen",
    "in/ün": "in vn",
    "ang": "ang iang uang",
    "eng": "eng ueng",
    "ing": "ing",
    "ong": "ong iong",
    "u": "u",
}.items():
    for f in finals.split():
        GROUPS[f] = name

# 不检查押韵的段落（前奏、间奏、尾声、念白）
SKIP_KEYS = ("intro", "interlude", "outro", "spoken", "前奏", "间奏", "尾声", "吟唱", "念白")
VERSE_KEYS = ("verse", "主歌")

# 句尾常见的轻声、语气字和多音字，押韵结果需要人工复核
UNSURE_END_CHARS = set("了的着吧啊呢吗嘛呀哇么得为还行都长重好")

# 容易被 AI 唱错的多音字：(常见正确读法, 容易错的读法)。
# 的/了/着/得/地 等太常见，已由句尾检查覆盖，这里不列。
RISKY_READINGS = {
    "咽": ("yàn", "yān"), "攥": ("zuàn", "zuān"), "转": ("zhuàn", "zhuǎn"), "折": ("zhé", "shé"),
    "传": ("chuán", "zhuàn"), "长": ("cháng", "zhǎng"), "重": ("zhòng", "chóng"), "行": ("xíng", "háng"),
    "难": ("nán", "nàn"), "少": ("shǎo", "shào"), "觉": ("jué", "jiào"), "乐": ("lè", "yuè"),
    "藏": ("cáng", "zàng"), "和": ("hé", "hè"), "载": ("zǎi", "zài"), "朝": ("zhāo", "cháo"),
    "角": ("jiǎo", "jué"), "弹": ("tán", "dàn"), "晃": ("huǎng", "huàng"), "露": ("lù", "lòu"),
    "薄": ("báo", "bó"), "模": ("mó", "mú"), "差": ("chà", "chā"), "曲": ("qǔ", "qū"),
    "尽": ("jìn", "jǐn"), "挣": ("zhèng", "zhēng"), "血": ("xuè", "xiě"), "种": ("zhǒng", "zhòng"),
    "降": ("jiàng", "xiáng"),
}

TAG_RE = re.compile(r"^\s*[\[【]([^\]】]+)[\]】]\s*$")
CJK_RE = re.compile(r"[一-鿿]")

EMOTION_WORDS = ["心痛", "心碎", "心酸", "难过", "伤心", "悲伤", "痛苦", "孤独", "寂寞", "思念", "想念", "遗憾", "绝望"]
GRAND_WORDS = ["永远", "永恒", "无尽", "无限", "生生世世", "海枯石烂"]
ABSTRACT_WORDS = ["回忆", "岁月", "青春", "时光", "宛如", "缱绻", "蓦然", "刻骨铭心"]
IDIOMS = ["刻骨铭心", "海枯石烂", "天长地久", "魂牵梦萦", "撕心裂肺", "千山万水", "朝思暮想", "物是人非", "沧海桑田", "心如刀割"]
PLAIN_FEELING = [
    r"我(很|好|真的|太)(难过|伤心|痛苦|孤独|寂寞|想你|爱你)",
    r"我(难过|伤心|痛苦|孤独|寂寞)",
    r"我爱你",
    r"我们都没有错",
    r"(一定|肯定)很(心碎|难过|痛)",
    r"心(碎|痛)了?",
]


def cjk_len(s):
    return len(CJK_RE.findall(s))


def clean_line(s):
    return re.sub(r"[\s,，.。!！?？、;；:：…\"“”'‘’—\-]+", "", s)


def extract_block(text):
    """有代码块时，取第一个含段落标签的代码块。"""
    parts = re.split(r"^```.*$", text, flags=re.M)
    blocks = parts[1::2]
    for b in blocks:
        if any(TAG_RE.match(l) for l in b.splitlines()):
            return b
    return text


def parse(text):
    sections = []  # [(tag, [lines])]
    cur = ("(未标注)", [])
    for raw in extract_block(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        m = TAG_RE.match(line)
        if m:
            if cur[1]:
                sections.append(cur)
            cur = (m.group(1).strip(), [])
            continue
        if line.startswith(("#", ">", "---", "|")):
            continue
        if re.match(r"^[（(].*[）)]$", line):  # 整行括号 = 表演指令
            continue
        if cjk_len(line) == 0:
            continue
        cur[1].append(line)
    if cur[1]:
        sections.append(cur)
    # 同名标签出现多次时编号（Chorus #1/#2/#3），方便在提示里区分
    names = Counter(t for t, _ in sections)
    seen = Counter()
    out = []
    for t, ls in sections:
        if names[t] > 1:
            seen[t] += 1
            t = f"{t} #{seen[t]}"
        out.append((t, ls))
    return out


def reading_risks(sections):
    """扫描全词里的多音字，返回 [(字, 词典读法, 易错读法, [所在句...])]。"""
    found = {}
    for tag, lines in sections:
        for line in lines:
            hans = "".join(ch for ch in line if CJK_RE.match(ch))
            if not hans:
                continue
            reads = [r[0] for r in pinyin(hans, style=Style.TONE)]
            for i, ch in enumerate(hans):
                if ch in RISKY_READINGS and i < len(reads):
                    d = found.setdefault(ch, {"read": reads[i], "lines": []})
                    if line not in d["lines"]:
                        d["lines"].append(line)
    out = []
    for ch, d in found.items():
        out.append((ch, d["read"], "/".join(RISKY_READINGS[ch]), d["lines"]))
    return out


def end_final(line):
    c = [ch for ch in clean_line(line) if CJK_RE.match(ch)]
    if not c:
        return None, None
    ch = c[-1]
    fin = pinyin(ch, style=Style.FINALS)[0][0]
    return ch, fin


def is_skip(tag):
    t = tag.lower()
    return any(k in t for k in SKIP_KEYS)


def is_verse(tag):
    t = tag.lower()
    return any(k in t for k in VERSE_KEYS)


def main():
    ap = argparse.ArgumentParser(description="歌词校验")
    ap.add_argument("file")
    ap.add_argument("--min-rate", type=float, default=0.8, help="段内最低押韵率，民谣可用 0.6，默认 0.8")
    ap.add_argument("--max-len", type=int, default=11, help="单句最大字数，默认 11")
    ap.add_argument("--min-total", type=int, default=250, help="全曲最低字数，默认 250")
    ap.add_argument("--speed", type=float, default=1.3, help="估算时长用的每秒字数，默认 1.3")
    args = ap.parse_args()

    text = open(args.file, encoding="utf-8").read()
    sections = parse(text)
    if not sections:
        sys.exit("没有解析到歌词。请确认歌词里有 [Verse 1] 或 【主歌】 这样的段落标签。")

    problems = []  # (级别, 说明)  级别：必改 / 建议
    total = 0
    all_lines = []
    print(f"文件：{args.file}\n")
    print("== 逐段 ==")
    for tag, lines in sections:
        lens = [cjk_len(l) for l in lines]
        total += sum(lens)
        all_lines += [clean_line(l) for l in lines]
        head = f"[{tag}] {len(lines)} 句，字数 {'/'.join(map(str, lens))}"
        if is_skip(tag):
            print(head + "（不检查押韵）")
            continue
        ends = [end_final(l) for l in lines]
        groups = [GROUPS.get(f, f"?{f}") if f else None for _, f in ends]
        cnt = Counter(g for g in groups if g)
        main_g, main_n = cnt.most_common(1)[0] if cnt else (None, 0)
        rate = main_n / len(lines) if lines else 0
        detail = " ".join(f"{c}({f})" for (c, f) in ends if c)
        mark = "✓" if rate >= args.min_rate else "✗"
        print(f"{head}\n   句尾：{detail}\n   主韵：{main_g}，押韵率 {main_n}/{len(lines)} = {rate:.0%} {mark}")
        if rate < args.min_rate:
            problems.append(("必改", f"[{tag}] 押韵率 {rate:.0%} 低于 {args.min_rate:.0%}（主韵 {main_g}）"))
        # 相近但不同的韵组混用
        close = [{"an", "ang"}, {"en/un", "eng"}, {"in/ün", "ing"}, {"ong", "eng"}]
        present = set(cnt)
        for pair in close:
            if pair <= present:
                problems.append(("必改", f"[{tag}] 同段混用 {' 与 '.join(sorted(pair))}，现代听感不押，请统一"))
        # 句尾是轻声/语气字或常见多音字：脚本按词典读音算，实际唱法可能不同
        shaky = [c for c, _ in ends if c and c in UNSURE_END_CHARS]
        if shaky:
            problems.append(("建议", f"[{tag}] 句尾有轻声/多音字：{'、'.join(sorted(set(shaky)))}。脚本按词典读音算，实际唱法可能不同（如「了」常唱成 liǎo），请人工核对这几句的押韵"))
        # 句尾字重复
        chars = Counter(c for c, _ in ends if c)
        rep = [c for c, n in chars.items() if n >= 2]
        if rep:
            problems.append(("建议", f"[{tag}] 句尾字重复：{'、'.join(rep)}（算押韵，但如果不是有意的会显得词穷）"))
        # 句长
        long_ = [(i + 1, n) for i, n in enumerate(lens) if n > args.max_len]
        if long_:
            problems.append(("必改", f"[{tag}] 第 {', '.join(str(i) for i, _ in long_)} 句超过 {args.max_len} 字（{', '.join(str(n) for _, n in long_)}），慢歌里容易被赶着唱，请在气口拆开"))
        if is_verse(tag) and lens and max(lens) - min(lens) > 6:
            problems.append(("建议", f"[{tag}] 句长落差较大（{min(lens)}–{max(lens)} 字）"))
        # AI 味
        body = "\n".join(lines)
        if len(re.findall(r"像.{1,8}?一样", body)) >= 2:
            problems.append(("必改", f"[{tag}] 「像……一样」出现 2 次以上"))
        emo = [w for w in EMOTION_WORDS if w in body]
        if len(emo) >= 2:
            problems.append(("必改", f"[{tag}] 情感词堆砌：{'、'.join(emo)}，只留一个，其余换成动作"))
        # 连续同起句
        starts = [clean_line(l)[:2] for l in lines]
        for i in range(len(starts) - 2):
            if starts[i] == starts[i + 1] == starts[i + 2]:
                problems.append(("建议", f"[{tag}] 连续 3 句都以「{starts[i]}」开头，若不是有意排比，请变换句式"))
                break
        for l in lines:
            for pat in PLAIN_FEELING:
                if re.search(pat, l):
                    problems.append(("建议", f"[{tag}] 「{l}」是直接说情绪，试着换成一个动作或细节"))
                    break

    full = "\n".join(all_lines)
    for w in GRAND_WORDS:
        if w in full:
            problems.append(("建议", f"全曲出现「{w}」，大词容易空，考虑换成具体画面"))
    for w in ABSTRACT_WORDS:
        if w in full:
            problems.append(("建议", f"全曲出现抽象词「{w}」，能不能换成一个具体的东西"))
    idi = [w for w in IDIOMS if w in full]
    if len(idi) >= 2:
        problems.append(("建议", f"成语偏多：{'、'.join(idi)}"))

    # 钩子：重复 3 次以上的句子
    cnt_lines = Counter(all_lines)
    hooks = [(l, n) for l, n in cnt_lines.items() if n >= 3 and len(l) >= 4]
    print("\n== 全曲 ==")
    print(f"总字数 {total}，按 {args.speed} 字/秒约 {total / args.speed / 60:.1f} 分钟")
    if hooks:
        print("重复 3 次以上的句子：" + "；".join(f"{l}×{n}" for l, n in hooks))
    else:
        print("没有重复 3 次以上的整句（副歌如果靠重复做钩子，请确认钩子在哪里）")
    if total > 420:
        problems.append(("建议", f"总字数 {total}，偏多；慢歌建议 250–420 字"))
    if total < args.min_total:
        problems.append(("建议", f"总字数 {total}，低于 {args.min_total}，慢歌可能不到 3 分钟；短歌可用 --min-total 调低"))

    print("\n== 问题 ==")
    if not problems:
        print("没有发现需要处理的问题。")
    for lv in ("必改", "建议"):
        items = [d for l, d in problems if l == lv]
        if items:
            print(f"【{lv}】")
            for d in items:
                print(f" - {d}")
    risks = reading_risks(sections)
    if risks:
        print("\n== 读音风险（生成后重点听这几句）==")
        print("（词典的读法自己也可能错，以你想要的读音为准；听生成结果时核对这几句）")
        for ch, now, both, ls in risks:
            shown = "；".join(ls[:2]) + ("…" if len(ls) > 2 else "")
            print(f" - 「{ch}」有两种读法 {both}，词典此处读 {now}：{shown}")
    print("\n注：i 与 ü 按同一辙计算；本脚本只检查可计算的部分，意象、情绪、事实需要人来判断。")


if __name__ == "__main__":
    main()
