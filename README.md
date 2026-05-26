<img src="pics/Bootblack_logo_v0.png" alt="Bootblack Logo" width="160" align="left"/>

# Bootblack 🥾

Bootblack knows the market before you do. A daily script that scrapes stock prices, renders interactive charts, and slips them into your Obsidian vault — quiet, punctual, and always on the corner.

<br clear="left"/>

---

## Features

- **Multi-market data fetching** — Tracks A-shares, HK stocks, and US stocks simultaneously, triggered automatically after each market close
- **Normalised line charts** — All stocks in a group start from the same baseline (0%) for fair comparison; toggle between daily / weekly view and 2-week / 2-month / full time ranges
- **Flexible grouping** — Define groups freely in `stocks.yaml`; groups that exceed the stock limit are split into sub-groups automatically
- **7-day performance ranking** — Symmetric dual-column bar chart (losses left, gains right), supports 7-day and intraday modes; click a bar to jump to the stock's quote page
- **Stock detail panel** — Click any end-of-line label to see ticker, market, today's change, and a short description; one-click links to Tonghuashun and Xueqiu
- **Collision-free labels** — End labels are automatically staggered with guide lines so they never overlap the chart
- **Obsidian injection** — Generates an HTML file and writes it into a target `.md` file as an `<iframe>`; uses comment markers for precise replacement without touching surrounding content
- **Auto-publish** — Pushes `output/bootblack.html` to GitHub after every run; GitHub Pages serves it as a live public URL
- **Scheduled runs** — Windows Task Scheduler triggers the script at 15:35 (A-shares close) and 05:05 (US close) on every weekday
- **Bootblack Briefing** — Calls the Claude API after each run to generate a terse, slightly sardonic daily market summary in both Chinese and English; cached locally so the API is only called once per day

---

## Stack

| Layer | Tool |
|-------|------|
| A-share data | [baostock](http://baostock.com) — TCP-based protocol, no rate limiting |
| HK / US data | [yfinance](https://github.com/ranaroussi/yfinance) — Yahoo Finance |
| Config | [PyYAML](https://pyyaml.org/) — `stocks.yaml` + `config.yaml` |
| Visualisation | [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) — Apache 2.0, loaded via CDN |
| Obsidian injection | Plain `<iframe>` + comment markers (`<!-- BOOTBLACK_START / END -->`), managed by `writer.py` |
| Briefing | [Anthropic Claude API](https://www.anthropic.com) — `claude-sonnet-4-5` |
| Auto-push | `subprocess` calling git; commit message includes timestamp |

---

## Project Structure

```
Bootblack/
├── pics/
│   └── Bootblack_logo.png
├── stocks.yaml        # Stock list and groups — edit this to add or change stocks
├── config.yaml        # Paths, timezone, push toggle, and other settings
├── requirements.txt
├── src/
│   ├── main.py        # Entry point — orchestrates all modules
│   ├── fetcher.py     # Data fetching and local cache
│   ├── renderer.py    # Generates output/bootblack.html
│   ├── briefing.py    # Calls Claude API to generate the daily briefing
│   ├── writer.py      # Injects HTML into Obsidian md file
│   └── exporter.py    # Generates output/stocks.md for human reference
├── scripts/
│   ├── schedule.bat   # Wrapper script for Task Scheduler
│   └── setup_task.bat # Registers the two scheduled tasks on Windows
└── output/            # Auto-generated; only bootblack.html is committed
    ├── bootblack.html # Published to GitHub Pages
    ├── briefing.json  # Cached daily briefing (CN + EN)
    ├── stocks.md      # Human-readable stock list (read-only, auto-generated)
    └── cache.json     # Local price data cache
```

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Anthropic API key (required for the daily briefing)
set ANTHROPIC_API_KEY=your_key_here   # Windows
export ANTHROPIC_API_KEY=your_key_here  # macOS / Linux

# Configure
# Edit stocks.yaml  — add your stocks and groups
# Edit config.yaml  — set the absolute path to your Obsidian md file

# Run
python src/main.py          # Full pipeline: fetch → briefing → render → inject → push
python src/main.py --test   # Fake data, skips all API calls (for debugging)

# Register scheduled tasks (Windows)
scripts\setup_task.bat
```

---

## Notes on Data Sources

`akshare` relies on the Eastmoney API, which applies TLS renegotiation throttling under batch requests. Bootblack uses `baostock` for A-shares (TCP protocol, unaffected) and `yfinance` for HK stocks instead.

---

*Named after the bootblacks of the 19th century — street-corner shoe shiners who handled enough clients each day to know the market's mood before anyone else did.*
