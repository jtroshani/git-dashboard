#!/usr/bin/env python3
"""Collect GitHub traffic for all owned repos and merge it into a local history.

GitHub only keeps 14 days of traffic, so run this at least once a week (daily is
best) to build up monthly / yearly totals. Requires the `gh` CLI, logged in.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
HISTORY = os.path.join(DATA_DIR, "history.json")
DATA_JS = os.path.join(DATA_DIR, "data.js")
GH = os.environ.get("GH_BIN", "gh")


def gh(*args):
    out = subprocess.run([GH, *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout)


def load_history():
    if os.path.exists(HISTORY):
        with open(HISTORY) as f:
            return json.load(f)
    return {"repos": {}}


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    history = load_history()
    owner = gh("api", "user")["login"]
    repos = gh("repo", "list", owner, "--limit", "1000", "--source",
               "--json", "name,visibility,url,stargazerCount,description,homepageUrl")

    for r in repos:
        name = r["name"]
        full = f"{owner}/{name}"
        try:
            views = gh("api", f"repos/{full}/traffic/views")
            clones = gh("api", f"repos/{full}/traffic/clones")
            referrers = gh("api", f"repos/{full}/traffic/popular/referrers")
            paths = gh("api", f"repos/{full}/traffic/popular/paths")
        except RuntimeError as e:
            print(f"skip {full}: {e}", file=sys.stderr)
            continue

        try:
            site = gh("api", f"repos/{full}/pages")["html_url"]
        except RuntimeError:
            site = r["homepageUrl"] or ""

        entry = history["repos"].setdefault(name, {"days": {}})
        entry.update(url=r["url"], visibility=r["visibility"],
                     stars=r["stargazerCount"], description=r["description"] or "",
                     site=site)
        days = entry["days"]
        # Newer fetches overwrite older values for the same day (the most recent
        # day is partial until it closes).
        for v in views["views"]:
            d = days.setdefault(v["timestamp"][:10], {})
            d["views"], d["visitors"] = v["count"], v["uniques"]
        for c in clones["clones"]:
            d = days.setdefault(c["timestamp"][:10], {})
            d["clones"], d["cloners"] = c["count"], c["uniques"]
        entry["referrers"] = referrers
        entry["paths"] = paths
        print(f"ok   {full}")

    history["owner"] = owner
    history["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(HISTORY, "w") as f:
        json.dump(history, f, indent=1, sort_keys=True)
    # data.js lets dashboard.html load the data straight from disk (file://).
    with open(DATA_JS, "w") as f:
        f.write("window.TRAFFIC = " + json.dumps(history) + ";\n")


if __name__ == "__main__":
    main()
