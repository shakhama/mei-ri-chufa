#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容 / SEO 资产自动化引擎  ——  真·睡后收入
============================================
把你的选题 + 素材，自动渲染成 SEO 友好的静态内容站，
并通过「定时发布」让站点每天自动长大：你睡觉，资产在累积。

核心思路（不投机）：
  - 内容是资产：每篇文章长期带来搜索流量，流量接广告/带货=被动收入。
  - 自动化发布：cron / 计划任务每天跑一次 `next`，站点稳步扩张。
  - 结构化 SEO：每页带 canonical、OpenGraph、JSON-LD(Article+FAQ)、sitemap、RSS。

运行：
    python generate.py build        # 渲染所有已发布文章 + 站点地图/RSS
    python generate.py next         # 发布下一篇未发布的文章，再重建全站
    python generate.py preview      # 本地预览（启动 http.server）
    python generate.py reset        # 把所有文章标记为未发布（重新来过）

接入 AI 写作（可选，非必须）：
    设置环境变量 OPENAI_API_KEY 后，程序会用大模型把你的要点扩写成正文；
    不设则用你提供的素材做结构化排版。两种方式都能离线/在线跑。
"""

import json
import os
import sys
import html
import argparse
import datetime
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
TPL = os.path.join(HERE, "template.html")
TOPICS = os.path.join(HERE, "topics.json")


def load_topics():
    with open(TOPICS, "r", encoding="utf-8") as f:
        return json.load(f)


def save_topics(data):
    with open(TOPICS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today():
    return datetime.date.today().isoformat()


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# 可选：AI 扩写（设置 OPENAI_API_KEY 后启用，失败自动回退模板）
# ---------------------------------------------------------------------------
def ai_expand(title, bullets):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        prompt = "用简体中文写一段约120字、通顺自然的科普性正文，主题：%s。要点：%s。不要标题，不要列表符号。" % (
            title, "；".join(bullets))
        payload = json.dumps({
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % key},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
def render_article(topic, site, related):
    with open(TPL, "r", encoding="utf-8") as f:
        tpl = f.read()

    slug = topic["slug"]
    url = "%s/%s.html" % (site["domain"].rstrip("/"), slug)
    kw = topic.get("keywords", [])
    desc = topic.get("summary", "")
    date = topic.get("publish_date") or today()

    # 正文
    parts = []
    parts.append("<header class='site'><a href='index.html'>%s</a></header>" % esc(site["name"]))
    parts.append("<h1>%s</h1>" % esc(topic["title"]))
    parts.append("<div class='meta'>发布于 %s · 关键词：%s</div>" % (esc(date), esc("、".join(kw))))
    if desc:
        parts.append("<p><strong>%s</strong></p>" % esc(desc))

    for sec in topic.get("sections", []):
        parts.append("<h2>%s</h2>" % esc(sec.get("h2", "")))
        body = sec.get("body")
        if not body:
            body = ai_expand(sec.get("h2", ""), sec.get("bullets", []))
        if body:
            parts.append("<p>%s</p>" % esc(body))
        bl = sec.get("bullets")
        if bl:
            parts.append("<ul>" + "".join("<li>%s</li>" % esc(b) for b in bl) + "</ul>")

    # FAQ
    faq = topic.get("faq", [])
    if faq:
        parts.append("<section class='faq'><h2>常见问题</h2>")
        for item in faq:
            parts.append("<details><summary>%s</summary><p>%s</p></details>" % (
                esc(item.get("q", "")), esc(item.get("a", ""))))
        parts.append("</section>")

    # 相关阅读（内链，利于 SEO）
    if related:
        parts.append("<section class='related'><h3>相关阅读</h3>")
        for r in related:
            parts.append("<div class='card'><a href='%s.html'>%s</a><p>%s</p></div>" % (
                esc(r["slug"]), esc(r["title"]), esc(r.get("summary", ""))))
        parts.append("</section>")

    body_html = "\n".join(parts)

    # JSON-LD：Article + FAQPage
    article_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": topic["title"],
        "description": desc,
        "datePublished": date,
        "author": {"@type": "Person", "name": site.get("author", "")},
        "publisher": {"@type": "Organization", "name": site["name"]},
        "mainEntityOfPage": url,
    }
    head_extra = "<script type='application/ld+json'>%s</script>" % json.dumps(article_ld, ensure_ascii=False)
    if faq:
        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [{"@type": "Question",
                            "name": it["q"],
                            "acceptedAnswer": {"@type": "Answer", "text": it["a"]}}
                           for it in faq],
        }
        head_extra += "\n<script type='application/ld+json'>%s</script>" % json.dumps(faq_ld, ensure_ascii=False)

    page = (tpl
            .replace("{{LANG}}", esc(site.get("lang", "zh-CN")))
            .replace("{{TITLE}}", esc(topic["title"]))
            .replace("{{META_DESC}}", esc(desc))
            .replace("{{CANONICAL}}", esc(url))
            .replace("{{HEAD_EXTRA}}", head_extra)
            .replace("{{BODY}}", body_html)
            .replace("{{SITE_NAME}}", esc(site["name"]))
            .replace("{{YEAR}}", str(datetime.date.today().year)))
    return page


def build_index(site, published):
    with open(TPL, "r", encoding="utf-8") as f:
        tpl = f.read()
    published = sorted(published, key=lambda t: t.get("publish_date", ""), reverse=True)
    parts = ["<header class='site'><a href='index.html'>%s</a></header>" % esc(site["name"])]
    parts.append("<h1>%s</h1>" % esc(site["name"]))
    parts.append("<p>%s</p>" % esc(site.get("description", "")))
    for t in published:
        parts.append("<div class='card'><a href='%s.html'>%s</a><p>%s</p></div>" % (
            esc(t["slug"]), esc(t["title"]), esc(t.get("summary", ""))))
    body_html = "\n".join(parts)
    page = (tpl
            .replace("{{LANG}}", esc(site.get("lang", "zh-CN")))
            .replace("{{TITLE}}", esc(site["name"]))
            .replace("{{META_DESC}}", esc(site.get("description", "")))
            .replace("{{CANONICAL}}", esc(site["domain"].rstrip("/") + "/index.html"))
            .replace("{{HEAD_EXTRA}}", "")
            .replace("{{BODY}}", body_html)
            .replace("{{SITE_NAME}}", esc(site["name"]))
            .replace("{{YEAR}}", str(datetime.date.today().year)))
    return page


def build_sitemap(site, published):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for t in published:
        lines.append("  <url><loc>%s/%s.html</loc></url>" % (site["domain"].rstrip("/"), t["slug"]))
    lines.append("</urlset>")
    return "\n".join(lines)


def build_feed(site, published):
    published = sorted(published, key=lambda t: t.get("publish_date", ""), reverse=True)
    items = []
    for t in published:
        items.append(
            "    <item><title>%s</title><link>%s/%s.html</link>"
            "<guid>%s/%s.html</guid><description>%s</description>"
            "<pubDate>%s</pubDate></item>" % (
                esc(t["title"]), site["domain"].rstrip("/"), t["slug"],
                site["domain"].rstrip("/"), t["slug"], esc(t.get("summary", "")),
                t.get("publish_date", "")))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>'
            "<title>%s</title><link>%s</link><description>%s</description>"
            "%s</channel></rss>" % (
                esc(site["name"]), esc(site["domain"].rstrip("/")),
                esc(site.get("description", "")), "\n".join(items)))


def build_robots(site):
    return "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % site["domain"].rstrip("/")


def build_all(data):
    os.makedirs(OUT, exist_ok=True)
    site = data["site"]
    published = [t for t in data["topics"] if t.get("publish_date")]
    for t in published:
        related = [x for x in published if x["slug"] != t["slug"]][:3]
        html_doc = render_article(t, site, related)
        with open(os.path.join(OUT, t["slug"] + ".html"), "w", encoding="utf-8") as f:
            f.write(html_doc)
        print("  生成文章: %s.html" % t["slug"])
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(site, published))
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(build_sitemap(site, published))
    with open(os.path.join(OUT, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(build_feed(site, published))
    with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(build_robots(site))
    print("  生成: index.html / sitemap.xml / feed.xml / robots.txt")


def publish_next(data):
    pending = [t for t in data["topics"] if not t.get("publish_date")]
    if not pending:
        print("所有文章都已发布，没有可发布的了。")
        return False
    t = pending[0]
    t["publish_date"] = today()
    save_topics(data)
    print("发布新文章: %s (%s)" % (t["title"], t["publish_date"]))
    return True


def main():
    ap = argparse.ArgumentParser(description="内容/SEO 资产自动化引擎")
    ap.add_argument("cmd", nargs="?", default="build",
                    choices=["build", "next", "preview", "reset"])
    args = ap.parse_args()

    data = load_topics()

    if args.cmd == "reset":
        for t in data["topics"]:
            t["publish_date"] = None
        save_topics(data)
        print("已重置：所有文章标记为未发布。")
        return

    if args.cmd == "next":
        if publish_next(data):
            data = load_topics()  # 重新读取（publish_next 已写盘）
        else:
            return

    if args.cmd == "build" or args.cmd == "next":
        print("构建站点 -> %s" % OUT)
        build_all(data)
        return

    if args.cmd == "preview":
        import http.server
        os.chdir(OUT)
        print("本地预览：http://localhost:8000  (Ctrl+C 退出)")
        http.server.HTTPServer(("127.0.0.1", 8000),
                               http.server.SimpleHTTPRequestHandler).serve_forever()


if __name__ == "__main__":
    main()
