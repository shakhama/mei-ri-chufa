import json, sys, urllib.request
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = "shakhama/mei-ri-chufa"
HDR = {"User-Agent": "wb-daily-check", "Accept": "application/vnd.github+json"}


def get(url):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# 1. 远端真实 HEAD
try:
    ref = get(f"https://api.github.com/repos/{REPO}/git/refs/heads/main")
    remote_sha = ref["object"]["sha"][:8]
    print(f"REMOTE_HEAD={remote_sha}")
except Exception as e:
    print(f"REMOTE_HEAD=ERR:{e}")

# 2. Actions runs
try:
    data = get(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=10")
    tz = timezone(timedelta(hours=8))
    print("=== ACTIONS RUNS (top 10, Beijing time) ===")
    for run in data.get("workflow_runs", []):
        ts = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(tz)
        fin = run.get("updated_at")
        fin_s = ""
        if fin:
            fin_s = datetime.fromisoformat(fin.replace("Z", "+00:00")).astimezone(tz).strftime("%m-%d %H:%M:%S")
        print(f"  {ts.strftime('%m-%d %H:%M')} | {run['name']:<28} | {run['status']:<10} | {run.get('conclusion')} | head={run['head_sha'][:8]} | fin={fin_s}")
except Exception as e:
    print(f"ACTIONS_ERR={e}")
