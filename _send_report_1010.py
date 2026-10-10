# -*- coding: utf-8 -*-
"""2026-10-10 日报 → 企业微信（用 argv 列表调用 node，避免 PowerShell 拆词）"""
import subprocess
import sys
import json
import os

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

NODE = "C:/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
WECOM = "C:/Users/Administrator/.workbuddy/binaries/node/cli-connector-packages/node_modules/@wecom/cli/bin/wecom.js"

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_report_content_1010.md"), encoding="utf-8") as f:
    content = f.read()

payload = {
    "chat_id": "wozNxoEQAAgOlLCTn45hIm0Z-MudbD1g",
    "msg_type": "markdown",
    "markdown": {"content": content},
}

p = subprocess.run(
    [NODE, WECOM, "message", "aibot", "send", "--json", json.dumps(payload, ensure_ascii=False)],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
)
print("RC=", p.returncode)
print("OUT=", (p.stdout or "")[:3000])
print("ERR=", (p.stderr or "")[:2000])
