<table border="0" cellpadding="0" cellspacing="0" style="border:none;border-collapse:collapse;">
  <tr>
    <td width="190" valign="middle" style="border:none;">
      <img src="pics/Bootblack_logo_v0.png" alt="Bootblack Logo" width="190"/>
    </td>
    <td valign="middle" style="padding-left: 24px;border:none;">
      <h1>Bootblack</h1>
      <p>Bootblack knows the market before you do.<br/>
      A daily script that scrapes stock prices, renders interactive charts, and slips them into your Obsidian vault — quiet, punctual, and always on the corner.</p>
    </td>
  </tr>
</table>

---

## Features

- **Interactive charts** — Normalised line charts (all from 0% baseline), switchable time ranges, and a 7-day ranking bar chart. Click any label to open a stock detail panel with one-click links to Tonghuashun and Xueqiu.
- **Flexible grouping** — Define groups freely in `stocks.yaml`; groups that exceed the stock limit are split into sub-groups automatically
- **Obsidian injection** — Generates an HTML file and writes it into a target `.md` file as an `<iframe>`; uses comment markers for precise replacement without touching surrounding content
- **Auto-publish & scheduling** — Windows Task Scheduler triggers runs at 15:35 (A-shares close) and 05:05 (US close) on weekdays; results are pushed to GitHub Pages automatically after each run
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
