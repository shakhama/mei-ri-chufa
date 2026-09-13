#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日定时触发 —— 全自动流水线的一次执行

流程：
  1. 发布下一篇未发布的文章
  2. 重建全站（SEO 页面 + sitemap + RSS）
  3. 提交内容变更
  4. 推送到 GitHub（若已配远端，进而触发 Pages 自动部署）
  5. 生成本次运行的报告并提交

用法：
    python daily_run.py
"""

import os
import sys
import subprocess
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "generate.py")
REPORTS = os.path.join(HERE, "reports")
PY = sys.executable


def run(cmd):
    p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def git(*args):
    return run(["git"] + list(args))


def commit_if_changed(message):
    """有改动就提交，返回提交结果文本；无改动返回说明。"""
    _, status, _ = git("status", "--porcelain")
    if not status:
        return "本地无变更，跳过提交。"
    git("add", "-A")
    _, out, err = git("commit", "-m", message)
    return out or err


def push_if_remote():
    """有远端就推送，返回推送结果文本。"""
    rrc, remote, _ = git("remote", "get-url", "origin")
    if rrc != 0:
        return "尚未配置 GitHub 远端，仅本地提交。配置：`git remote add origin <仓库地址>`"
    prc, pout, perr = git("push")
    if prc == 0:
        return "已推送到 GitHub：%s" % remote
    return "推送失败（多因未配置凭据）：%s" % (perr or pout)


def main():
    today = datetime.date.today().isoformat()

    # 1. 发布下一篇
    _, out, err = run([PY, GEN, "next"])
    publish = out or err or "(无输出)"

    # 2. 构建全站
    _, out, err = run([PY, GEN, "build"])
    build = out or err or "(无输出)"

    # 3. 提交内容变更
    sync1 = commit_if_changed("chore: daily publish %s" % today)

    # 4. 推送（有远端才推）
    push_result = push_if_remote()

    # 5. 写报告并提交
    os.makedirs(REPORTS, exist_ok=True)
    report_path = os.path.join(REPORTS, today + ".md")
    report = "\n".join([
        "# 每日构建报告 %s" % today,
        "",
        "## 1. 发布",
        publish,
        "",
        "## 2. 构建",
        build,
        "",
        "## 3. 同步 GitHub",
        sync1,
        push_result,
        "",
    ])
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    sync2 = commit_if_changed("docs: daily report %s" % today)
    if sync1.startswith("已推送") or sync2 != "本地无变更，跳过提交。":
        push_result2 = push_if_remote()
    else:
        push_result2 = "(无新提交，未推送)"

    print(report)
    print("---")
    print("报告提交: %s" % sync2)
    print("报告推送: %s" % push_result2)
    print("报告文件: %s" % report_path)


if __name__ == "__main__":
    main()
