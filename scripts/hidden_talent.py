#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隐藏天赋发现 v0.4：题库、计分（8 项能力 × 来劲 / 做得好 / 做完累 / 用得少）、小时候的水土、
同频与补位城市、一致性检查，生成手机报告 HTML 与分享图 PNG。

用法：
  python3 hidden_talent.py ask 1                 # 第 1 段的按钮答题卡（cindy-ui），原样发出；共 6 段
  python3 hidden_talent.py ask 1 --text          # 纯文字版（对方的界面不显示按钮时用）
  python3 hidden_talent.py check 1 "第1段：1A 2B…"  # 核对某一段的回复
  python3 hidden_talent.py score "<46 个字母或 1A 2B…>" [--text]
  python3 hidden_talent.py render result.json --out ./documents --prefix 2026-11-09 [--png]
  python3 hidden_talent.py questions --md > ../references/questions.md
  python3 hidden_talent.py simulate --n 2000 --seed 7

题库只在本文件的 BANK 里维护，城市印象在 references/cities.json。仅依赖 Python 标准库；导出 PNG 需要本机装有 Chrome、Edge 或 Chromium 之一。
"""
import argparse
import html
import json
import os
import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter

VERSION = "0.5"
HERE = os.path.dirname(os.path.abspath(__file__))
TYPES_PATH = os.path.join(HERE, "..", "references", "types.json")
CITIES_PATH = os.path.join(HERE, "..", "references", "cities.json")
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge", "msedge"]
FONT = '"Yuanti SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC","WenQuanYi Micro Hei",sans-serif'
BODY_FONT = '-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC","Helvetica Neue",sans-serif'
LEVELS = ["低", "中", "高"]

AXES = [
    {"name": "起点", "p1": "开拓", "p2": "深耕", "c1": "开", "c2": "深"},
    {"name": "对象", "p1": "人", "p2": "物", "c1": "人", "c2": "物"},
    {"name": "节奏", "p1": "快反馈", "p2": "长周期", "c1": "快", "c2": "长"},
    {"name": "方式", "p1": "独立", "p2": "协同", "c1": "独", "c2": "合"},
]
SIDE_DESC = {
    0: {"开": "想不断开新的局", "深": "想把一件事磨透"},
    1: {"人": "先看人的感受", "物": "先看事和结构"},
    2: {"快": "要马上有结果", "长": "愿意慢慢养"},
    3: {"独": "想自己搞定", "合": "习惯一起商量"},
}
CLASH_TIPS = [
    "分工：开头交给开拓的人，收尾交给深耕的人。",
    "重要决定前，先聊事实，再聊感受，两件事都留出时间。",
    "先约定一个小里程碑：让快的人有结果，让慢的人不被催。",
    "给协同的人一个固定的同步时间，让独立的人保留自己的空档。",
]

# ---------------------------------------------------------------- 8 项能力
ABILITIES = {
    "insight": {"name": "看出门道", "line": "别人还没察觉，你先看出哪里不对、哪里有机会",
                "scenes": ["科技", "咨询", "金融"], "roles": "研究、分析、产品、用户洞察"},
    "ideas": {"name": "冒出点子", "line": "从无到有想出新办法",
              "scenes": ["设计", "内容", "科技"], "roles": "创意、策划、产品构思、内容选题"},
    "judge": {"name": "拍板判断", "line": "在一堆选项里看出哪个能成",
              "scenes": ["金融", "咨询", "商贸"], "roles": "决策支持、选品、投资、把关"},
    "rally": {"name": "拉人起势", "line": "让一群人动起来",
              "scenes": ["商贸", "电商", "文旅"], "roles": "社群、销售、活动、带团队"},
    "care": {"name": "读人照顾", "line": "读懂情绪，给人恰好的支持",
             "scenes": ["生活服务", "教育", "文旅"], "roles": "陪伴咨询、用户运营、教育、服务"},
    "order": {"name": "理顺落地", "line": "把乱的排成步骤，推到完成",
              "scenes": ["制造", "电商", "商贸"], "roles": "项目统筹、运营、供应链"},
    "craft": {"name": "磨到极致", "line": "把细节做到经得起看",
              "scenes": ["手艺", "设计", "制造"], "roles": "设计、品控、编辑、手艺"},
    "voice": {"name": "讲清讲透", "line": "把复杂的事说成别人能懂、愿意传的话",
              "scenes": ["内容", "教育", "演出"], "roles": "内容创作、讲解培训、文案"},
}
AB_ORDER = ["insight", "ideas", "judge", "rally", "care", "order", "craft", "voice"]
KIND_NAME = {"style": "风格题", "water": "水土题", "perf": "做得好", "energy": "来劲",
             "drain": "做完累", "unused": "用得少", "repeat": "重复题"}
ABILITY_KINDS = ("perf", "energy", "drain", "unused")

# ---------------------------------------------------------------- 题库（46 题，6 段）
# style/repeat(风格): axis, p1   water: key, val(字母->分)；terrain 用 val 存地貌
# perf/energy/drain/unused/repeat(能力): map(字母->能力)   tb: 给某个维度投 1 票(字母->一侧)，只用意思明确的情境题
BANK = [
    # ---- 第 1 段
    {"id": 1, "kind": "style", "axis": 0, "p1": "A", "topic": "新项目刚启动",
     "q": "新项目刚启动，一片空白。你更兴奋的是：",
     "opts": {"A": "从零开始定方向、画下第一笔", "B": "接手一个有雏形的，把它做到极致"}},
    {"id": 2, "kind": "perf", "topic": "逛一家新店", "q": "朋友拉你去一家刚开的新店，你第一眼最先注意到的是：",
     "opts": {"A": "哪里不对劲、还能更好", "B": "要是我来做，会怎么改", "C": "这生意到底能不能做下去", "D": "店员和客人之间的气氛"},
     "map": {"A": "insight", "B": "ideas", "C": "judge", "D": "care"}},
    {"id": 3, "kind": "water", "key": "stable", "topic": "小时候的晚饭", "q": "小时候，家里的晚饭通常是：",
     "opts": {"A": "每天差不多同一时间，一家人一起吃", "B": "看大人忙不忙，时早时晚", "C": "经常各吃各的", "D": "记不清了"},
     "val": {"A": 1, "B": -1, "C": -1}},
    {"id": 4, "kind": "energy", "topic": "十岁时最常玩的", "q": "十岁左右，你最常玩的是：",
     "opts": {"A": "当孩子王，组织大家一起玩", "B": "拆东西、搭东西、做手工", "C": "编故事、给人讲故事", "D": "照顾小动物或更小的孩子"},
     "map": {"A": "rally", "B": "craft", "C": "voice", "D": "care"}},
    {"id": 5, "kind": "style", "axis": 1, "p1": "B", "topic": "周末半天",
     "q": "周末有半天空闲，你更可能：",
     "opts": {"A": "一个人研究点东西，搞明白它怎么运转", "B": "约人聊天或组个局，听别人的故事"}},
    {"id": 6, "kind": "perf", "topic": "嘉宾临时来不了", "q": "活动开始前一小时，主讲嘉宾说来不了了。你的第一反应：",
     "opts": {"A": "马上把剩下的流程重排一遍", "B": "站出来跟大家说明情况，把场子稳住", "C": "想一个替代的节目顶上", "D": "先看谁最慌，过去安抚一下"},
     "map": {"A": "order", "B": "rally", "C": "ideas", "D": "care"}},
    {"id": 7, "kind": "water", "key": "terrain", "topic": "长大的地方", "q": "你长大的地方，出门最常看见的是：",
     "opts": {"A": "山", "B": "江、河、湖或海", "C": "一大片平地或农田", "D": "楼和马路"},
     "val": {"A": "山", "B": "水", "C": "平原", "D": "城"}},
    {"id": 8, "kind": "style", "axis": 2, "p1": "A", "topic": "喜欢的节奏",
     "q": "你更喜欢的工作节奏：",
     "opts": {"A": "一天里能看到好几次结果和反馈", "B": "沉下去几个月，最后拿出一件分量很重的东西"}},
    # ---- 第 2 段
    {"id": 9, "kind": "perf", "topic": "朋友最常找你干什么", "q": "朋友最常因为什么事来找你？",
     "opts": {"A": "帮忙拿主意：该不该做、选哪个", "B": "帮忙改东西：修图、改文案、调细节", "C": "帮忙出面：去谈、去说、去张罗", "D": "找你聊心事"},
     "map": {"A": "judge", "B": "craft", "C": "rally", "D": "care"}},
    {"id": 10, "kind": "energy", "topic": "怎样算“值了”", "q": "同样忙了一整天，哪种结尾最让你觉得“值了”？",
     "opts": {"A": "想出一个以前没人想到的点子", "B": "把一团乱麻理顺，全部交了出去", "C": "有人跟我说“多亏有你”", "D": "我说的话、写的东西被很多人转发"},
     "map": {"A": "ideas", "B": "order", "C": "care", "D": "voice"}},
    {"id": 11, "kind": "style", "axis": 3, "p1": "B", "topic": "攻克大问题",
     "q": "遇到需要攻克的大问题，你更想：",
     "opts": {"A": "拉几个人一起碰", "B": "一个人关起门想透"}},
    {"id": 12, "kind": "water", "key": "stable", "topic": "换过几次学校", "q": "上小学到初中，你换过几次学校或搬过几次家？",
     "opts": {"A": "没换过", "B": "一次", "C": "两次或更多", "D": "记不清了"},
     "val": {"A": 1, "B": 0, "C": -1}},
    {"id": 13, "kind": "perf", "topic": "帮人看一份东西", "q": "朋友请你帮忙看一份要交的东西（简历、方案、文案），你最先动手改的是：",
     "opts": {"A": "错字、格式、没对齐的地方", "B": "整体顺序：先说什么，后说什么", "C": "几句关键的话，让它更打动人", "D": "它到底要打动谁、那个人在乎什么"},
     "map": {"A": "craft", "B": "order", "C": "voice", "D": "insight"}},
    {"id": 14, "kind": "energy", "topic": "大人怎么说小时候的你", "q": "小时候，大人最常说你：",
     "opts": {"A": "“这孩子主意多”", "B": "“这孩子什么都要问为什么”", "C": "“这孩子做事有条理”", "D": "“这孩子挺有主见”"},
     "map": {"A": "ideas", "B": "insight", "C": "order", "D": "judge"}},
    {"id": 15, "kind": "style", "axis": 0, "p1": "A", "topic": "进入重复优化",
     "q": "一件事进入“重复优化”阶段，你会：",
     "opts": {"A": "有点坐不住，想找下一个新东西", "B": "反而更来劲，越磨越有味道"}},
    {"id": 16, "kind": "perf", "topic": "聚会没人牵头", "q": "一个小群想聚一次，但一直没人牵头。你最可能：",
     "opts": {"A": "在群里先喊一声，把时间定下来", "B": "私下问问每个人方便吗、想吃什么", "C": "默默把地点、预算、路线都查好", "D": "想个有意思的主题，让大家想来"},
     "map": {"A": "rally", "B": "care", "C": "order", "D": "ideas"}},
    # ---- 第 3 段
    {"id": 17, "kind": "water", "key": "resource", "topic": "想要不便宜的东西", "q": "小时候想要一个不便宜的东西，通常是：",
     "opts": {"A": "说一声，大多能有", "B": "要攒钱，或者等考好了当奖励", "C": "知道家里不宽裕，一般不开口", "D": "记不清了"},
     "val": {"A": 1, "B": 0, "C": -1}},
    {"id": 18, "kind": "perf", "topic": "开会没结论", "q": "开会讨论了半天没有结论，你通常会：",
     "opts": {"A": "用一句话把大家绕来绕去的东西说清楚", "B": "直接说“我觉得选这个”，再讲理由", "C": "发现大家其实在说两件不同的事", "D": "提议先散会，把分工写下来"},
     "map": {"A": "voice", "B": "judge", "C": "insight", "D": "order"}},
    {"id": 19, "kind": "energy", "topic": "忘了时间", "q": "做哪种事的时候，你最容易忘了时间？",
     "opts": {"A": "琢磨一个东西为什么会这样", "B": "一遍遍打磨一个作品", "C": "带着一群人把一件事搞起来", "D": "在几个选项之间推演、做决定"},
     "map": {"A": "insight", "B": "craft", "C": "rally", "D": "judge"}},
    {"id": 20, "kind": "style", "axis": 1, "p1": "B", "topic": "电影里打动你的",
     "q": "看电影或读书，你更容易被什么打动：",
     "opts": {"A": "设定和结构，世界是怎么运转的", "B": "人物之间的关系和情感"}},
    {"id": 21, "kind": "drain", "topic": "常被夸但做完想躺平", "q": "下面四件事，哪件你常被夸，但做完最想躺平？",
     "opts": {"A": "把一团乱的事理顺", "B": "照顾大家的情绪", "C": "把东西做得特别精细", "D": "在人前把话讲漂亮"},
     "map": {"A": "order", "B": "care", "C": "craft", "D": "voice"}},
    {"id": 22, "kind": "perf", "topic": "听得最多的夸奖", "q": "下面哪句话，你从别人那儿听得最多？",
     "opts": {"A": "“你怎么一下就看出问题了”", "B": "“你点子真多”", "C": "“经你一说我就懂了”", "D": "“交给你我就放心”"},
     "map": {"A": "insight", "B": "ideas", "C": "voice", "D": "order"}},
    {"id": 23, "kind": "perf", "topic": "到了新地方", "q": "到一个新地方（新工作、新城市），头一个月你最快摸清的是：",
     "opts": {"A": "谁说了算，事情真正是怎么运转的", "B": "哪里做得粗糙，可以做精", "C": "谁和谁合得来，谁不太开心", "D": "大家愿意听谁的，怎么把人叫动"},
     "map": {"A": "insight", "B": "craft", "C": "care", "D": "rally"},
     "tb": {"axis": 1, "side": {"A": "物", "B": "物", "C": "人", "D": "人"}}},
    # ---- 第 4 段
    {"id": 24, "kind": "water", "key": "renqing", "topic": "过年过节的走动", "q": "小时候过年过节，家里的走动：",
     "opts": {"A": "一大家子亲戚，走动多，礼数也多", "B": "走几家近亲", "C": "基本就自己家过", "D": "记不清了"},
     "val": {"A": 1, "B": 0, "C": -1}},
    {"id": 25, "kind": "style", "axis": 2, "p1": "A", "topic": "学新技能",
     "q": "学一个新技能，你更享受：",
     "opts": {"A": "很快做出一个能用的小成果", "B": "慢慢把底子打好，一步步变强"}},
    {"id": 26, "kind": "energy", "topic": "做完反而更有精神", "q": "做完哪件事，你反而更有精神？",
     "opts": {"A": "办了一场把大家都带热了的活动", "B": "帮一个人想通了一件事", "C": "写完或讲完一个自己满意的东西", "D": "把一个流程从乱改到顺"},
     "map": {"A": "rally", "B": "care", "C": "voice", "D": "order"}},
    {"id": 27, "kind": "perf", "topic": "给长辈解释新东西", "q": "要给不太懂的长辈解释一个新东西（比如怎么用一个 App），你会：",
     "opts": {"A": "打个比方，几句话说明白", "B": "一步一步写下来，让 TA 照着做", "C": "先弄清 TA 到底卡在哪一步", "D": "干脆帮 TA 设置好，顺手把字调大、图标排好"},
     "map": {"A": "voice", "B": "order", "C": "insight", "D": "craft"}},
    {"id": 28, "kind": "perf", "topic": "这有什么难的", "q": "别人觉得难、你却觉得“这有什么难的”，更像是：",
     "opts": {"A": "一眼看出哪个选择更靠谱", "B": "把一个冷场带热，让大家动起来", "C": "把一件东西做到别人挑不出毛病", "D": "把一堆杂事排得明明白白"},
     "map": {"A": "judge", "B": "rally", "C": "craft", "D": "order"}},
    {"id": 29, "kind": "drain", "topic": "做得不差但一想就累", "q": "哪件事你做得不差，但一想到要做就有点累？",
     "opts": {"A": "牵头张罗，催大家动起来", "B": "帮人拿主意、做决定", "C": "想新点子、出创意", "D": "查漏补缺，挑出问题"},
     "map": {"A": "rally", "B": "judge", "C": "ideas", "D": "insight"}},
    {"id": 30, "kind": "energy", "topic": "上学时主动做的事", "q": "上学的时候，哪种课外的事你会主动去做？",
     "opts": {"A": "出黑板报、做手工作品", "B": "当班干部、组织活动", "C": "参加演讲、辩论或者写稿", "D": "帮同学讲题，听同学倾诉"},
     "map": {"A": "craft", "B": "rally", "C": "voice", "D": "care"}},
    # ---- 第 5 段
    {"id": 31, "kind": "water", "key": "renqing", "topic": "大人常挂在嘴边的", "q": "小时候在家，大人更常挂在嘴边的是：",
     "opts": {"A": "“别人会怎么看”", "B": "“你自己想清楚就行”", "C": "“先把事做完再说”", "D": "记不清了"},
     "val": {"A": 1, "B": -1, "C": 0}},
    {"id": 32, "kind": "perf", "topic": "上手比别人快的", "q": "下面哪类东西，你上手比身边人快？",
     "opts": {"A": "看懂一个行业、一款游戏的门道", "B": "写东西、说话的技巧", "C": "剪辑、修图、手工这类要手上功夫的", "D": "组织活动、带一群人"},
     "map": {"A": "insight", "B": "voice", "C": "craft", "D": "rally"}},
    {"id": 33, "kind": "style", "axis": 3, "p1": "B", "topic": "成果做出来那一刻",
     "q": "成果做出来的那一刻，你更满足于：",
     "opts": {"A": "“这是我们一起做成的”", "B": "“这是我自己做成的”"}},
    {"id": 34, "kind": "unused", "topic": "最近没机会做但手痒", "q": "下面哪件事，你最近一个月几乎没机会做，但一想到就有点手痒？",
     "opts": {"A": "从零想一个新东西", "B": "把一个东西做到极致", "C": "站出来带一群人", "D": "和一个人深聊，帮 TA 一把"},
     "map": {"A": "ideas", "B": "craft", "C": "rally", "D": "care"}},
    {"id": 35, "kind": "perf", "topic": "两个方案选一个", "q": "两个方案只能选一个，大家各执一词。你：",
     "opts": {"A": "很快看出哪个更站得住，直接说", "B": "想出第三个方案，把两边的好处合起来", "C": "把两边的理由讲清楚，让大家听懂彼此", "D": "先让每个人把顾虑说出来"},
     "map": {"A": "judge", "B": "ideas", "C": "voice", "D": "care"}},
    {"id": 36, "kind": "energy", "topic": "一整天不用为钱工作", "q": "如果有一整天不用为钱工作，你最想：",
     "opts": {"A": "研究一个一直好奇的问题", "B": "动手做个东西，做到满意", "C": "试几个新点子，看哪个能成", "D": "帮朋友把一件纠结的事理清、拿主意"},
     "map": {"A": "insight", "B": "craft", "C": "ideas", "D": "judge"}},
    {"id": 37, "kind": "repeat", "of": 9, "topic": "别人第一个想到你", "q": "身边的人遇到事，最常第一个想到你的是哪种时候？",
     "opts": {"A": "想找人倾诉的时候", "B": "要做个东西、改个细节的时候", "C": "拿不准该选哪个的时候", "D": "需要有人出面张罗的时候"},
     "map": {"A": "care", "B": "craft", "C": "judge", "D": "rally"}},
    # ---- 第 6 段
    {"id": 38, "kind": "water", "key": "duty", "topic": "小时候家里的活儿", "q": "小时候家里的活儿：",
     "opts": {"A": "我得帮着干，或者照顾弟弟妹妹", "B": "偶尔搭把手", "C": "大人包办，我管好自己就行", "D": "记不清了"},
     "val": {"A": 1, "B": 0, "C": -1}},
    {"id": 39, "kind": "perf", "topic": "最容易拿高分的作业", "q": "上学时，哪种作业或任务你最容易拿高分？",
     "opts": {"A": "作文、演讲", "B": "发散的创意题、手工制作", "C": "需要严密推理、做判断的题", "D": "小组作业里当组长、分工"},
     "map": {"A": "voice", "B": "ideas", "C": "judge", "D": "order"}},
    {"id": 40, "kind": "drain", "topic": "最想交出去的事", "q": "如果能把一件事永久交给别人做，你最想交出去的是：",
     "opts": {"A": "安抚、照顾别人的情绪", "B": "对外讲解、汇报", "C": "排期、盯进度", "D": "抠细节、反复检查"},
     "map": {"A": "care", "B": "voice", "C": "order", "D": "craft"}},
    {"id": 41, "kind": "unused", "topic": "多出一个周末想补上的", "q": "如果下个月多出一个自由的周末，你最想补上的是：",
     "opts": {"A": "一个人好好研究点东西", "B": "写点、拍点、讲点东西发出去", "C": "把生活或工作里乱的地方好好整理一遍", "D": "替自己一件拖着的大事拿个主意"},
     "map": {"A": "insight", "B": "voice", "C": "order", "D": "judge"}},
    {"id": 42, "kind": "repeat", "of": 33, "axis": 3, "p1": "A", "topic": "做成之后想听的话",
     "q": "一件重要的事做成了，你更想听到：",
     "opts": {"A": "“这是你一个人扛下来的”", "B": "“多亏大家一起”"}},
    {"id": 43, "kind": "unused", "topic": "用得太少的本事", "q": "现在的生活里，哪种本事你觉得“用得太少，有点浪费”？",
     "opts": {"A": "一眼看出问题和机会", "B": "把复杂的事讲明白", "C": "把一群人带起来", "D": "把东西做得很精"},
     "map": {"A": "insight", "B": "voice", "C": "rally", "D": "craft"}},
    {"id": 44, "kind": "repeat", "of": 10, "topic": "怎样算没白忙", "q": "一天下来，发生了哪件事你会觉得“今天没白忙”？",
     "opts": {"A": "有人跟我说“幸好有你”", "B": "我写的、说的东西被人拿去转发", "C": "冒出一个别人没想到的主意", "D": "一摊乱事被我理清、交掉了"},
     "map": {"A": "care", "B": "voice", "C": "ideas", "D": "order"}},
    {"id": 45, "kind": "style", "axis": 0, "p1": "A", "topic": "再学一样东西",
     "q": "有人愿意免费教你一样东西，你更想学：",
     "opts": {"A": "一个从没碰过的新领域", "B": "在我已经会的东西上再往深里学"}},
    {"id": 46, "kind": "style", "axis": 2, "p1": "A", "topic": "更难受的情况",
     "q": "做一件事，哪种情况更让你难受：",
     "opts": {"A": "做了好几天，还看不到任何反馈", "B": "被催着匆匆交差，没法做好"}},
]
Q = {q["id"]: q for q in BANK}
N_Q = len(BANK)
BATCHES = [(1, 8), (9, 16), (17, 24), (25, 31), (32, 38), (39, 46)]
STYLE_IDS = [q["id"] for q in BANK if q["kind"] == "style"]
AXIS_VOTERS = {ax: [q for q in BANK if (q["kind"] == "style" or (q["kind"] == "repeat" and "axis" in q)) and q.get("axis") == ax]
                  + [q for q in BANK if q.get("tb", {}).get("axis") == ax] for ax in range(len(AXES))}
NO_SKIP = {q["id"] for qs in AXIS_VOTERS.values() for q in qs}

# ---------------------------------------------------------------- 水土
WATER_LABEL = {
    ("稳", "紧"): ("稻田水土", "日子有准点，人情很近，像一年一熟的稻田：守着一块地，一家一家互相搭着"),
    ("稳", "中"): ("小院水土", "日子安稳，家门里自成一片天地"),
    ("稳", "松"): ("小院水土", "日子安稳，各家关起门过自己的日子"),
    ("变", "紧"): ("渡口水土", "日子常有变数，但身边那张人情网一直都在"),
    ("变", "中"): ("码头水土", "来来往往、常有变数，要靠自己很快站稳"),
    ("变", "松"): ("码头水土", "来来往往、常有变数，各自靠自己站稳"),
    ("中", "紧"): ("大院水土", "节奏不紧不慢，人情很浓，大家看着彼此长大"),
    ("中", "中"): ("街角水土", "不紧不慢，人情不远不近"),
    ("中", "松"): ("街角水土", "不紧不慢，各自安好，不太被人情牵着走"),
}
TERRAIN_LINE = {"山": "看着山长大", "水": "在水边长大", "平原": "在开阔的平地上长大", "城": "在楼群和马路之间长大"}
# 水土里的某个特点，可能练出了哪几项能力
ORIGINS = [
    ("stable", "变", ["care", "insight"], "日子常有变数的环境里，提前察觉变化几乎是本能"),
    ("stable", "稳", ["craft", "order"], "日子有准点的环境，适合把一件事长期磨下去"),
    ("renqing", "紧", ["care", "rally", "voice"], "人情很近的环境里，会看场合、会说话、会照顾人，都是天天在练的"),
    ("renqing", "松", ["judge", "ideas"], "各过各的环境里，凡事要自己拿主意"),
    ("duty", "顾人", ["care", "order"], "从小要搭把手、照顾人，排事情和照顾情绪是练出来的"),
    ("resource", "紧", ["judge", "order"], "东西来得不容易，自然会精打细算、先想清楚再动"),
    ("resource", "宽", ["ideas"], "被允许试错，敢冒新点子"),
    ("resource", "攒", ["craft", "judge"], "习惯先攒着、等一等，耐得住慢慢磨"),
]


# ---------------------------------------------------------------- 解析
def _norm(s):
    return unicodedata.normalize("NFKC", str(s)).upper()


def parse_answers(raw, ids=None):
    """把回复读成 {题号: 字母或 None}。接受连写字母（跳过用 -）或“1A 2B…”，前面的“第N段：”会被忽略。"""
    ids = ids or [q["id"] for q in BANK]
    s = _norm(raw)
    s = re.sub(r"第\s*\d+\s*段", " ", s)
    got, errors = {}, []
    if re.search(r"\d", s):
        for num, letter in re.findall(r"(\d+)\s*[\.、:：\)）]?\s*([A-D?？\-_])", s):
            n = int(num)
            if n not in ids:
                errors.append("第 %d 题不在这一段里" % n)
                continue
            got[n] = None if letter in "?？-_" else letter
        missing = [i for i in ids if i not in got]
        if missing:
            errors.append("没读到这些题：%s" % "、".join(str(i) for i in missing))
    else:
        letters = [c for c in s if c in "ABCD?？-_"]
        if len(letters) != len(ids):
            errors.append("需要 %d 个答案，实际读到 %d 个（跳过的题用 - 占位）" % (len(ids), len(letters)))
        for i, c in zip(ids, letters):
            got[i] = None if c in "?？-_" else c
    for i, c in sorted(got.items()):
        q = Q[i]
        if c is None:
            if i in NO_SKIP:
                errors.append("第 %d 题要用来定奶茶人格，不能跳过" % i)
            continue
        if c not in q["opts"]:
            errors.append("第 %d 题只有 %s，读到的是 %s" % (i, "/".join(q["opts"]), c))
    if errors:
        raise ValueError("；".join(errors))
    return got


def ev(i, c):
    q = Q[i]
    return "第%d题（%s）选了%s：%s" % (i, q["topic"], c, q["opts"][c])


def down(level, steps=1):
    return LEVELS[max(0, LEVELS.index(level) - steps)]


def side_of(q, c):
    a = AXES[q["axis"]]
    return a["c1"] if c == q["p1"] else a["c2"]


# ---------------------------------------------------------------- 16 型（每个维度 3 票：风格题 + 换说法的风格题或意思明确的情境题）
def vote_side(q, c):
    if q.get("tb"):
        return q["tb"]["side"][c]
    return side_of(q, c)


PCT = {3: 90, 2: 65, 1: 35, 0: 10}


def score_axes(ans):
    axes, code = [], ""
    for ax, a in enumerate(AXES):
        qs = AXIS_VOTERS[ax]
        sides = [vote_side(q, ans[q["id"]]) for q in qs]
        n1 = sum(1 for x in sides if x == a["c1"])
        win1 = n1 * 2 > len(qs)
        side = a["c1"] if win1 else a["c2"]
        pct1 = PCT.get(n1, int(round(n1 * 100.0 / len(qs))))
        code += side
        unanimous = n1 in (0, len(qs))
        axes.append({
            "name": a["name"], "p1": a["p1"], "p2": a["p2"], "pct1": pct1, "pct2": 100 - pct1,
            "winner": a["p1"] if win1 else a["p2"], "side": side,
            "lean": "鲜明" if unanimous else "略偏",
            "tiebreak": not unanimous,
            "support": [q["id"] for q, x in zip(qs, sides) if x == side],
            "questions": [q["id"] for q in qs],
            "evidence": [ev(q["id"], ans[q["id"]]) for q in qs],
        })
    return code, axes


# ---------------------------------------------------------------- 一致性
def consistency(ans):
    answered = [c for _, c in sorted(ans.items()) if c]
    letters = "".join(answered)
    n = len(letters) or 1
    top_letter, top_n = Counter(letters).most_common(1)[0] if letters else ("-", 0)
    share = top_n / float(n)
    run = best = 1
    for k in range(1, len(letters)):
        run = run + 1 if letters[k] == letters[k - 1] else 1
        best = max(best, run)
    period = 0.0
    for k in (2, 3, 4):
        if len(letters) > k:
            m = sum(1 for j in range(k, len(letters)) if letters[j] == letters[j - k])
            period = max(period, m / float(len(letters) - k))
    repeats = []
    for q in BANK:
        if q["kind"] != "repeat":
            continue
        o = Q[q["of"]]
        a, b = ans.get(o["id"]), ans.get(q["id"])
        if not a or not b:
            continue
        if "axis" in q:
            ok = side_of(o, a) == side_of(q, b)
        else:
            ok = o["map"][a] == q["map"][b]
        repeats.append({"q": q["id"], "of": o["id"], "ok": ok,
                        "text": "第%d题和第%d题问的是同一件事，%s" % (o["id"], q["id"], "前后一致" if ok else "前后选得不一样")})
    mism = sum(1 for r in repeats if not r["ok"])
    dunno = sum(1 for q in BANK if q["kind"] == "water" and ans.get(q["id"]) == "D" and q["key"] != "terrain")
    skipped = sum(1 for q in BANK if not ans.get(q["id"]))
    level, reasons, notes = "高", [], []

    def hit(lv, why):
        nonlocal level
        if LEVELS.index(lv) < LEVELS.index(level):
            level = lv
        reasons.append(why)

    if share >= 0.7:
        hit("低", "%d 道题里 %d%% 都选了 %s，像是没细看就点了" % (N_Q, round(share * 100), top_letter))
    elif share >= 0.55:
        hit("中", "%d%% 的题都选了 %s，偏多" % (round(share * 100), top_letter))
    if best >= 16:
        hit("低", "连续 %d 题选了同一个选项" % best)
    elif best >= 10:
        hit("中", "连续 %d 题选了同一个选项" % best)
    if period >= 0.7 and share < 0.7:
        hit("低", "答案像是按固定规律在点（比如 ABAB、ABCD 轮着来）")
    if mism == 3:
        hit("中", "3 道换个说法再问的题，前后都选得不一样")
    elif mism == 2:
        notes.append("3 道重复题里有 2 道前后不一样，相关结论会保守一些")
    if skipped >= 6:
        hit("中", "跳过了 %d 道题" % skipped)
    if dunno >= 4:
        notes.append("水土题里有 %d 道选了“记不清”，水土画像会画得比较粗" % dunno)
    summary = "重复题 %d 道里 %d 道前后一致；出现最多的选项 %s 占 %d%%；最长连续同一选项 %d 题" % (
        len(repeats), len(repeats) - mism, top_letter, round(share * 100), best)
    out = {"level": level, "reasons": reasons, "notes": notes, "summary": summary, "repeats": repeats,
           "top_letter": top_letter, "top_share": round(share, 2), "longest_run": best,
           "pattern_score": round(period, 2), "skipped": skipped, "water_dunno": dunno}
    if level == "低":
        out["warning"] = "这组答案的一致性很低，结果不可靠。先别出完整报告，请用户重新答一遍。"
    return out


# ---------------------------------------------------------------- 8 项能力
def score_abilities(ans):
    res = {}
    for key in AB_ORDER:
        r = {"id": "ab." + key, "key": key, "name": ABILITIES[key]["name"], "line": ABILITIES[key]["line"]}
        for kind in ABILITY_KINDS:
            n, picks = 0, []
            for q in BANK:
                if q["kind"] == kind and key in q["map"].values():
                    n += 1
                    c = ans.get(q["id"])
                    if c and q["map"][c] == key:
                        picks.append(q["id"])
            r[kind] = len(picks)
            r[kind + "_n"] = n
            r[kind + "_q"] = picks
            r[kind + "_ev"] = [ev(i, ans[i]) for i in picks]
        p, e, dr, un = r["perf"], r["energy"], r["drain"], r["unused"]
        cls, conf = "none", "低"
        # 题量有限（做得好 6~8 题、来劲 3~4 题分给 8 项），门槛按“和自己比”定，证据少的标“中”
        if p >= 2 and e >= 1 and p + e >= 4:
            cls = "hidden" if un >= 1 else "realized"
            conf = "高" if p + e >= 6 else "中"
        elif p >= 2 and dr >= 1 and e <= 1:
            cls = "learned"
            conf = "高" if p >= 3 and (dr >= 2 or e == 0) else "中"
        elif dr >= 1 and un >= 1 and un + e >= 2:
            cls = "tug"
            conf = "高" if un + e >= 4 else "中"
        elif e >= 1 and un >= 1 and e + un >= 3:
            cls = "spark"
            conf = "中"
        r.update(cls=cls, confidence=conf, tired=dr >= 1,
                 score=round(p / float(r["perf_n"]) + e / float(r["energy_n"]), 2))
        # 画像用的两个合计：换说法再问的题也算一次（第 37 题算“做得好”，第 44 题算“来劲”）
        good_q, drive_q = list(r["perf_q"]), list(r["energy_q"]) + list(r["unused_q"])
        for q in BANK:
            if q["kind"] == "repeat" and "map" in q and ans.get(q["id"]) and q["map"][ans[q["id"]]] == key:
                (good_q if Q[q["of"]]["kind"] == "perf" else drive_q).append(q["id"])
        r.update(good=len(good_q), good_q=sorted(good_q), drive=len(drive_q), drive_q=sorted(drive_q),
                 good_ev=[ev(i, ans[i]) for i in sorted(good_q)], drive_ev=[ev(i, ans[i]) for i in sorted(drive_q)])
        res[key] = r
    return res


CLS_NAME = {"hidden": "没用上的长处", "learned": "旧护甲", "realized": "在用的长处", "tug": "又爱又累", "spark": "小火苗", "none": ""}


def ability_headline(r):
    nm = r["name"]
    return {
        "hidden": "“%s”是你没用上的长处" % nm,
        "learned": "“%s”可能是你的旧护甲" % nm,
        "realized": "“%s”是你正在用的长处" % nm,
        "tug": "“%s”是你又爱又累的事" % nm,
        "spark": "“%s”是一簇小火苗" % nm,
    }.get(r["cls"], nm)


def ability_meaning(r):
    p, e, dr, un = r["perf"], r["energy"], r["drain"], r["unused"]
    pq = "、".join(map(str, r["perf_q"]))
    eq = "、".join(map(str, r["energy_q"]))
    uq = "、".join(map(str, r["unused_q"]))
    dq = "、".join(map(str, r["drain_q"]))
    if r["cls"] == "hidden":
        s = "做得好：第 %s 题；来劲：第 %s 题；可第 %s 题你说最近几乎没机会用。我的推测：这是你身上闲着的一块好料。" % (pq, eq, uq)
        if dr:
            s += "第 %s 题你也说它有时让你累，用的时候留意节奏。" % dq
        return s
    if r["cls"] == "learned":
        return "第 %s 题显示你做得好，可第 %s 题你说它做完累，来劲的题里它%s。我的推测：这是你练出来的本事，不一定是你该靠它吃饭的那一项。" % (
            pq, dq, "几乎没出现" if e == 0 else "只出现了一次")
    if r["cls"] == "realized":
        return "第 %s 题显示你做得好，第 %s 题显示你做着来劲，而且你现在用得上。这是可以放心拿出来的长处。" % (pq, eq)
    if r["cls"] == "tug":
        want = "、".join(map(str, sorted(r["unused_q"] + r["energy_q"])))
        return "第 %s 题显示你想做它、做着来劲，可第 %s 题你又说它让你累。我的推测：你喜欢的是它的某一部分，累的是另一部分，把两部分分开，就知道该把它用在哪。" % (want, dq)
    if r["cls"] == "spark":
        return "第 %s 题显示它让你来劲，第 %s 题你说最近没机会用，但“做得好”的证据还不多。值得找个小机会试一试。" % (eq, uq)
    return ""


# ---------------------------------------------------------------- 水土
def score_water(ans):
    def val(i):
        c = ans.get(i)
        return Q[i]["val"].get(c) if c else None

    stable_vals = [v for v in (val(3), val(12)) if v is not None]
    ren_vals = [v for v in (val(24), val(31)) if v is not None]
    s = sum(stable_vals)
    r = sum(ren_vals)
    stable = "稳" if s >= 1 else ("变" if s <= -1 else "中")
    renqing = "紧" if r >= 1 else ("松" if r <= -1 else "中")
    res_c = ans.get(17)
    resource = {"A": "宽", "B": "攒", "C": "紧"}.get(res_c)
    duty_c = ans.get(38)
    duty = {"A": "顾人", "B": "搭把手", "C": "自理"}.get(duty_c)
    terrain = Q[7]["val"].get(ans.get(7)) if ans.get(7) else None
    known = len(stable_vals) + len(ren_vals) + (1 if resource else 0) + (1 if duty else 0)
    name, desc = WATER_LABEL[(stable, renqing)]
    extras = []
    if duty == "顾人":
        extras.append("从小就是要搭把手的那个")
    if resource == "紧":
        extras.append("知道东西来得不容易")
    elif resource == "宽":
        extras.append("被允许试错")
    elif resource == "攒":
        extras.append("习惯先攒着、等一等")
    if terrain:
        extras.append(TERRAIN_LINE[terrain])
    facts = {"stable": stable, "renqing": renqing, "resource": resource, "duty": duty}
    origins = []
    for key, v, abil, why in ORIGINS:
        if facts.get(key) == v:
            origins.append({"factor": key, "value": v, "abilities": abil, "why": why})
    ev_q = [i for i in (3, 12, 24, 31, 17, 38, 7) if ans.get(i)]
    return {"name": name, "desc": desc, "extras": extras, "stable": stable, "renqing": renqing,
            "resource": resource, "duty": duty, "terrain": terrain, "known": known,
            "confidence": "高" if known >= 5 else ("中" if known >= 3 else "低"),
            "origins": origins, "evidence": [ev(i, ans[i]) for i in ev_q]}


def link_origins(abil, water):
    """把能力和水土连起来：旧护甲、没用上的长处，各自可能是哪片水土练出来的。"""
    out = []
    for key, r in abil.items():
        if r["cls"] not in ("hidden", "learned", "realized", "tug"):
            continue
        for o in water["origins"]:
            if key in o["abilities"]:
                out.append({"ability": key, "name": r["name"], "cls": r["cls"], "why": o["why"],
                            "factor": o["factor"], "value": o["value"]})
                break
    order = {"learned": 0, "hidden": 1, "tug": 2, "realized": 3}
    out.sort(key=lambda x: order[x["cls"]])
    return out


# ---------------------------------------------------------------- 城市：同频与补位
def load_cities():
    with open(CITIES_PATH, encoding="utf-8") as f:
        return json.load(f)["cities"]


def _ax(axes, i):
    return axes[i]["side"], "、".join(map(str, axes[i]["support"]))


def pick_cities(axes, abil, water, cities):
    """同频：和现在的做事方式合拍；补位：给成长水土里缺的东西。理由都绑定题号。"""
    top = sorted(AB_ORDER, key=lambda k: -abil[k]["score"])[:3]
    want_scenes = []
    for k in top:
        for s in ABILITIES[k]["scenes"]:
            if s not in want_scenes:
                want_scenes.append(s)

    def same_score(c):
        pts, why = 0.0, []
        side, qs = _ax(axes, 0)
        if side == "开" and c["newcomer"] == "多":
            pts += 1; why.append("你偏开拓（第 %s 题），我印象里这里外来的年轻人多，新东西冒得快" % qs)
        if side == "深" and c["pace"] in ("中", "慢") and c["newcomer"] != "多":
            pts += 1; why.append("你偏深耕（第 %s 题），我印象里这里节奏不急，适合把一件事磨深" % qs)
        side, qs = _ax(axes, 1)
        if side == "人" and c["night"] == "热闹":
            pts += 1; why.append("你先看人（第 %s 题），我印象里这里夜里热闹，人和人碰得到" % qs)
        if side == "物" and c["night"] == "安静":
            pts += 1; why.append("你先看事和结构（第 %s 题），我印象里这里安静，能专心做东西" % qs)
        side, qs = _ax(axes, 2)
        if side == "快" and c["pace"] == "快":
            pts += 1; why.append("你要快反馈（第 %s 题），我印象里这里节奏快，做出来很快就有人看" % qs)
        if side == "长" and c["pace"] == "慢":
            pts += 1; why.append("你愿意慢慢养（第 %s 题），我印象里这里不催人" % qs)
        side, qs = _ax(axes, 3)
        if side == "独" and c["renqing"] == "松":
            pts += 1; why.append("你想自己搞定（第 %s 题），我印象里这里边界感清楚，不太被人情牵着走" % qs)
        if side == "合" and c["renqing"] in ("中", "紧") and c["night"] == "热闹":
            pts += 1; why.append("你习惯一起干（第 %s 题），我印象里这里有烟火气，容易找到搭子" % qs)
        used, hit = [], []
        for k, w in zip(top, (1.6, 1.0, 0.6)):
            h = [x for x in ABILITIES[k]["scenes"] if x in c["scenes"]]
            if h:
                pts += w
                # 理由里只点名让你来劲、又写得出结论的本事；旧护甲不拿来当去一座城的理由
                if abil[k].get("usable") and abil[k]["cls"] in ("hidden", "realized", "tug", "spark"):
                    used.append(abil[k]["name"])
                    hit += [x for x in h if x not in hit]
        if used:
            why.insert(0, "你的“%s”在这里有用武之地：我印象里%s相关的事多" % ("”和“".join(used[:2]), "、".join(hit[:2])))
        # 节奏、夜里、人情是“中”的城市，对两头的人都给一点分，免得几座极端的城市包揽
        pts += 0.4 * sum(1 for f in ("pace", "night", "renqing") if c[f] == "中")
        if c.get("obvious"):
            pts -= 1.0
        return pts, why

    def fill_score(c):
        ws, why = [], []
        if water["renqing"] == "紧" and c["renqing"] == "松":
            ws.append(2); why.append("你在人情很近的环境里长大（第 24、31 题），这里我印象里是陌生人社会，可以松一口气")
        if water["renqing"] == "松" and c["renqing"] in ("中", "紧") and c["night"] == "热闹":
            ws.append(2); why.append("你长大的环境各过各的（第 24、31 题），这里我印象里有浓的烟火气和人情味，补上“热乎”的那一块")
        if water["stable"] == "变" and c["pace"] == "慢":
            ws.append(2); why.append("你小时候的日子常有变数（第 3、12 题），这里我印象里节奏慢、日子有准点")
        if water["stable"] == "稳" and c["newcomer"] == "多":
            ws.append(1.5); why.append("你在很稳的环境里长大（第 3、12 题），这里我印象里外来的人多，什么都在变，能给你新鲜感")
        if water["duty"] == "顾人" and c["night"] == "安静" and c["renqing"] == "松":
            ws.append(1); why.append("你从小要照顾人（第 38 题），这里我印象里安静、松，不用总当那个张罗的人")
        if water["resource"] == "紧" and c["newcomer"] == "多" and c["pace"] != "慢":
            ws.append(1); why.append("你小时候知道东西来得不容易（第 17 题），这里我印象里机会多，试错成本相对低")
        t = water["terrain"]
        want = {"平原": ["山", "海", "湖"], "城": ["山", "海", "湖", "水"], "山": ["海", "平原"], "水": ["山"]}.get(t, [])
        got = [x for x in c["terrain"] if x in want]
        if got:
            ws.append(1.5); why.append("你%s（第 7 题），这里有%s，是你小时候少见的风景" % (TERRAIN_LINE[t], "、".join(got)))
        pts = (max(ws) + 0.35 * (len(ws) - 1)) if ws else 0.0   # 最强的一条为主，多一条加一点
        if c.get("obvious"):
            pts -= 1.0
        return pts, why

    def fill_score2(c):
        pts, why = fill_score(c)
        return pts, why

    seed = sum(ord(ch) * (i + 1) for i, ch in enumerate(json.dumps([a["side"] for a in axes]) + water["name"] + "".join(top)))

    def ranked(scored):
        """分数相近（差 0.5 以内）的城市按这个人的答案轮换，避免所有人都被推到同几座城。"""
        scored = sorted(scored, key=lambda x: -x[0][0])
        out, rest = [], list(scored)
        while rest:
            best = rest[0][0][0]
            near = [x for x in rest if best - x[0][0] <= 0.5]
            pick = near[seed % len(near)]
            out.append(pick)
            rest.remove(pick)
        return out

    same = ranked([(same_score(c), c) for c in cities])
    picks_same = []
    for (pts, why), c in same:
        if len(picks_same) == 3:
            break
        if why:
            picks_same.append({"kind": "同频", "name": c["name"], "score": round(pts, 2), "why": why[:3],
                               "vibe": c["vibe"], "cost": c["cost"]})
    taken = {p["name"] for p in picks_same}
    fill = []
    if water["known"] >= 2 or water["terrain"]:
        fill = ranked([(fill_score2(c), c) for c in cities if c["name"] not in taken])
    picks_fill = []
    for (pts, why), c in fill:
        if pts > 0 and why:
            picks_fill.append({"kind": "补位", "name": c["name"], "score": round(pts, 2), "why": why[:3],
                               "vibe": c["vibe"], "cost": c["cost"]})
            break
    return picks_same + picks_fill


# ---------------------------------------------------------------- 汇总
def analyze(raw):
    ans = parse_answers(raw)
    code, axes = score_axes(ans)
    cons = consistency(ans)
    abil = score_abilities(ans)
    steps = {"高": 0, "中": 1, "低": 9}[cons["level"]]
    for r in abil.values():
        r["raw_confidence"] = r["confidence"]
        r["confidence"] = down(r["confidence"], steps)
        r["usable"] = r["cls"] != "none" and r["confidence"] != "低"
    water = score_water(ans)
    if cons["level"] == "低":
        water["confidence"] = "低"
    origins = link_origins({k: v for k, v in abil.items() if v["usable"]}, water) if water["confidence"] != "低" else []
    cities = pick_cities(axes, abil, water, load_cities()) if cons["level"] != "低" else []
    letters = "".join(ans[i] or "-" for i in sorted(ans))
    sig = {"version": VERSION, "answers": letters, "code": code, "axes": axes, "reliability": cons,
           "abilities": abil, "water": water, "origins": origins, "cities": cities}
    sig["candidates"] = candidates(sig)
    sig["profile"] = profile(abil, cons["level"])
    sig["top_abilities"] = [{"key": k, "name": abil[k]["name"], "perf": abil[k]["perf"], "energy": abil[k]["energy"],
                             "roles": ABILITIES[k]["roles"]} for k in sorted(AB_ORDER, key=lambda k: -abil[k]["score"])[:3]]
    return sig


def profile(abil, level):
    """给写画像用的三张清单：发动机（来劲 + 想用）、本事（做得好 + 别人常找你）、耗你的事。"""
    if level == "低":
        return {"engine": [], "skills": [], "drain": [], "note": "答案前后对不上，先不画像"}

    def item(k, n, qs):
        # 随机作答时每项平均能碰上 1.5 次左右，所以 ≥3 次才算“明显”，2 次只算“有一些”
        return {"key": k, "name": abil[k]["name"], "line": ABILITIES[k]["line"], "count": n, "questions": qs,
                "level": "明显" if n >= 3 else "有一些"}

    engine = sorted((k for k in AB_ORDER if abil[k]["drive"] >= 2), key=lambda k: (-abil[k]["drive"], -abil[k]["good"]))
    skills = sorted((k for k in AB_ORDER if abil[k]["good"] >= 2), key=lambda k: (-abil[k]["good"], -abil[k]["drive"]))
    drain = sorted((k for k in AB_ORDER if abil[k]["drain"] >= 1), key=lambda k: -abil[k]["drain"])
    return {
        "engine": [item(k, abil[k]["drive"], abil[k]["drive_q"]) for k in engine],
        "skills": [dict(item(k, abil[k]["good"], abil[k]["good_q"]), engine=k in engine) for k in skills],
        "drain": [item(k, abil[k]["drain"], abil[k]["drain_q"]) for k in drain],
    }


def candidates(sig):
    pri = {"hidden": 0, "learned": 1, "tug": 2, "realized": 3, "spark": 4}
    out = []
    for r in sig["abilities"].values():
        if not r["usable"]:
            continue
        out.append({"basis": r["id"], "cls": r["cls"], "cls_name": CLS_NAME[r["cls"]], "confidence": r["confidence"],
                    "headline": ability_headline(r), "meaning": ability_meaning(r),
                    "evidence": r["perf_ev"] + r["energy_ev"] + r["unused_ev"] + r["drain_ev"],
                    "_r": (pri[r["cls"]], 0 if r["confidence"] == "高" else 1, -r["score"])})
    out.sort(key=lambda x: x["_r"])
    for x in out:
        x.pop("_r")
    return out


def basis_index(sig):
    idx = {r["id"]: r for r in sig["abilities"].values()}
    idx["water"] = {"usable": sig["water"]["confidence"] != "低", "confidence": sig["water"]["confidence"]}
    for i, a in enumerate(sig["axes"]):
        idx["axis.%d" % i] = {"usable": True, "confidence": "高" if a["lean"] == "鲜明" else "中"}
    return idx


def text_summary(sig, types=None):
    t = (types or {}).get(sig["code"], {})
    r = sig["reliability"]
    lines = ["类型：%s %s（%s）" % (sig["code"], t.get("name", ""), " · ".join(
        "%s%s" % (a["lean"], a["winner"]) for a in sig["axes"])),
             "可信度：%s。%s" % (r["level"], r["summary"])]
    lines += ["  ! " + x for x in r["reasons"]] + ["  · " + x for x in r["notes"]]
    if r.get("warning"):
        lines.append("  !! " + r["warning"])
    for k in AB_ORDER:
        a = sig["abilities"][k]
        lines.append("能力·%s：做得好 %d/%d，来劲 %d/%d，做完累 %d/%d，用得少 %d/%d → %s［%s］" % (
            a["name"], a["perf"], a["perf_n"], a["energy"], a["energy_n"], a["drain"], a["drain_n"],
            a["unused"], a["unused_n"], CLS_NAME[a["cls"]] or "—", a["confidence"]))
    pf = sig["profile"]
    lines.append("画像·发动机（来劲 + 想用）：" + ("、".join("%s %d %s" % (x["name"], x["count"], x["level"]) for x in pf["engine"]) or "无"))
    lines.append("画像·本事（做得好 + 别人常找你）：" + ("、".join("%s %d %s%s" % (x["name"], x["count"], x["level"], "（也是发动机）" if x["engine"] else "") for x in pf["skills"]) or "无"))
    lines.append("画像·耗你的事：" + ("、".join("%s %d" % (x["name"], x["count"]) for x in pf["drain"]) or "无"))
    w = sig["water"]
    lines.append("水土：%s（%s；%s）［%s］" % (w["name"], w["desc"], "，".join(w["extras"]), w["confidence"]))
    for o in sig["origins"]:
        lines.append("  来源：%s（%s）← %s" % (o["name"], CLS_NAME[o["cls"]], o["why"]))
    for c in sig["cities"]:
        lines.append("城市·%s：%s（%s）" % (c["kind"], c["name"], "；".join(c["why"])))
    return "\n".join(lines)


# ---------------------------------------------------------------- 出题
def batch_ids(n):
    a, b = BATCHES[n - 1]
    return list(range(a, b + 1))


def batch_text(n):
    ids = batch_ids(n)
    lines = ["第 %d 段（共 %d 段）· %d 题" % (n, len(BATCHES), len(ids)),
             "按顺序回 %d 个字母就行，也可以写“%dA %dB…”。凭第一反应选。" % (len(ids), ids[0], ids[0] + 1), ""]
    for i in ids:
        q = Q[i]
        lines.append("%d. %s" % (i, q["q"]))
        for k, v in q["opts"].items():
            lines.append("%s %s" % (k, v))
        lines.append("")
    return "\n".join(lines).rstrip()


def batch_card(n):
    """一段题的按钮答题卡（Cindy 对话界面的 cindy-ui 组件）。每题点一个按钮，最后点“发送”把这一段的答案发回对话。"""
    ids = batch_ids(n)
    ops = []

    def add(op):
        op["seq"] = len(ops) + 1
        if op["seq"] == 1:
            op["version"] = 1
        ops.append(op)

    root = "b%d" % n
    add({"op": "create", "id": root, "kind": "stack", "props": {"style": {"gap": 12}}})
    add({"op": "create", "id": root + "h", "kind": "text", "parent": root, "props": {
        "text": "第 %d 段（共 %d 段）· %d 题　凭第一反应点，选好了点最下面的“发送”" % (n, len(BATCHES), len(ids)),
        "style": {"color": "secondary", "fontSize": 13}}})
    for i in ids:
        q = Q[i]
        box = "%sq%d" % (root, i)
        add({"op": "create", "id": box, "kind": "stack", "parent": root,
             "props": {"style": {"gap": 6, "padding": 12, "borderWidth": 1, "borderRadius": 14}}})
        add({"op": "create", "id": box + "t", "kind": "text", "parent": box,
             "props": {"text": "%d. %s" % (i, q["q"]), "style": {"fontWeight": 600}}})
        g = box + "g"
        add({"op": "create", "id": g, "kind": "grid", "parent": box,
             "props": {"columns": 1, "mobileColumns": 1, "style": {"gap": 6}}})
        for k, v in q["opts"].items():
            add({"op": "create", "id": "%s%s" % (g, k), "kind": "button", "parent": g,
                 "props": {"label": "%s　%s" % (k, v), "set": {"q%d" % i: k}}})
        add({"op": "create", "id": box + "s", "kind": "stat", "parent": box,
             "props": {"label": "你选了", "value": {"ref": "q%d" % i}}})
    args = ["第%d段：" % n]
    for j, i in enumerate(ids):
        args += ["%s%d" % ("" if j == 0 else " ", i), {"ref": "q%d" % i}]
    add({"op": "create", "id": root + "go", "kind": "button", "parent": root,
         "props": {"label": "第 %d 段选好了，发送" % n, "send": {"op": "concat", "args": args}}})
    return "```cindy-ui\n" + "\n".join(json.dumps(o, ensure_ascii=False) for o in ops) + "\n```"


def scoring_note(q):
    k = q["kind"]
    if k == "style":
        a = AXES[q["axis"]]
        o = "B" if q["p1"] == "A" else "A"
        return "风格·%s：%s=%s，%s=%s（1 票）" % (a["name"], q["p1"], a["p1"], o, a["p2"])
    if k == "water":
        if q["key"] == "terrain":
            return "水土·地貌：" + "，".join("%s=%s" % (c, v) for c, v in q["val"].items())
        name = {"stable": "节奏稳还是多变（+1 稳，−1 变）", "renqing": "人情紧还是松（+1 紧，−1 松）",
                "resource": "资源宽还是紧（A 宽，B 攒，C 紧）", "duty": "要不要顾别人（A 顾人，B 搭把手，C 自理）"}[q["key"]]
        return "水土·%s；D 记不清不计分" % name
    if k == "repeat" and "axis" in q:
        a = AXES[q["axis"]]
        o = "B" if q["p1"] == "A" else "A"
        return "重复题（对照第 %d 题查一致性，也给“%s”投 1 票）：%s=%s，%s=%s" % (q["of"], a["name"], q["p1"], a["p1"], o, a["p2"])
    s = "%s：" % ("重复题（对照第 %d 题，只查一致性）" % q["of"] if k == "repeat" else "能力·" + KIND_NAME[k])
    s += "，".join("%s %s" % (c, ABILITIES[v]["name"]) for c, v in q["map"].items())
    if q.get("tb"):
        a = AXES[q["tb"]["axis"]]
        s += "；同时给“%s”投 1 票：%s" % (a["name"], "，".join("%s=%s" % (c, v) for c, v in q["tb"]["side"].items()))
    return s


def questions_md():
    kinds = Counter(q["kind"] for q in BANK)
    out = ["# 题库（v%s）" % VERSION, "",
           "> 本文件由 `python3 scripts/hidden_talent.py questions --md > references/questions.md` 生成。"
           "题目和计分只在脚本的 `BANK` 里维护，改完重新生成，别手改这里。", "",
           "## 怎么用", "",
           "- 共 %d 题，全部是选择题，分 %d 段，每段 7 到 8 题，点按钮作答，约 12 分钟。" % (N_Q, len(BATCHES)),
           "- 发题用 `python3 scripts/hidden_talent.py ask <段号>`，输出按钮答题卡，原样发出；界面不显示按钮时加 `--text`。",
           "- 不问现在住在哪、能不能搬；城市建议在报告里直接给。", "",
           "题型构成：风格 %d（定 16 型）、水土 %d、做得好 %d、来劲 %d、做完累 %d、用得少 %d、重复检查 %d。" % (
               kinds["style"], kinds["water"], kinds["perf"], kinds["energy"], kinds["drain"], kinds["unused"], kinds["repeat"]), ""]
    for n in range(1, len(BATCHES) + 1):
        out += ["## 第 %d 段（第 %d–%d 题）" % ((n,) + BATCHES[n - 1]), ""]
        for i in batch_ids(n):
            q = Q[i]
            out.append("**%d.** %s　`%s`" % (i, q["q"], KIND_NAME[q["kind"]]))
            for k, v in q["opts"].items():
                out.append("%s. %s  " % (k, v))
            out += ["> 计分：" + scoring_note(q), ""]
    out += ["## 计分总表", "", "### 8 项能力", ""]
    for key in AB_ORDER:
        cnt = {k: ["%d%s" % (q["id"], "".join(c for c, v in q["map"].items() if v == key))
                   for q in BANK if q["kind"] == k and key in q["map"].values()] for k in ABILITY_KINDS}
        out.append("- **%s**（%s）：做得好 %s；来劲 %s；做完累 %s；用得少 %s" % (
            ABILITIES[key]["name"], ABILITIES[key]["line"], "、".join(cnt["perf"]), "、".join(cnt["energy"]),
            "、".join(cnt["drain"]), "、".join(cnt["unused"])))
    out += ["", "判定（按次数，门槛是“和自己比”：题量分到 8 项后每项只有几道题）：",
            "- **没用上的长处**：做得好 ≥2、来劲 ≥1、两者合计 ≥4，并且用得少 ≥1。**在用的长处**：同样条件，但没说用得少。",
            "- **旧护甲**：做得好 ≥2 + 做完累 ≥1 + 来劲 ≤1。",
            "- **又爱又累**：做完累 ≥1，同时用得少 ≥1，且用得少 + 来劲 ≥2（想做它，又被它的某一部分累着）。",
            "- **小火苗**：来劲 + 用得少合计 ≥3。",
            "- 置信度：长处类做得好 + 来劲 ≥6 记高；旧护甲做得好 ≥3 且（累 ≥2 或来劲 0）记高；又爱又累 用得少 + 来劲 ≥4 记高；其余记中。整体可信度“中”时每条降一级，“低”时全部不写。",
            "", "### 16 型", "",
            "每个维度 3 票，≥2 票的一侧胜出；3 票一致为“鲜明”，2:1 为“略偏”。", ""]
    for ax, a in enumerate(AXES):
        out.append("- %s（%s / %s）：第 %s 题" % (a["name"], a["p1"], a["p2"], "、".join(str(q["id"]) for q in AXIS_VOTERS[ax])))
    out += ["", "### 水土与城市", "",
            "- 节奏稳 / 变：第 3、12 题；人情紧 / 松：第 24、31 题；资源：第 17 题；顾人：第 38 题；地貌：第 7 题。",
            "- 同频城市：按 4 个风格维度和得分最高的 3 项能力，匹配 `references/cities.json` 里的节奏、人情、外来年轻人、夜里、行业气质。",
            "- 补位城市：给水土里缺的东西（人情紧→陌生人社会；日子多变→慢节奏；很稳→新移民多；平原和城里长大→山海湖）。",
            "- 北上广深这类人人想得到的城市扣分，除非分数明显最高。", "",
            "### 一致性", "",
            "- 重复题：第 37 题对照第 9 题，第 42 题对照第 33 题，第 44 题对照第 10 题，换个说法、选项顺序打乱。",
            "- 同一选项占比 ≥70%、连续 16 题同一选项、按 ABAB / ABCD 规律点 → 可信度“低”，不出完整报告。", ""]
    return "\n".join(out)


def flip(code, idx):
    a = AXES[idx]
    new = a["c2"] if code[idx] == a["c1"] else a["c1"]
    return code[:idx] + new + code[idx + 1:]


def flip_all(code):
    for i in range(4):
        code = flip(code, i)
    return code


def load_types():
    with open(TYPES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    by = {t["code"]: t for t in data}
    if len(by) != 16:
        raise SystemExit("types.json 需要 16 个不同的类型，实际 %d 个" % len(by))
    return by


def E(x):
    return html.escape(str(x), quote=True)


def names(t):
    return t["name"], "我的奶茶人格", t["emoji"]


def lean_text(ax):
    if ax["lean"] == "鲜明":
        return "鲜明偏向%s" % ax["winner"]
    return "略偏%s" % ax["winner"]


# ---------------------------------------------------------------- 颜色与杯子角色
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(h1, h2, t):
    a, b = _rgb(h1), _rgb(h2)
    return "#%02x%02x%02x" % tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def palette(t):
    liquid = t.get("liquid", "#c89b6d")
    accent = t.get("accent", "#b8672a")
    return {
        "liquid": liquid,
        "light": mix(liquid, "#ffffff", 0.35),
        "foam": mix(liquid, "#ffffff", 0.8),
        "bg": t.get("bg", "#f6efe6"),
        "accent": accent,
        "ink": mix(accent, "#000000", 0.45),
        "soft": mix(accent, "#ffffff", 0.82),
        "topping": t.get("topping", ["#3a2417"]),
    }


def cup_svg(t, uid="c"):
    p = palette(t)
    body = "M62 178 L258 178 L236 440 Q233 458 214 458 L106 458 Q87 458 84 440 Z"
    tops = []
    pos = [(110, 442), (138, 442), (166, 442), (194, 442), (222, 440),
           (124, 418), (152, 418), (180, 418), (208, 417), (138, 394), (166, 394), (194, 393)]
    for i, (x, y) in enumerate(pos):
        col = p["topping"][i % len(p["topping"])]
        tops.append('<circle cx="%d" cy="%d" r="13" fill="%s"/>'
                    '<circle cx="%d" cy="%d" r="3.6" fill="#fff" opacity=".55"/>' % (x, y, col, x - 4, y - 5))
    return (
        '<svg viewBox="0 0 320 480" xmlns="http://www.w3.org/2000/svg">'
        '<defs><clipPath id="%(u)sclip"><path d="%(body)s"/></clipPath>'
        '<linearGradient id="%(u)sliq" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="%(light)s"/><stop offset="1" stop-color="%(liquid)s"/></linearGradient></defs>'
        '<rect x="176" y="10" width="22" height="196" rx="11" transform="rotate(8 187 108)" fill="%(accent)s"/>'
        '<path d="%(body)s" fill="#ffffff" fill-opacity=".62" stroke="#3b2a22" stroke-opacity=".14" stroke-width="3"/>'
        '<g clip-path="url(#%(u)sclip)">'
        '<rect x="40" y="236" width="240" height="240" fill="url(#%(u)sliq)"/>'
        '<path d="M40 236 Q70 216 100 236 T160 236 T220 236 T280 236 V258 H40 Z" fill="%(foam)s"/>'
        '%(tops)s'
        '<rect x="80" y="196" width="14" height="236" rx="7" fill="#fff" opacity=".4" transform="rotate(5 87 314)"/>'
        '</g>'
        '<path d="M52 182 Q52 122 160 112 Q268 122 268 182 Z" fill="#ffffff" fill-opacity=".78" stroke="#3b2a22" stroke-opacity=".14" stroke-width="3"/>'
        '<rect x="42" y="172" width="236" height="20" rx="10" fill="#ffffff" stroke="#3b2a22" stroke-opacity=".14" stroke-width="3"/>'
        '<circle cx="124" cy="328" r="9.5" fill="#3b2a22"/><circle cx="196" cy="328" r="9.5" fill="#3b2a22"/>'
        '<circle cx="127.5" cy="324.5" r="3.4" fill="#fff"/><circle cx="199.5" cy="324.5" r="3.4" fill="#fff"/>'
        '<path d="M147 344 Q160 360 173 344" stroke="#3b2a22" stroke-width="5.5" fill="none" stroke-linecap="round"/>'
        '<ellipse cx="100" cy="347" rx="15" ry="9" fill="#ff8fa3" opacity=".55"/>'
        '<ellipse cx="220" cy="347" rx="15" ry="9" fill="#ff8fa3" opacity=".55"/>'
        '</svg>' % {"u": uid, "body": body, "light": p["light"], "liquid": p["liquid"], "accent": p["accent"],
                    "foam": p["foam"], "tops": "".join(tops)})


def confetti(t, sizes):
    """杯子周围的配料表情，用来增加可爱感。sizes 为 px。"""
    p = palette(t)
    spots = [(2, 14, -14, sizes[0]), (82, 6, 12, sizes[1]), (-2, 62, 10, sizes[2]), (86, 56, -10, sizes[3])]
    out = []
    for x, y, r, s in spots:
        out.append('<span style="position:absolute;left:%d%%;top:%d%%;font-size:%dpx;transform:rotate(%ddeg)">%s</span>'
                   % (x, y, s, r, E(t["emoji"])))
    out.append('<span style="position:absolute;left:14%%;top:2%%;font-size:%dpx;color:%s">✦</span>' % (sizes[2], p["accent"]))
    out.append('<span style="position:absolute;left:74%%;top:78%%;font-size:%dpx;color:%s">✦</span>' % (sizes[1], p["accent"]))
    out.append('<span style="position:absolute;left:10%%;top:84%%;font-size:%dpx;color:%s">●</span>' % (sizes[3] // 2, p["accent"]))
    return "".join(out)


# ---------------------------------------------------------------- 搭档与相冲
def partners(code, types):
    a = types[flip(code, 0)]
    b = types[flip(code, 1)]
    c = types[flip_all(code)]
    why_a = "你负责开头，TA 负责把它磨到收尾" if code[0] == "开" else "TA 负责开新局，你负责把它做扎实"
    if code[1] == "物":
        why_b = "你先看事和结构，TA 先看人，会帮你补上容易漏掉的人的那一面"
    else:
        why_b = "你先看人，TA 先看事和结构，会帮你把感受落成能执行的事实"
    diffs = ["你%s，TA %s" % (SIDE_DESC[i][code[i]], SIDE_DESC[i][c["code"][i]]) for i in range(4)]
    return {"a": a, "why_a": why_a, "b": b, "why_b": why_b, "c": c, "diffs": diffs, "tips": CLASH_TIPS}


# ---------------------------------------------------------------- 报告
REPORT_CSS = """
*{box-sizing:border-box}
body{margin:0;background:__BG__;color:#2b2a33;font-family:__BODY__;line-height:1.75;-webkit-text-size-adjust:100%}
.wrap{max-width:560px;margin:0 auto;padding:16px 16px 56px}
.ribbon{background:#fff3cd;color:#7a5a00;border-radius:12px;padding:8px 12px;font-size:13px;margin-bottom:12px;text-align:center}
.hero{background:#fff;border-radius:30px;padding:22px 18px 22px;text-align:center;box-shadow:0 6px 24px rgba(60,40,30,.10);position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;left:50%;top:44px;width:300px;height:300px;margin-left:-150px;border-radius:50%;background:__SOFT__}
.hero .k{position:relative;display:inline-block;background:__ACCENT__;color:#fff;border-radius:99px;padding:2px 14px;font-size:12px;letter-spacing:.12em}
.stage{position:relative;width:250px;height:300px;margin:6px auto 0}
.stage svg{position:relative;width:200px;display:block;margin:0 auto}
.hero .name{position:relative;font-family:__FONT__;font-size:38px;font-weight:700;color:__INK__;line-height:1.2;margin-top:2px}
.hero .sub{position:relative;font-size:13px;color:__ACCENT__;letter-spacing:.18em;margin-top:2px}
.bubble{position:relative;display:inline-block;margin-top:12px;background:__SOFT__;border:2px solid __ACCENT__;border-radius:18px;padding:5px 16px;font-size:15px;color:__INK__;font-weight:600}
.tag{position:relative;margin-top:12px;font-size:15px;color:#555}
.chips{position:relative;margin-top:12px;display:flex;flex-wrap:wrap;gap:6px;justify-content:center}
.chips span{background:__SOFT__;color:__INK__;border-radius:99px;padding:2px 11px;font-size:12px}
h2{font-family:__FONT__;font-size:22px;margin:30px 4px 4px;color:__INK__}
.lead{margin:0 4px 12px;color:#777;font-size:13px}
.card{background:#fff;border-radius:22px;padding:16px 18px;margin-bottom:12px;box-shadow:0 2px 12px rgba(60,40,30,.07)}
.card h3{margin:2px 0 6px;font-size:18px;line-height:1.4;color:__INK__}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px}
.badge{font-size:11px;border-radius:99px;padding:1px 9px;background:#f0eef3;color:#6a6878}
.badge.star{background:__ACCENT__;color:#fff;font-weight:700}
.badge.guess{background:#eef3ff;color:#4a63a8}
p{margin:0 0 8px}
.flow{font-size:14.5px}
.mute{color:#9a97a6;font-size:12px;margin-right:2px}
.arrow{color:__ACCENT__;font-weight:700;margin:0 4px}
ul{margin:0 0 8px;padding-left:18px}
li{margin:2px 0;font-size:14px}
.ev li{color:#5b5868}
.try{background:__SOFT__;border-radius:12px;padding:8px 12px;font-size:13.5px}
.try b{display:block;font-size:11px;letter-spacing:.1em;color:__ACCENT__;margin-bottom:1px}
.ins{border-left:6px solid __ACCENT__}
.ins .why{font-size:12px;color:#8a8796;margin-top:2px}
.hd{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.rk{flex:none;width:30px;height:30px;border-radius:50%;background:__ACCENT__;color:#fff;font-weight:800;text-align:center;line-height:30px}
.hd h3{margin:0;flex:1}
.tagf{flex:none;font-size:11px;border-radius:99px;padding:1px 9px;background:__SOFT__;color:__INK__;font-weight:700}
.blk{margin-top:8px}
.blk b{display:block;font-size:11px;letter-spacing:.1em;color:#9a97a6;margin-bottom:1px}
.blk.warn{background:#fff7e6;border-radius:12px;padding:8px 12px}
.blk.warn b{color:#b07a00}
.note{background:#eef3ff;border-radius:14px;padding:10px 14px;font-size:13px;color:#42538a;margin-bottom:12px}
.avoid li b{color:__INK__}
.pair{display:flex;gap:10px;margin-bottom:12px}
.pair .card{flex:1;margin:0;text-align:center;padding:14px 10px}
.pair .em{font-size:44px;line-height:1.2}
.pair .nm{font-family:__FONT__;font-size:18px;font-weight:700;color:__INK__}
.pair .lb{display:inline-block;font-size:11px;border-radius:99px;padding:1px 9px;background:__SOFT__;color:__INK__;font-weight:700;margin-bottom:4px}
.pair .tx{font-size:12.5px;color:#666;text-align:left;margin-top:6px}
.clash{border:2px dashed #c9c5d3}
.clash .lb{background:#ece9f2;color:#5b5868}
.ax{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12.5px}
.ax .l{width:86px;text-align:right;color:#666;white-space:nowrap}
.ax .r{width:86px;color:#666;white-space:nowrap}
.bar{flex:1;height:8px;border-radius:99px;background:__SOFT__;overflow:hidden}
.bar i{display:block;height:100%;background:__ACCENT__}
.week{background:__ACCENT__;color:#fff;border-radius:22px;padding:16px 18px;margin:12px 0}
.week b{display:block;font-size:12px;letter-spacing:.12em;opacity:.85;margin-bottom:2px}
.foot{margin:24px 6px 0;font-size:12px;color:#8a8796;line-height:1.7}
"""


def _css(p):
    out = REPORT_CSS
    for k, v in {"__BG__": p["bg"], "__ACCENT__": p["accent"], "__INK__": p["ink"], "__SOFT__": p["soft"],
                 "__FONT__": FONT, "__BODY__": BODY_FONT}.items():
        out = out.replace(k, v)
    return out


def _ul(items, cls=""):
    if not items:
        return ""
    return '<ul%s>%s</ul>' % (' class="%s"' % cls if cls else "", "".join("<li>%s</li>" % E(x) for x in items))



SHARE_CSS = """
*{box-sizing:border-box;margin:0}
body{width:1080px;height:1440px;overflow:hidden;position:relative;font-family:__FONT__;color:__INK__;background:__BG__}
.dots{position:absolute;left:0;top:0;width:100%;height:100%;background-image:radial-gradient(__DOT__ 3.5px,transparent 4px);background-size:46px 46px}
.blob{position:absolute;left:50%;top:136px;width:640px;height:640px;margin-left:-320px;border-radius:50%;background:#fff;opacity:.7}
.c{position:relative;height:100%;padding:44px 64px 40px;display:flex;flex-direction:column;align-items:center}
.top{width:100%;display:flex;justify-content:space-between;align-items:center}
.pill{background:__ACCENT__;color:#fff;border-radius:99px;padding:8px 26px;font-size:28px;letter-spacing:.12em;font-weight:700}
.q{font-size:28px;color:__ACCENT__;font-weight:700}
.stage{position:relative;width:700px;height:462px;margin-top:6px}
.stage svg{position:absolute;left:50%;top:0;width:312px;margin-left:-156px}
.name{font-size:116px;font-weight:700;line-height:1.1;margin-top:0;text-shadow:0 4px 0 #fff}
.sub{font-size:28px;letter-spacing:.3em;color:__ACCENT__;margin-top:2px;font-weight:700}
.bubble{margin-top:16px;background:#fff;border:4px solid __ACCENT__;border-radius:40px;padding:10px 38px;font-size:38px;font-weight:700;transform:rotate(-1.5deg)}
.card{width:100%;margin-top:22px;background:#fff;border-radius:46px;padding:26px 38px 22px;box-shadow:0 10px 0 __SOFT2__}
.card .h{font-size:30px;color:__ACCENT__;font-weight:700;margin-bottom:10px;letter-spacing:.08em}
.row{display:flex;align-items:center;gap:20px;margin-top:12px}
.row i{flex:none;width:50px;height:50px;border-radius:50%;background:__ACCENT__;color:#fff;font-style:normal;font-weight:700;font-size:30px;text-align:center;line-height:50px}
.rt{font-size:42px;font-weight:700;line-height:1.3}
.star{font-size:24px;background:__SOFT__;color:__INK__;border-radius:99px;padding:2px 16px;font-weight:700}
.match{width:100%;display:flex;gap:22px;margin-top:22px}
.mc{flex:1;background:#fff;border-radius:40px;padding:20px 26px;display:flex;align-items:center;gap:20px;box-shadow:0 8px 0 __SOFT2__}
.mc .em{flex:none;width:96px;height:96px;border-radius:50%;background:__SOFT__;font-size:60px;line-height:96px;text-align:center}
.mc .lb{font-size:24px;font-weight:700;color:__ACCENT__}
.mc.bad .lb{color:#6b6877}
.mc .nm{font-size:40px;font-weight:700;line-height:1.2}
.ft{margin-top:auto;padding-top:14px;font-size:30px;font-weight:700;color:__ACCENT__;text-align:center;letter-spacing:.06em}
"""


EXTRA_CSS = """
.alarm{background:#ffe9e6;color:#9a3a2a;border-radius:16px;padding:10px 14px;font-size:13.5px;margin-bottom:12px;line-height:1.6}
.alarm b{display:block;font-size:14.5px;margin-bottom:2px}
.hero .pname{position:relative;font-family:__FONT__;font-size:40px;font-weight:700;color:__INK__;line-height:1.2;margin-top:4px}
.hero .pline{position:relative;font-size:16px;line-height:1.75;color:#3a3844;margin:10px 4px 0;font-weight:600}
.hero .milk{position:relative;margin-top:14px;font-size:13px;color:#6a6878}
.hero .milk b{color:__INK__}
.wow{background:__ACCENT__;color:#fff;border-radius:22px;padding:16px 18px;margin:16px 0 0}
.wow b{display:block;font-size:12px;letter-spacing:.12em;opacity:.85;margin-bottom:4px}
.wow p{margin:0;font-size:16px;line-height:1.75}
.sec{background:#fff;border-radius:22px;padding:16px 18px;margin-top:12px;box-shadow:0 2px 12px rgba(60,40,30,.07)}
.sec>b{display:block;font-family:__FONT__;font-size:19px;color:__INK__;margin-bottom:6px}
.sec p{font-size:15.5px;line-height:1.8;margin:0}
.sk{display:flex;gap:10px;align-items:baseline;margin:8px 0;font-size:15px;line-height:1.6}
.sk .n{flex:none;font-weight:700;color:__INK__;min-width:4.5em}
.sk .eng{flex:none;font-size:11px;border-radius:99px;padding:0 8px;background:__ACCENT__;color:#fff;white-space:nowrap;align-self:center}
.sk .t{flex:1}
.sknote{font-size:13.5px;color:#6a6878;margin-top:8px}
.sec ul{margin:0;padding-left:18px}
.sec li{font-size:15px;line-height:1.75}
.go .pos{font-size:17px;font-weight:700;color:__INK__;margin-bottom:10px}
.go .lb{font-size:12px;letter-spacing:.1em;color:#9a97a6;margin:12px 0 6px}
.pills{display:flex;flex-wrap:wrap;gap:8px}
.pills span{background:__SOFT__;color:__INK__;border-radius:99px;padding:5px 14px;font-size:14.5px;font-weight:600}
details.appx{margin-top:26px;background:#fff;border-radius:22px;padding:4px 18px;box-shadow:0 2px 12px rgba(60,40,30,.07)}
details.appx summary{cursor:pointer;padding:12px 0;font-size:14px;color:#6a6878;list-style:none}
details.appx summary::-webkit-details-marker{display:none}
details.appx summary:after{content:" ▸";color:__ACCENT__}
details.appx[open] summary:after{content:" ▾"}
.appx h4{font-size:14px;color:__INK__;margin:14px 0 4px}
.appx li,.appx p{font-size:13px;color:#5b5868;line-height:1.65}
.abrow{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:12.5px}
.abrow .n{width:64px;flex:none;color:__INK__;font-weight:600}
.abrow .bars{flex:1}
.abrow .bar2{height:7px;border-radius:99px;background:#f0eef3;overflow:hidden;margin:2px 0}
.abrow .bar2 i{display:block;height:100%;border-radius:99px}
.legend{font-size:11.5px;color:#9a97a6;margin-bottom:4px}
.legend i{display:inline-block;width:10px;height:6px;border-radius:9px;margin:0 3px 1px 8px;vertical-align:middle}
.mini{display:flex;gap:8px;font-size:13px;color:#5b5868;margin:4px 0}
.mini b{color:__INK__}
"""
QREF = r"第\s*\d+(?:\s*[、，,和]\s*\d+)*\s*题"
MAIN_FIELDS = ("surprise", "engine", "roots", "position")
OLD_FIELDS = ("insights", "talents", "armor", "this_week", "avoid", "city_note", "watch_out")
EVIDENCE_KEYS = ("画像", "最意外的一点", "发动机", "本事", "底色", "要留意", "职业")


def _main_texts(data):
    pf = data.get("portrait") or {}
    out = [("portrait", pf.get("name", "")), ("portrait", pf.get("line", ""))]
    out += [(k, data.get(k, "")) for k in MAIN_FIELDS]
    out += [("skills", "%s %s" % (x.get("name", ""), x.get("line", ""))) for x in data.get("skills", [])]
    out += [("skills_note", data.get("skills_note", ""))]
    out += [("watch", x) for x in data.get("watch", [])]
    out += [("careers", x) for x in data.get("careers", [])]
    return out


def check_result(data, sig):
    """v0.5 的报告只放结论：正文不写题号、不写推导、不出现“水土”，没有行动建议；依据放进 evidence，在附录里折叠。"""
    warns = []
    for k in list(data.keys()):
        if any(b in k for b in ("原话", "quote")):
            warns.append("result.json 里有字段 %s：报告不使用用户原话，已忽略" % k)
            data.pop(k)
    old = [k for k in OLD_FIELDS if k in data]
    if old:
        warns.append("v0.5 不再使用这些字段，已忽略：%s" % "、".join(old))
    pf = data.get("portrait") or {}
    if not pf.get("name") or not pf.get("line"):
        warns.append("缺少 portrait.name（画像名字）或 portrait.line（一句话描述）")
    elif len(pf["name"]) > 6:
        warns.append("画像名字“%s”太长，建议 2 到 5 个字" % pf["name"])
    for k in MAIN_FIELDS:
        if not data.get(k):
            warns.append("缺少 %s" % k)
    sk = data.get("skills", [])
    if not 2 <= len(sk) <= 5:
        warns.append("skills（你的本事）写 2 到 5 条，现在是 %d 条" % len(sk))
    if not 1 <= len(data.get("watch", [])) <= 3:
        warns.append("watch（要留意）写 1 到 3 条")
    cs = data.get("careers", [])
    if not 3 <= len(cs) <= 5:
        warns.append("careers（适合的职业）写 3 到 5 个，现在是 %d 个" % len(cs))
    if any(not isinstance(c, str) or len(c) > 20 for c in cs):
        warns.append("careers 只写职业名称（字符串，20 字以内），不写解说")
    for field, txt in _main_texts(data):
        txt = str(txt)
        if re.search(QREF, txt):
            warns.append("%s 里出现了题号：正文只放结论，题号写进 evidence" % field)
        if "水土" in txt:
            warns.append("%s 里出现了“水土”：正文用“底色”“成长环境”这类说法" % field)
        if any(w in txt for w in ("推测", "推断", "因为你在", "你选了")):
            warns.append("%s 里有推导过程的字眼，正文直接写结论" % field)
    ev_ = data.get("evidence") or {}
    for k in ("最意外的一点", "发动机", "本事", "底色"):
        items = ev_.get(k, [])
        if not items or not all(re.search(QREF, str(x)) for x in items):
            warns.append("evidence 里“%s”的依据缺失，或没写成“第 N 题选了 X”" % k)
    if sig["reliability"]["level"] == "低":
        warns.append("整体可信度低：不该出完整报告，先请用户重答")
    return warns


def ability_rows(sig):
    rows = []
    for k in sorted(AB_ORDER, key=lambda k: -(sig["abilities"][k]["good"] + sig["abilities"][k]["drive"])):
        a = sig["abilities"][k]
        gw = min(100, a["good"] * 25)
        dw = min(100, a["drive"] * 25)
        rows.append('<div class="abrow"><span class="n">%s</span><div class="bars">'
                    '<div class="bar2"><i style="width:%d%%;background:__ACCENT__"></i></div>'
                    '<div class="bar2"><i style="width:%d%%;background:#f2b84b"></i></div></div></div>' % (
                        E(a["name"]), max(gw, 3), max(dw, 3)))
    return ('<div class="legend"><i style="background:__ACCENT__"></i>做得好<i style="background:#f2b84b"></i>来劲、想用</div>%s'
            % "".join(rows))


def appendix(sig, data, pr, types):
    ev_ = data.get("evidence") or {}
    parts = ['<details class="appx"><summary>这些结论是怎么来的（点开看）</summary>',
             '<p>报告完全根据你在 %d 道选择题里的选择推出来，下面是每部分对应的题。</p>' % N_Q]
    for k in EVIDENCE_KEYS:
        if ev_.get(k):
            parts.append('<h4>%s</h4>%s' % (E(k), _ul(ev_[k])))
    parts.append('<h4>8 项本事的证据多少</h4>' + ability_rows(sig))
    w = sig["water"]
    if w["confidence"] != "低" and not ev_.get("底色"):
        parts.append('<h4>成长环境</h4>%s' % _ul(w["evidence"]))
    if sig["cities"]:
        parts.append('<h4>为什么是这几座城市</h4><p>城市特点是常识印象，没有联网核实；不是建议搬家，有机会可以去住一阵试试。</p>%s'
                     % _ul(["%s：%s" % (c["name"], "；".join(c["why"])) for c in sig["cities"]]))
    ax_rows = ['<div class="ax"><span class="l">%s %d%%</span><div class="bar"><i style="width:%d%%"></i></div>'
               '<span class="r">%d%% %s</span></div>' % (E(ax["p1"]), ax["pct1"], ax["pct1"], ax["pct2"], E(ax["p2"]))
               for ax in sig["axes"]]
    parts.append('<h4>做事风格（奶茶人格从这里来）</h4>%s' % "".join(ax_rows))
    a, c = pr["a"], pr["c"]
    parts.append('<h4>和谁最搭，和谁最冲</h4><div class="mini"><b>最搭</b>%s %s：%s</div>'
                 '<div class="mini"><b>最冲</b>%s %s：%s</div>' % (
                     E(a["emoji"]), E(a["name"]), E(pr["why_a"]), E(c["emoji"]), E(c["name"]), E("；".join(pr["tips"][:2]))))
    rel = sig["reliability"]
    rows = [r["text"] for r in rel["repeats"]] + rel["notes"]
    parts.append('<h4>答题一致性：%s</h4><p>%s</p>%s' % (E(rel["level"]), E(rel["summary"]), _ul(rows)))
    parts.append('</details>')
    return "".join(parts)


def build_report(sig, t, types, data, sample):
    p = palette(t)
    name, sub, emoji = names(t)
    pr = partners(sig["code"], types)
    rel = sig["reliability"]
    css = _css(p) + EXTRA_CSS.replace("__INK__", p["ink"]).replace("__ACCENT__", p["accent"]).replace(
        "__SOFT__", p["soft"]).replace("__FONT__", FONT)
    pf = data.get("portrait") or {}
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>我的隐藏天赋报告</title><style>%s</style></head><body><div class="wrap">' % css]
    if sample:
        parts.append('<div class="ribbon">示例 · 虚构人物和虚构答案，仅用于展示报告样式</div>')
    if rel["level"] == "低":
        parts.append('<div class="alarm"><b>⚠ 这次的结果不可靠</b>%s。下面的内容只能当娱乐看，建议重新答一遍再看。</div>'
                     % E("；".join(rel["reasons"])))
    elif rel["level"] == "中":
        parts.append('<div class="alarm"><b>有几处答案不太一致</b>部分结论可能不够准，看的时候打个折扣。</div>')
    parts.append(
        '<div class="hero"><div class="k">我的隐藏天赋报告</div><div class="stage">%s%s</div>'
        '<div class="pname">%s</div><div class="pline">%s</div>'
        '<div class="milk">我的奶茶人格 · <b>%s</b>　“%s”</div>'
        '<div class="chips">%s</div></div>' % (
            confetti(t, [30, 34, 28, 30]), cup_svg(t), E(pf.get("name", name)), E(pf.get("line", t["line"])),
            E(name), E(t["order"]), "".join("<span>%s</span>" % E(a["winner"]) for a in sig["axes"])))
    if data.get("surprise"):
        parts.append('<div class="wow"><b>最意外的一点</b><p>%s</p></div>' % E(data["surprise"]))
    if data.get("engine"):
        parts.append('<div class="sec"><b>你的发动机</b><p>%s</p></div>' % E(data["engine"]))
    if data.get("skills"):
        rows = "".join('<div class="sk"><span class="n">%s</span><span class="t">%s</span>%s</div>' % (
            E(x.get("name", "")), E(x.get("line", "")), '<span class="eng">发动机</span>' if x.get("engine") else "")
            for x in data["skills"])
        note = '<div class="sknote">%s</div>' % E(data["skills_note"]) if data.get("skills_note") else ""
        parts.append('<div class="sec"><b>你的本事</b>%s%s</div>' % (rows, note))
    if data.get("roots"):
        parts.append('<div class="sec"><b>你的底色</b><p>%s</p></div>' % E(data["roots"]))
    if data.get("watch"):
        parts.append('<div class="sec"><b>要留意</b>%s</div>' % _ul(data["watch"]))
    go = []
    if data.get("position"):
        go.append('<div class="pos">%s</div>' % E(data["position"]))
    if data.get("careers"):
        go.append('<div class="lb">适合的职业</div><div class="pills">%s</div>' % "".join(
            "<span>%s</span>" % E(c) for c in data["careers"]))
    if sig["cities"]:
        go.append('<div class="lb">适合的城市</div><div class="pills">%s</div>' % "".join(
            "<span>%s</span>" % E(c["name"]) for c in sig["cities"]))
    if go:
        parts.append('<div class="sec go"><b>往哪走</b>%s</div>' % "".join(go))
    parts.append(appendix(sig, data, pr, types).replace("__ACCENT__", p["accent"]))
    parts.append('<div class="foot">这份报告根据你在 %d 道选择题里的选择推断而来，用来帮你看见可能性，不是心理诊断，也不预测你的未来。'
                 '职业和城市是参考，没有结合最新的行业与薪资数据，做决定前请自己核实。</div></div></body></html>' % N_Q)
    return "".join(parts)


def build_share(sig, t, types, data, entry, sample):
    p = palette(t)
    name, sub, emoji = names(t)
    pr = partners(sig["code"], types)
    pf = data.get("portrait") or {}
    if sig["reliability"]["level"] == "低" or not pf.get("name"):
        msg = "答案前后对不上，先不下结论" if sig["reliability"]["level"] == "低" else "还没写画像"
        card = '<div class="card"><div class="h">从选择里看到的我</div><div class="pl">%s</div></div>' % msg
    else:
        card = ('<div class="card"><div class="h">我是</div><div class="pn">%s</div><div class="pl">%s</div></div>'
                % (E(pf["name"]), E(pf.get("line", ""))))
    css = SHARE_CSS + SHARE_EXTRA
    for k, v in {"__BG__": p["bg"], "__ACCENT__": p["accent"], "__INK__": p["ink"], "__SOFT__": p["soft"],
                 "__SOFT2__": mix(p["accent"], "#ffffff", 0.7), "__DOT__": mix(p["accent"], "#ffffff", 0.7),
                 "__FONT__": FONT}.items():
        css = css.replace(k, v)
    if sig["reliability"]["level"] == "低":
        ribbon = '<div class="q" style="color:#b0442f">⚠ 结果不可靠 · 建议重测</div>'
    elif sample:
        ribbon = '<div class="q">示例 · 虚构人物</div>'
    else:
        ribbon = '<div class="q">你是哪一杯奶茶？</div>'
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>分享图</title><style>%s</style></head><body>'
        '<div class="dots"></div><div class="blob"></div><div class="c">'
        '<div class="top"><div class="pill">隐藏天赋发现</div>%s</div>'
        '<div class="stage">%s%s</div>'
        '<div class="name">%s</div><div class="sub">%s</div><div class="bubble">“%s”</div>'
        '%s'
        '<div class="match">'
        '<div class="mc"><div class="em">%s</div><div><div class="lb">最搭</div><div class="nm">%s</div></div></div>'
        '<div class="mc bad"><div class="em">%s</div><div><div class="lb">最冲</div><div class="nm">%s</div></div></div></div>'
        '<div class="ft">%s</div></div></body></html>' % (
            css, ribbon, confetti(t, [64, 72, 60, 64]), cup_svg(t, "s"), E(name), E(sub), E(t["order"]), card,
            E(pr["a"]["emoji"]), E(pr["a"]["name"]), E(pr["c"]["emoji"]), E(pr["c"]["name"]), E(entry)))


SHARE_EXTRA = """
.stage{height:420px}
.stage svg{width:290px;margin-left:-145px}
.name{font-size:108px}
.card{margin-top:22px;text-align:center;padding:24px 44px 28px}
.card .h{margin-bottom:0}
.pn{font-size:76px;font-weight:700;line-height:1.15;color:__ACCENT__}
.pl{font-size:33px;line-height:1.5;margin-top:10px;font-weight:700}
"""


def find_chrome():
    """找一个能无头截图的 Chromium 内核浏览器：环境变量 CHROME_PATH 优先，再找常见安装位置，最后查 PATH。"""
    import shutil
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return env
    for c in CHROME_PATHS:
        if os.path.exists(c):
            return c
    for n in CHROME_NAMES:
        found = shutil.which(n)
        if found:
            return found
    return None


def screenshot(html_path, png_path, w, h):
    chrome = find_chrome()
    if not chrome:
        return False, "没找到 Chrome / Edge / Chromium（装一个，或用环境变量 CHROME_PATH 指到它）。报告 HTML 已生成，只是没有分享图"
    prof = os.path.join(os.path.dirname(png_path), ".chrome-profile")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           "--user-data-dir=" + prof, "--window-size=%d,%d" % (w, h),
           "--force-device-scale-factor=1", "--screenshot=" + png_path,
           "file://" + os.path.abspath(html_path)]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    except Exception as exc:  # noqa
        return False, str(exc)
    finally:
        if os.path.isdir(prof):
            import shutil
            shutil.rmtree(prof, ignore_errors=True)
    ok = os.path.exists(png_path) and os.path.getsize(png_path) > 0
    return ok, "" if ok else "Chrome 未生成图片"


def cmd_ask(args):
    if not 1 <= args.batch <= len(BATCHES):
        raise ValueError("段号是 1 到 %d" % len(BATCHES))
    print(batch_text(args.batch) if args.text else batch_card(args.batch))


def cmd_check(args):
    ids = batch_ids(args.batch)
    got = parse_answers(args.reply, ids)
    print(json.dumps({"batch": args.batch, "letters": "".join(got[i] or "-" for i in ids),
                      "read_as": ["%d%s" % (i, got[i] or "-") for i in ids]}, ensure_ascii=False))


def cmd_score(args):
    sig = analyze(args.answers)
    types = load_types()
    if args.text:
        print(text_summary(sig, types))
        return
    t = types[sig["code"]]
    sig["type"] = {"name": t["name"], "order": t["order"], "line": t["line"]}
    print(json.dumps(sig, ensure_ascii=False, indent=1))


def cmd_questions(args):
    if args.md:
        print(questions_md())
    else:
        for n in range(1, len(BATCHES) + 1):
            print(batch_text(n) + "\n\n" + "-" * 20 + "\n")


def cmd_render(args):
    try:
        with open(args.result, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError("找不到结果文件：%s" % args.result)
    except json.JSONDecodeError as exc:
        raise ValueError("结果文件不是合法的 JSON（%s）：%s" % (exc, args.result))
    if not isinstance(data, dict) or not data.get("answers"):
        raise ValueError("结果文件里没有 answers（46 个字母）。格式见 SKILL.md 里的示例")
    sig = analyze(data["answers"])
    types = load_types()
    t = types[sig["code"]]
    sample = bool(data.get("sample"))
    warns = check_result(data, sig)
    os.makedirs(args.out, exist_ok=True)
    pre = args.prefix + "-" if args.prefix else ""
    report_path = os.path.join(args.out, pre + "隐藏天赋报告.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(build_report(sig, t, types, data, sample))
    out = {"code": sig["code"], "type": t["name"], "reliability": sig["reliability"]["level"],
           "water": sig["water"]["name"], "cities": [c["kind"] + "·" + c["name"] for c in sig["cities"]], "report": report_path}
    if sig["reliability"].get("warning"):
        out["reliability_warning"] = sig["reliability"]["warning"]
    if warns:
        out["warnings"] = warns
    if args.png:
        share_html = os.path.join(args.out, ".share-work.html")
        with open(share_html, "w", encoding="utf-8") as f:
            f.write(build_share(sig, t, types, data, args.entry, sample))
        png_path = os.path.join(args.out, pre + "隐藏天赋分享图.png")
        ok, why = screenshot(share_html, png_path, 1080, 1440)
        if ok:
            os.remove(share_html)
            out["share_png"] = png_path
        else:
            out["share_png_error"] = why
            out["share_html_kept"] = share_html
    print(json.dumps(out, ensure_ascii=False, indent=2))


def random_answers(rng):
    return "".join(rng.choice(list(Q[i]["opts"])) for i in sorted(Q))


def cmd_simulate(args):
    rng = random.Random(args.seed)
    types = load_types()
    n = args.n
    codes, rel, cls, water, city = Counter(), Counter(), Counter(), Counter(), Counter()
    has_hidden = 0
    n_eng, n_sk, no_eng = 0, 0, 0
    for _ in range(n):
        sig = analyze(random_answers(rng))
        n_eng += sum(1 for x in sig["profile"]["engine"] if x["level"] == "明显")
        n_sk += sum(1 for x in sig["profile"]["skills"] if x["level"] == "明显")
        no_eng += not any(x["level"] == "明显" for x in sig["profile"]["engine"] + sig["profile"]["skills"])
        codes[sig["code"]] += 1
        rel[sig["reliability"]["level"]] += 1
        hidden = False
        for a in sig["abilities"].values():
            if a["usable"]:
                cls[a["cls"]] += 1
                hidden = hidden or a["cls"] == "hidden"
        has_hidden += hidden
        water[sig["water"]["name"]] += 1
        for c in sig["cities"]:
            city[c["name"]] += 1
    print("随机作答 %d 组（每题在自己的选项里均匀随机），seed=%d\n\n16 型分布：" % (n, args.seed))
    flagged = []
    for code in sorted(types, key=lambda c: -codes[c]):
        pct = codes[code] * 100.0 / n
        mark = "  <-- 超出 1%~15%" if (pct < 1 or pct > 15) else ""
        if mark:
            flagged.append(code)
        print("  %s %-6s %5.2f%%%s" % (code, types[code]["name"], pct, mark))
    print("  结论：%s" % ("全部在 1%~15% 之间" if not flagged else "需要调整：" + "、".join(flagged)))
    print("\n整体可信度：" + "，".join("%s %.1f%%" % (k, rel[k] * 100.0 / n) for k in LEVELS))
    print("每人平均能写出的能力结论：" + "，".join("%s %.2f" % (CLS_NAME[k], cls[k] / float(n)) for k in ("hidden", "learned", "realized", "tug", "spark")))
    print("至少有 1 条“没用上的长处”的比例：%.1f%%" % (has_hidden * 100.0 / n))
    print("画像（随机作答）：平均“明显”的发动机 %.2f 项、本事 %.2f 项；两样都没有“明显”项的比例 %.1f%%" % (n_eng / float(n), n_sk / float(n), no_eng * 100.0 / n))
    print("水土分布：" + "，".join("%s %.1f%%" % (k, v * 100.0 / n) for k, v in water.most_common()))
    print("城市被推荐最多的前 10：" + "，".join("%s %.1f%%" % (k, v * 100.0 / n) for k, v in city.most_common(10)))
    print("一次都没被推荐过的城市：" + ("、".join(c["name"] for c in load_cities() if c["name"] not in city) or "无"))
    print("\n极端作答：")
    pats = [("全选 A", "A" * N_Q), ("全选 B", "B" * N_Q), ("ABAB 轮着点", "AB" * (N_Q // 2)),
            ("ABCD 轮着点", "".join(("ABCD"[(i - 1) % 4] if "ABCD"[(i - 1) % 4] in Q[i]["opts"] else "AB"[(i - 1) % 2]) for i in sorted(Q)))]
    for label, s in pats:
        sig = analyze(s)
        usable = sum(1 for a in sig["abilities"].values() if a["usable"])
        print("  %s → 可信度 %s；能写的能力结论 %d 条；城市 %d 个；%s" % (
            label, sig["reliability"]["level"], usable, len(sig["cities"]), "；".join(sig["reliability"]["reasons"])))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("batch", type=int)
    a.add_argument("--text", action="store_true")
    a.set_defaults(fn=cmd_ask)
    c = sub.add_parser("check")
    c.add_argument("batch", type=int)
    c.add_argument("reply")
    c.set_defaults(fn=cmd_check)
    s = sub.add_parser("score")
    s.add_argument("answers")
    s.add_argument("--text", action="store_true")
    s.set_defaults(fn=cmd_score)
    q = sub.add_parser("questions")
    q.add_argument("--md", action="store_true")
    q.set_defaults(fn=cmd_questions)
    r = sub.add_parser("render")
    r.add_argument("result")
    r.add_argument("--out", default="./documents")
    r.add_argument("--prefix", default="")
    r.add_argument("--png", action="store_true")
    r.add_argument("--entry", default="来测测，你是哪一杯奶茶 🧋")
    r.set_defaults(fn=cmd_render)
    m = sub.add_parser("simulate")
    m.add_argument("--n", type=int, default=2000)
    m.add_argument("--seed", type=int, default=7)
    m.set_defaults(fn=cmd_simulate)
    args = p.parse_args()
    try:
        args.fn(args)
    except ValueError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
