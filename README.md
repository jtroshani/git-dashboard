# Git Dashboard

Daily, weekly, monthly and yearly visits to each of my GitHub Pages sites, counted with GoatCounter.

**Live dashboard:** https://jtroshani.github.io/git-dashboard/

GitHub keeps only 14 days of traffic, so a GitHub Action (`.github/workflows/collect.yml`) runs `collect.py` every 3 hours and commits the results to `data/history.json`, which builds up monthly and yearly totals over time.

To run it locally: `python3 collect.py` (needs the `gh` CLI, logged in), then open `index.html`.
