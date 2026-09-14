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

网络说明：
    本机直连 GitHub 常被重置，脚本会先直连推送，失败后自动改用代理重试。
    代理地址取自环境变量 GIT_PROXY，未设置则用默认值 http://127.0.0.1:7897。
    更换代理工具/端口时无需改代码，例如：
        set GIT_PROXY=http://127.0.0.1:10809
    完全不需要代理的环境可设 GIT_PROXY=none 关闭重试。
"""

import os
import sys
import subprocess
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "generate.py")
REPORTS = os.path.join(HERE, "reports")
PY = sys.executable

# 代理默认值：本机系统代理端口（Clash 类工具常用 7897）
DEFAULT_PROXY = "http://127.0.0.1:7897"


def git_proxy():
    """返回本次使用的代理地址；设 GIT_PROXY=none 可彻底关闭代理重试。"""
    return (os.environ.get("GIT_PROXY") or DEFAULT_PROXY).strip()


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


def git_via_proxy(*args):
    """用代理执行一次 git 命令（仅对该命令生效，不写全局配置）。

    注意必须同时带 `-c http.sslBackend=openssl`：本机 Git for Windows 默认后端是
    schannel，走 HTTP 代理时 TLS 握手会失败（SSL/TLS connection failed），
    换成 openssl 后端后代理推送才稳定。
    """
    proxy = git_proxy()
    return run(["git",
                "-c", "http.sslBackend=openssl",
                "-c", "http.proxy=%s" % proxy,
                "-c", "https.proxy=%s" % proxy] + list(args))


def push_if_remote():
    """有远端就推送，返回推送结果文本。

    先直连尝试（网络正常时最快）；失败则自动改用代理重试，
    避免本机直连 GitHub 被重置导致每日发布卡在最后一步。
    """
    rrc, remote, _ = git("remote", "get-url", "origin")
    if rrc != 0:
        return "尚未配置 GitHub 远端，仅本地提交。配置：`git remote add origin <仓库地址>`"

    prc, pout, perr = git("push")
    if prc == 0:
        return "已推送到 GitHub：%s" % remote

    proxy = git_proxy()
    if proxy.lower() == "none":
        return "推送失败（已关闭代理重试）：%s" % (perr or pout)

    rrc2, pout2, perr2 = git_via_proxy("push")
    if rrc2 == 0:
        return ("直连推送失败，已通过代理 %s 重试成功：%s"
                % (proxy, remote))
    return ("推送失败（直连与代理 %s 均失败）：%s"
            % (proxy, (perr2 or pout2) or (perr or pout)))


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
