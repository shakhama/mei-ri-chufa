import json, os, subprocess, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def get_pat():
    p = subprocess.run(
        ["git", "-c", "credential.helper=", "-c", "credential.helper=manager", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    for line in (p.stdout or "").splitlines():
        if line.lower().startswith("password="):
            return line.split("=", 1)[1].strip()
    return None

pat = get_pat()
if not pat:
    print("NO_PAT"); sys.exit(1)

req = urllib.request.Request(
    "https://api.github.com/repos/shakhama/mei-ri-chufa/actions/runs?per_page=10",
    headers={"Authorization": "Bearer " + pat, "Accept": "application/vnd.github+json",
             "User-Agent": "wb-daily"},
)
with urllib.request.urlopen(req, timeout=60) as r:
    data = json.load(r)

rows = []
for run in data.get("workflow_runs", []):
    rows.append({
        "id": run.get("id"),
        "name": run.get("name"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created": run.get("created_at"),
        "updated": run.get("updated_at"),
        "event": run.get("event"),
        "head_sha": (run.get("head_sha") or "")[:7],
    })
out = {"total": data.get("total_count"), "runs": rows}
with open(r"C:/Users/Administrator/.workbuddy/tmp/runs_parsed.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("OK total=%s wrote=%d" % (out["total"], len(rows)))
for r in rows:
    print("%s | %s | %s/%s | created=%s upd=%s | %s" % (
        r["id"], r["name"], r["status"], r["conclusion"], r["created"], r["updated"], r["event"]))
