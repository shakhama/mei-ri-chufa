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


def run(cmd, timeout=None):
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        # 超时绝不无限等待：返回明确的超时结果，交给上层走下一路重试
        return 124, "", "命令超时（%ss）：%s" % (timeout, " ".join(cmd[:6]))
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def git(*args, **kw):
    return run(["git"] + list(args), **kw)


def commit_if_changed(message):
    """有改动就提交，返回提交结果文本；无改动返回说明。"""
    _, status, _ = git("status", "--porcelain")
    if not status:
        return "本地无变更，跳过提交。"
    git("add", "-A")
    _, out, err = git("commit", "-m", message)
    return out or err


# 凭据链修正（2026-09-20 定位）：
# 本仓库继承了全局 credential.helper=helper-selector，该选择器在非交互环境
# （定时任务 / 自动化会话）里取不到凭据时会挂起等待终端输入，导致 push 永久卡死、
# 且**不报错**——表现为"生成与提交都成功、站点却停在旧版本"。
# 解决：先用 `-c credential.helper=` 清空 helper 列表（gitcredentials 规定空值即清空），
# 再指定 `manager`（Windows 凭据管理器，存有 git:https://github.com 的有效凭据）。
# 顺序不可颠倒，否则 helper-selector 仍在链上并继续卡死。
CRED_FIX = ["-c", "credential.helper=", "-c", "credential.helper=manager"]

# push 单路最长等待秒数。宁可失败报错，也不要无限挂起。
PUSH_TIMEOUT = 70


def git_via_proxy(*args, **kw):
    """用代理执行一次 git 命令（仅对该命令生效，不写全局配置）。

    注意必须同时带 `-c http.sslBackend=openssl`：本机 Git for Windows 默认后端是
    schannel，走 HTTP 代理时 TLS 握手会失败（SSL/TLS connection failed），
    换成 openssl 后端后代理推送才稳定。
    """
    proxy = git_proxy()
    cmd = ["git",
           "-c", "http.sslBackend=openssl",
           "-c", "http.proxy=%s" % proxy,
           "-c", "https.proxy=%s" % proxy] + CRED_FIX + list(args)
    return run(cmd, **kw)


def push_if_remote():
    """有远端就推送，返回推送结果文本。

    先直连尝试（网络正常时最快）；失败则自动改用代理重试，
    避免本机直连 GitHub 被重置导致每日发布卡在最后一步。
    """
    rrc, remote, _ = git("remote", "get-url", "origin")
    if rrc != 0:
        return "尚未配置 GitHub 远端，仅本地提交。配置：`git remote add origin <仓库地址>`"

    attempts = []
    proxy = git_proxy()

    # 1) 直连（修正凭据链后，这是最快也最常见成功的路径）
    prc, pout, perr = run(["git"] + CRED_FIX + ["push", "origin", "main"],
                          timeout=PUSH_TIMEOUT)
    if prc == 0:
        return "已推送到 GitHub：%s" % remote
    attempts.append("直连：%s" % (perr or pout or ("超时 %ss" % PUSH_TIMEOUT)))

    # 2) 代理重试
    if proxy.lower() == "none":
        return "推送失败（已关闭代理重试）：%s" % "；".join(attempts)

    rrc2, pout2, perr2 = git_via_proxy("push", "origin", "main",
                                       timeout=PUSH_TIMEOUT)
    if rrc2 == 0:
        return ("直连推送失败，已通过代理 %s 重试成功：%s"
                % (proxy, remote))
    attempts.append("代理 %s：%s" % (proxy, perr2 or pout2 or ("超时 %ss" % PUSH_TIMEOUT)))
    return "推送失败（直连与代理均失败）：%s" % "；".join(attempts)


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
