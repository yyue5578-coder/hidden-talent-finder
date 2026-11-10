# Suno 版提示词

> 界面和功能会更新，以 Suno 当时的实际界面为准。
> 已实测：「中速抒情」这一档用在一首中文歌上，能出歌，效果可接受。其余两档和念白写法**尚未逐项验证**，生成后请按 `check.md` 听。

Suno 选 **Custom Mode**，有三个框：**Style of Music**（曲风）、**Exclude Styles**（排除项）、**Lyrics**（歌词）。

## 零、先问声音

问用户：**想要男声还是女声？**（没偏好就问"歌里的'我'听起来像谁在唱"，让用户选）。**不要根据歌里人物的姓名、称呼去推断性别。** 下面的 Style 默认写女声，选男声就按「按需调整」那张表换。

## 一、先让用户选一档（用人话描述）

| 档位 | 对用户怎么说 | 适合 |
|---|---|---|
| **A. 中速抒情**（默认） | 钢琴和吉他，温柔，慢慢往前走，像在跟你说话 | 大多数怀念、想念类 |
| **B. 安静民谣** | 只有吉他，很轻很近，像耳边说话，几乎没有鼓 | 克制、放下、不甘心但不吵 |
| **C. 影视感** | 钢琴加弦乐，厚一点，像电影片尾曲 | 想要更大的情绪 |

## 二、Style of Music（按档位填）

**A. 中速抒情**
```
Mandopop ballad, solo female vocal, warm and slightly husky tone,
piano and fingerpicked acoustic guitar, cello enters at the second chorus,
light brush drums from the second verse only, 78 BPM,
restrained and conversational, clear Mandarin diction, no belting
```

**B. 安静民谣**
```
Chinese folk ballad, solo female vocal, fingerpicked acoustic guitar only,
cello from the bridge, no drums, 70 BPM,
intimate close-mic vocal, restrained, almost spoken in the verses, clear Mandarin diction
```

**C. 影视感**
```
Cinematic Mandopop ballad, solo female vocal, piano and strings,
subtle ambient texture, 74 BPM, wide but quiet arrangement,
emotional restraint, clear Mandarin diction
```

### 按需调整的几个词

| 想要 | 改成 |
|---|---|
| 男声 | `solo female vocal` 换成 `solo male vocal`，Exclude 里的 `male vocal` 删掉，加上 `female vocal` |
| 更素 | 去掉 `piano` |
| 更满 | `cello` 换成 `strings` |
| 更像流行 | `78 BPM` 调到 84 |
| 更像民谣 | `78 BPM` 调到 68 |

## 三、Exclude Styles

```
EDM, trap, rap, heavy drums, rock guitar, autotune, choir, duet,
big key change, epic build, belting, English pronunciation
```

> 性别要和 Style 里一致：选女声就加 `male vocal`，选男声就加 `female vocal`。
> `duet` 必须保留，否则副歌里喊名字时它可能自动加一个应答的声音。

## 四、Lyrics

1. **段落标签必须是英文方括号**，中文标签它不认：
   `[Intro] [Verse 1] [Pre-Chorus] [Chorus] [Verse 2] [Bridge] [Interlude] [Outro]`
2. 把定稿歌词按结构贴进去，每段前面加标签。
3. 每行 4–11 个字。超过 11 字的句子，AI 容易赶。
4. 想让某个词前后有一点停顿，在词后面多留一个空格。

### 念白（不唱、只说）怎么写

在标签下面，用括号写表演指令，再写词：

```
[Interlude]
(whispered, spoken word, no melody, very quiet, breathy, close mic)
名字 名字 名字
```

```
[Outro]
(spoken, almost not sung, no melody)
最后一句话
```

- `no melody` 最关键，少了它 Suno 会自动配旋律。
- 结尾用 `almost not sung`，比 `spoken` 更像"话说到最后没气了"。

## 五、生成后的第一次听

一次让它生成两版，对照 `check.md` 的三处检查。
有问题，用 **Replace Section** 只换那一段；结尾被硬切，用 **Extend** 补两小节尾奏。

## 六、输出格式

声音按用户选的填。给用户时，按三块分开，每块一个代码框，写好"复制到哪个框"：

```
【复制到 Style of Music】
……
【复制到 Exclude Styles】
……
【复制到 Lyrics】
……
```
