#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git 协议推不上去时的兜底：用 GitHub Git Data API 直接提交并快进远端分支。

什么时候用
----------
本机到 github.com:443 走不通（直连超时 / 代理没开 / 中间设备拦截），
但 api.github.com 可达时。先用 `git push` 重试若干次确认真的不通，再来用这个。

用法
----
    python push_via_api.py                  # 把本地领先远端的提交推上去
    python push_via_api.py --dry-run        # 只看将要上传什么，不改动远端
    python push_via_api.py --branch main

它做的事
--------
  1. 取本地 HEAD 与远端 branch 的 diff 文件列表（默认全推，不挑）
  2. 每个文件转成 LF 后建 blob
  3. 以远端当前 tree 为 base_tree，覆盖这些文件，建新 tree
  4. 用**本地提交的 author / committer / message / parent** 建 commit
  5. force 更新远端 branch 指向它

两个必须知道的坑（都是 2026-10-12 实测踩出来的）
------------------------------------------------
坑 1 · CRLF
    直接把磁盘字节当 blob 上传，会把 Windows 的 CRLF 一起传上去，
    而 git 本地提交时会做 CRLF→LF 规范化。结果远端 tree 与本地 tree 不一致，
    本地再也重建不出同一个 commit，两端就此分叉。
    → 上传前必须先 `replace(b"\\r\\n", b"\\n")`。

坑 2 · committer 时间戳
    commit sha = f(tree, parent, author, committer, message)。
    就算 tree / parent / message 全对，只要让 API 自动生成 committer，
    时间戳就是"现在"，sha 必然和本地不同 → 依旧分叉，而 git 协议又不通、
    拉不回远端对象，这个分叉无法自动愈合。
    → 必须从本地 commit 里读出精确的 author / committer（含 unix 时间戳）一并传。

局限
----
- 只推**文件内容**，不管空目录、权限位、submodule。
- 需要 PAT：`git credential fill` 从 Windows 凭据管理器取，要求仓库写权限。
- 若远端在此期间被别人推过，force 会覆盖，用前先确认。
"""

import sys
import os
import json
import base64
import ssl
import subprocess
import urllib.request
import datetime
import argparse

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "shakhama/mei-ri-chufa"
API = "https://api.github.com"
UA = {"User-Agent": "wb-push-via-api", "Accept": "application/vnd.github+json"}

# urllib 在 Windows 会读注册表代理设置；代理软件没开时表现为
# "Tunnel connection failed: 502"，看起来像网络不通，其实是代理挂了。显式关掉。
OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))


def g(*args, **kw):
    p = subprocess.run(["git"] + list(args), cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, **kw)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def get_pat():
    p = subprocess.run(["git", "-c", "credential.helper=", "-c", "credential.helper=manager",
                        "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    for line in (p.stdout or "").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return None


def req(method, path, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(API + path, data=data, method=method, headers=dict(UA))
    if data:
        r.add_header("Content-Type", "application/json")
    with OP.open(r, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def iso(ts, tz):
    """git 内部 '1760203581 +0800' -> API 要的 ISO 8601"""
    sign = 1 if tz[0] == "+" else -1
    off = datetime.timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
    dt = datetime.datetime.fromtimestamp(int(ts), datetime.timezone(sign * off))
    return dt.isoformat()


def local_commit_meta(sha):
    rc, raw, err = g("cat-file", "commit", sha)
    if rc != 0:
        raise RuntimeError("读本地 commit 失败: %s" % err)
    head, _, message = raw.partition("\n\n")
    out = {"message": message + "\n"}
    for line in head.splitlines():
        if line.startswith("author "):
            out["author"] = line[7:]
        elif line.startswith("committer "):
            out["committer"] = line[10:]
        elif line.startswith("parent "):
            out.setdefault("parents", []).append(line[7:])
    return out


def split_ident(s):
    ne, ts, tz = s.rsplit(" ", 2)
    name, _, email = ne.rpartition(" <")
    return {"name": name, "email": email.rstrip(">"), "date": iso(ts, tz)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="main")
    ap.add_argument("--base", default=None, help="远端当前 sha，默认自动取")
    ap.add_argument("--files", default=None,
                    help="手动指定要上传的文件（逗号分隔）。远端 sha 在本地不存在、"
                         "自动 diff 取不到时用它。")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pat = get_pat()
    if not pat:
        print("取不到 PAT（凭据管理器里没有 git:https://github.com）")
        return 1
    UA["Authorization"] = "Bearer " + pat
    print("身份:", req("GET", "/user").get("login"))

    base = args.base or req("GET", "/repos/%s/git/ref/heads/%s" % (REPO, args.branch))["object"]["sha"]
    rc, head, _ = g("rev-parse", "HEAD")
    print("远端 %s = %s" % (args.branch, base[:7]))
    print("本地 HEAD   = %s" % head[:7])

    if head == base:
        print("本地与远端一致，无需推送。")
        return 0

    # 注意：远端 sha 常常不在本地对象库里（git 协议不通就拉不回来），
    # 这时 git diff 取不到东西，需要 --files 手动指定。
    files = []
    if args.files:
        files = [f.strip() for f in args.files.split(",") if f.strip()]
    else:
        rc, diff, err = g("diff", "--name-only", base, "HEAD")
        files = [f for f in diff.splitlines() if f.strip()]
        if not files and err:
            print("自动 diff 失败（远端 sha 不在本地对象库）：%s" % err[:120])
            print("请用 --files 手动列出要上传的文件。")
            return 1
    # 删除的文件排掉（API 建 tree 时删文件要传 sha=null，这里保守跳过）
    files = [f for f in files if os.path.exists(os.path.join(HERE, f))]
    if not files:
        print("没有需要上传的文件变更。")
        return 0
    print("将上传 %d 个文件:" % len(files))
    for f in files:
        print("   ", f)

    meta = local_commit_meta(head)
    if args.dry_run:
        print("\n[dry-run] 到此为止，未改动远端。")
        print("message:", meta["message"].splitlines()[0])
        return 0

    tree = []
    for f in files:
        raw = open(os.path.join(HERE, f), "rb").read().replace(b"\r\n", b"\n")
        blob = req("POST", "/repos/%s/git/blobs" % REPO,
                   {"content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"})
        tree.append({"path": f.replace("\\", "/"), "mode": "100644",
                     "type": "blob", "sha": blob["sha"]})
        print("  blob %-40s %s" % (f, blob["sha"][:7]))

    base_commit = req("GET", "/repos/%s/git/commits/%s" % (REPO, base))
    new_tree = req("POST", "/repos/%s/git/trees" % REPO,
                   {"base_tree": base_commit["tree"]["sha"], "tree": tree})
    rc2, local_tree, _ = g("rev-parse", "HEAD^{tree}")
    print("new tree = %s / 本地 tree = %s → %s"
          % (new_tree["sha"][:7], local_tree[:7],
             "一致" if new_tree["sha"] == local_tree else "不一致（检查换行/文件集）"))

    payload = {
        "message": meta["message"],
        "tree": new_tree["sha"],
        "parents": [base],
        "author": split_ident(meta["author"]),
        "committer": split_ident(meta["committer"]),
    }
    new_commit = req("POST", "/repos/%s/git/commits" % REPO, payload)
    print("new commit = %s (本地 %s) → %s"
          % (new_commit["sha"][:7], head[:7],
             "sha 一致" if new_commit["sha"] == head else "sha 不同（内容一致即可）"))

    req("PATCH", "/repos/%s/git/refs/heads/%s" % (REPO, args.branch),
        {"sha": new_commit["sha"], "force": True})
    print("远端 %s 已指向 %s" % (args.branch, new_commit["sha"][:7]))
    print("完成。注意：本地 HEAD 与远端 sha 可能不同（内容一致），"
          "网络恢复后跑一次 `git pull --rebase` 让 git 自动去重对齐。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
