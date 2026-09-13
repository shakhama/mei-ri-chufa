#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「知乎版」稿件。

为什么要单独生成一版，而不是把站内文章原样搬过去：
1. 知乎域名权重远高于新站，一模一样的内容若被知乎先收录，
   搜索引擎可能把自家站判定为转载方而降权。
   —— 所以站内必须首发，知乎版要精简并链回原文。
2. 知乎读者偏好开门见山、结构化、少废话的写法，与站内 SEO 文略有差异。

产物：
    zhihu/<slug>.md   适合人工复制粘贴（知乎编辑器可识别大部分 Markdown）
    zhihu/<slug>.txt  纯文本版，适合自动化逐字输入（不依赖 Markdown 解析）

用法：
    python zhihu_draft.py            # 只为已发布的文章生成
    python zhihu_draft.py --all      # 为全部选题生成
    python zhihu_draft.py --slug xxx # 只生成指定一篇
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOPICS = os.path.join(HERE, "topics.json")
OUT = os.path.join(HERE, "zhihu")

MAX_TITLE = 100


def build_md(topic, site, url):
    title = topic["title"]
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE - 1] + "…"

    lines = []
    lines.append("# " + title)
    lines.append("")
    lines.append(topic.get("summary", ""))
    lines.append("")

    for sec in topic.get("sections", []):
        lines.append("## " + sec.get("h2", ""))
        lines.append("")
        if sec.get("body"):
            lines.append(sec["body"])
            lines.append("")
        for b in sec.get("bullets", []):
            lines.append("- " + b)
        lines.append("")

    faq = topic.get("faq", [])
    if faq:
        lines.append("## 常见问题")
        lines.append("")
        for item in faq:
            lines.append("**" + item.get("q", "") + "**")
            lines.append("")
            lines.append(item.get("a", ""))
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("本文首发于「%s」：%s" % (site["name"], url))
    lines.append("")
    lines.append("完整版与更多同类内容都在那边，感兴趣可以点过去看看。")
    lines.append("")
    return "\n".join(lines)


def build_txt(topic, site, url):
    """纯文本版：去掉 Markdown 标记，适合自动化逐字输入。"""
    title = topic["title"]
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE - 1] + "…"

    lines = [title, ""]
    lines.append(topic.get("summary", ""))
    lines.append("")

    for sec in topic.get("sections", []):
        lines.append(sec.get("h2", ""))
        if sec.get("body"):
            lines.append(sec["body"])
        for b in sec.get("bullets", []):
            lines.append("· " + b)
        lines.append("")

    faq = topic.get("faq", [])
    if faq:
        lines.append("常见问题")
        for item in faq:
            lines.append("问：" + item.get("q", ""))
            lines.append("答：" + item.get("a", ""))
        lines.append("")

    lines.append("本文首发于「%s」：%s" % (site["name"], url))
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="生成知乎版稿件")
    ap.add_argument("--all", action="store_true", help="为全部选题生成（默认只为已发布生成）")
    ap.add_argument("--slug", help="只生成指定 slug")
    args = ap.parse_args()

    data = json.load(open(TOPICS, encoding="utf-8"))
    site = data["site"]
    base = site["domain"].rstrip("/")

    if args.slug:
        targets = [t for t in data["topics"] if t["slug"] == args.slug]
    elif args.all:
        targets = data["topics"]
    else:
        targets = [t for t in data["topics"] if t.get("publish_date")]

    if not targets:
        print("没有符合条件的目标文章。")
        return

    os.makedirs(OUT, exist_ok=True)
    for t in targets:
        url = "%s/%s.html" % (base, t["slug"])
        md = build_md(t, site, url)
        txt = build_txt(t, site, url)
        with open(os.path.join(OUT, t["slug"] + ".md"), "w", encoding="utf-8") as f:
            f.write(md)
        with open(os.path.join(OUT, t["slug"] + ".txt"), "w", encoding="utf-8") as f:
            f.write(txt)
        print("生成: zhihu/%s.md  (%d 字符) + .txt" % (t["slug"], len(md)))

    print("\n共 %d 篇。原文链接已自动写入文末，用于把权重导回自家站。" % len(targets))


if __name__ == "__main__":
    main()
