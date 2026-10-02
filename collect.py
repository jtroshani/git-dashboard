#!/usr/bin/env python3
"""Collect visits to each of my GitHub Pages sites and merge them into a history.

Visits are counted on the sites by GoatCounter; the `gh` CLI (logged in) lists
the sites. Needs GOATCOUNTER_TOKEN; run it regularly to build up the history.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
HISTORY = os.path.join(DATA_DIR, "history.json")
DATA_JS = os.path.join(DATA_DIR, "data.js")
GH = os.environ.get("GH_BIN", "gh")
SELF = "git-dashboard"  # this dashboard; not one of the tracked sites


def gh(*args):
    out = subprocess.run([GH, *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout)


def goatcounter(path, **params):
    site = os.environ.get("GOATCOUNTER_SITE", "jtroshani")
    url = f"https://{site}.goatcounter.com/api/v0/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + os.environ["GOATCOUNTER_TOKEN"],
        "Content-Type": "application/json"})
    # GoatCounter occasionally answers a valid request with 404 or 5xx; those
    # clear up on a retry.
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            err = f"GoatCounter {path}: HTTP {e.code}: {e.read().decode()[:500]}"
            if e.code not in (404, 429) and e.code < 500:
                break
        except urllib.error.URLError as e:
            err = f"GoatCounter {path}: {e.reason}"
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(err)


def collect_site_visits(history):
    """Merge the last 14 days of GoatCounter visits into each repo's days.

    Every site lives at <owner>.github.io/<repo>/..., so the first path segment
    names the repo.
    """
    if not os.environ.get("GOATCOUNTER_TOKEN"):
        print("GOATCOUNTER_TOKEN not set; skipping site visits", file=sys.stderr)
        return
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=13)).isoformat()
    try:
        totals = fetch_visits(history, start, today)
    except RuntimeError as e:
        # Keep the existing numbers; the next run re-reads the last 14 days.
        print(f"::warning::{e}; keeping previous site visits")
        return
    for repo, entry in history["repos"].items():
        for i in range(14):
            day = (today - timedelta(days=i)).isoformat()
            if day >= history.setdefault("visits_since", today.isoformat()):
                entry["days"].setdefault(day, {})["site_visits"] = totals.get((repo, day), 0)
    print(f"ok   site visits for {len({r for r, _ in totals})} sites")


def fetch_visits(history, start, today):
    """Return {(repo, day): visits} for start..today, paging through all paths."""
    totals, seen = {}, []
    while True:
        params = dict(start=start, end=today.isoformat(), limit=100)
        if seen:
            params["exclude_paths"] = ",".join(map(str, seen))
        page = goatcounter("stats/hits", **params)
        for hit in page.get("hits", []):
            seen.append(hit["path_id"])
            repo = hit["path"].strip("/").split("/")[0]
            if hit.get("event") or repo not in history["repos"]:
                continue
            for st in hit.get("stats", []):
                n = st.get("daily", sum(st.get("hourly") or []))
                key = (repo, st["day"])
                totals[key] = totals.get(key, 0) + n
        if not page.get("more"):
            return totals


def load_history():
    if os.path.exists(HISTORY):
        with open(HISTORY) as f:
            return json.load(f)
    return {"repos": {}}


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    history = load_history()
    # Short hand-written summaries shown next to each repo on the dashboard
    # (repos not listed fall back to their GitHub description), plus an
    # optional "page" for sites whose entry point isn't index.html.
    about_file = os.path.join(ROOT, "descriptions.json")
    about = json.load(open(about_file)) if os.path.exists(about_file) else {}
    owner = gh("api", "user")["login"]
    repos = gh("repo", "list", owner, "--limit", "1000", "--source",
               "--json", "name,url,description")

    sites = {}
    for r in repos:
        name = r["name"]
        if name == SELF:
            continue
        try:
            site = gh("api", f"repos/{owner}/{name}/pages")["html_url"]
        except RuntimeError:
            continue  # no GitHub Pages site
        # Sites without an index.html need their page named explicitly.
        if about.get(name, {}).get("page"):
            site = site.rstrip("/") + "/" + about[name]["page"]
        entry = history["repos"].get(name, {"days": {}})
        entry.update(url=r["url"], description=r["description"] or "",
                     site=site, about=about.get(name, {}).get("about", ""))
        sites[name] = entry
        print(f"ok   {name}")
    history["repos"] = sites

    collect_site_visits(history)
    history["owner"] = owner
    history["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(HISTORY, "w") as f:
        json.dump(history, f, indent=1, sort_keys=True)
    # data.js lets dashboard.html load the data straight from disk (file://).
    with open(DATA_JS, "w") as f:
        f.write("window.TRAFFIC = " + json.dumps(history) + ";\n")


if __name__ == "__main__":
    main()
