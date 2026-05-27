<table border="0" cellpadding="0" cellspacing="0" style="border:none;border-collapse:collapse;">
  <tr>
    <td width="190" valign="middle" style="border:none;">
      <img src="pics/Bootblack_logo_v1.png" alt="Bootblack Logo" width="190"/>
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
- **Automated pipeline** — Fetches stock prices daily after each market close, runs return analysis and ranking, and publishes the result to GitHub Pages automatically
- **Bootblack Briefing** — Automatically generates a daily market summary analysing sentiment and flagging notable movers, powered by the Claude API
- **Obsidian integration** — The generated HTML is injected into `.md` file via `<iframe>` and rendered by Obsidian's Custom Frames plugin, enabling seamless interaction between the live dashboard and your notes
- **Interactive dashboard** — Normalised line charts, switchable time ranges, and a 7-day ranking bar chart. Click any label to open a stock detail panel with one-click links to [Tonghuashun](https://www.10jqka.com.cn/) and [Xueqiu](https://xueqiu.com/).
- **Flexible setting** — Define stocks and groups freely in `stocks.yaml`; groups that exceed the stock limit are split into sub-groups automatically

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

---

## Changelog

- **2026-05-23** — Initial build: multi-market data fetching, chart rendering, and Obsidian injection pipeline
- **2026-05-24** — Designed the Bootblack logo
- **2026-05-25** — Adaptive chart scaling and automatic collision-free label alignment
- **2026-05-26** — Bilingual daily briefing powered by the Claude API
- **2026-05-27** — Fixed guide line alignment between charts and labels; fixed data range clipping across mixed-market groups
