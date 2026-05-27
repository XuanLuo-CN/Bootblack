# Copyright (c) 2026 Xuan Luo
# SPDX-License-Identifier: MIT
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
STOCKS_PATH = ROOT / "stocks.yaml"
CONFIG_PATH = ROOT / "config.yaml"
OUTPUT_PATH = ROOT / "output" / "bootblack.html"

COLORS = [
    "#4C9BE8", "#3DBCB8", "#E8A838", "#5BAD7F", "#D4667A", "#8B7EC8",
    "#2E7DD1", "#2A9D99", "#C78D20", "#3D9162", "#B84D5F", "#6B5FB0",
    "#1A5FAD",
]


def _load_meta() -> dict:
    """Return {code: {name, market, desc}} from stocks.yaml."""
    with open(STOCKS_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out = {}
    for group in cfg["groups"]:
        for s in group["stocks"]:
            out[s["code"]] = {
                "name": s["name"],
                "market": s["market"],
                "desc": s.get("desc", ""),
            }
    return out


def _build_briefing_info(briefing: dict) -> str:
    parts = []
    if briefing.get("generated_date"):
        delta = (date.today() - date.fromisoformat(briefing["generated_date"])).days
        label = "today" if delta == 0 else f"{delta} day{'s' if delta > 1 else ''} ago"
        parts.append(f"Generated {label}")
    if briefing.get("days_remaining") is not None:
        parts.append(f"~{briefing['days_remaining']} days of credit remaining")
    return " · ".join(parts)


def _briefing_to_html(text: str) -> str:
    """Parse **Title** sections into newspaper-style HTML blocks."""
    if not text:
        return ""

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts = re.split(r"\*\*([^*\n]+)\*\*", text.strip())
    # parts: [pre-header-text, title1, body1, title2, body2, ...]
    sections: list[dict] = []
    if parts[0].strip():
        sections.append({"title": None, "text": parts[0].strip()})
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body  = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append({"title": title, "text": body})

    if not sections:
        return f'<p class="bf-text">{esc(text)}</p>'

    def render_section(s: dict, is_overview: bool) -> str:
        title_html = f'<div class="bf-stitle">{esc(s["title"])}</div>' if s["title"] else ""
        body_html  = esc(s["text"]).replace("\n\n", "</p><p class=\"bf-text\">").replace("\n", " ")
        css = "bf-overview" if is_overview else "bf-section"
        return f'<div class="{css}">{title_html}<p class="bf-text">{body_html}</p></div>'

    overview_html = render_section(sections[0], is_overview=True)
    group_html = "".join(render_section(s, is_overview=False) for s in sections[1:])
    grid = f'<div class="bf-grid">{group_html}</div>' if group_html else ""
    return overview_html + grid


def _agg_weekly(records: list) -> list:
    """Return last trading day of each ISO week (weekly close aggregation)."""
    by_week: dict = {}
    for r in records:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        by_week[dt.isocalendar()[:2]] = r
    return sorted(by_week.values(), key=lambda r: r["date"])


def render(groups: list, output_path: Path = OUTPUT_PATH, briefing: dict | None = None) -> None:
    """
    Render fetcher output to a self-contained HTML dashboard.

    groups:   list returned by fetcher.fetch_all()
    briefing: optional {"cn": "...", "en": "..."} from briefing.generate()
    """
    meta = _load_meta()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ranking_limit = int(cfg.get("ranking_limit", 10))
    charts_per_row = int(cfg.get("charts_per_row", 2))
    group_max_stocks = int(cfg.get("group_max_stocks", 8))
    max_width = int(cfg.get("max_width", 1000))

    # 7-day ranking (use up to 8 data points back to approximate ~7 trading days)
    rankings: list[dict] = []
    for group in groups:
        for s in group.get("stocks", []):
            d = s.get("data", [])
            if len(d) < 2:
                continue
            base = d[max(0, len(d) - 8)]["close"]
            last = d[-1]["close"]
            pct = (last - base) / base * 100 if base else 0.0
            rankings.append({
                "name": s["name"],
                "code": s["code"],
                "market": s["market"],
                "pct": round(pct, 2),
            })
    rankings.sort(key=lambda x: x["pct"])

    # Today's ranking: last day close vs open
    rankings_today: list[dict] = []
    for group in groups:
        for s in group.get("stocks", []):
            d = s.get("data", [])
            if not d:
                continue
            last = d[-1]
            open_p, close_p = last.get("open", 0), last.get("close", 0)
            pct = (close_p - open_p) / open_p * 100 if open_p else 0.0
            rankings_today.append({
                "name": s["name"],
                "code": s["code"],
                "market": s["market"],
                "pct": round(pct, 2),
            })
    rankings_today.sort(key=lambda x: x["pct"])

    # Build per-group series data for JS
    chart_groups: list[dict] = []
    for group in groups:
        series_list = []
        for s in group.get("stocks", []):
            d = s.get("data", [])
            if not d:
                continue
            sm = meta.get(s["code"], {})
            first_price = d[0]["close"] or 1
            weekly_d = _agg_weekly(d)
            daily = [{"time": r["date"], "value": round((r["close"] - first_price) / first_price * 100, 3)} for r in d]
            weekly = [{"time": r["date"], "value": round((r["close"] - first_price) / first_price * 100, 3)} for r in weekly_d]
            daily_raw = [{"time": r["date"], "value": r["close"]} for r in d]
            weekly_raw = [{"time": r["date"], "value": r["close"]} for r in weekly_d]
            series_list.append({
                "name": s["name"],
                "code": s["code"],
                "market": s["market"],
                "daily": daily,
                "weekly": weekly,
                "daily_raw": daily_raw,
                "weekly_raw": weekly_raw,
                "desc": sm.get("desc", ""),
                "_last_pct": daily[-1]["value"] if daily else 0,
            })

        if len(series_list) <= group_max_stocks:
            for i, s in enumerate(series_list):
                s["color"] = COLORS[i % len(COLORS)]
                s.pop("_last_pct")
            chart_groups.append({"name": group["name"], "series": series_list})
        else:
            # Sort by latest normalized pct desc, then split into sub-groups
            series_list.sort(key=lambda s: s["_last_pct"], reverse=True)
            n_parts = (len(series_list) + group_max_stocks - 1) // group_max_stocks
            for part_idx in range(n_parts):
                part = series_list[part_idx * group_max_stocks:(part_idx + 1) * group_max_stocks]
                for i, s in enumerate(part):
                    s["color"] = COLORS[i % len(COLORS)]
                    s.pop("_last_pct")
                sub_name = f"{group['name']} ({part_idx + 1}/{n_parts})"
                chart_groups.append({"name": sub_name, "series": part})

    # Build per-stock metadata for the click popup
    stock_meta: dict = {}
    for group in groups:
        for s in group.get("stocks", []):
            d = s.get("data", [])
            if not d:
                continue
            sm = meta.get(s["code"], {})
            last = d[-1]
            last_price = float(last.get("close") or 0)
            open_today = float(last.get("open") or last_price) or 1
            change_today = (last_price - open_today) / open_today * 100
            base_7d = float(d[max(0, len(d) - 8)].get("close") or last_price) or 1
            change_7d = (last_price - base_7d) / base_7d * 100
            stock_meta[s["code"]] = {
                "name": s["name"],
                "code": s["code"],
                "market": s["market"],
                "desc": sm.get("desc", ""),
                "last_price": round(last_price, 2),
                "change_today": round(change_today, 2),
                "change_7d": round(change_7d, 2),
            }

    # Pre-compute page height so writer.py can set iframe height without JS
    n_groups_with_data = sum(1 for g in chart_groups if g["series"])
    n_rank_rows = max(
        min(sum(1 for r in rankings if r["pct"] < 0), ranking_limit),
        min(sum(1 for r in rankings if r["pct"] > 0), ranking_limit),
    )
    n_chart_rows = (n_groups_with_data + charts_per_row - 1) // charts_per_row
    page_height = max(200 + n_chart_rows * 420 + 40 + n_rank_rows * 30 + 200, 1200)

    has_briefing = bool(briefing and (briefing.get("cn") or briefing.get("en")))
    briefing_cn_html = _briefing_to_html((briefing or {}).get("cn", ""))
    briefing_en_html = _briefing_to_html((briefing or {}).get("en", ""))
    briefing_hidden  = "" if has_briefing else ' style="display:none"'
    briefing_info    = _build_briefing_info(briefing) if has_briefing else ""
    if has_briefing:
        page_height += 180

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = _TEMPLATE
    html = html.replace("__GROUPS__", json.dumps(chart_groups, ensure_ascii=False))
    html = html.replace("__RANKINGS__", json.dumps(rankings, ensure_ascii=False))
    html = html.replace("__RANKINGS_TODAY__", json.dumps(rankings_today, ensure_ascii=False))
    html = html.replace("__UPDATED__", now)
    html = html.replace("__RANKING_LIMIT__", str(ranking_limit))
    html = html.replace("__COLS__", str(charts_per_row))
    html = html.replace("__MAX_WIDTH__", str(max_width))
    html = html.replace("__HEIGHT__", str(page_height))
    html = html.replace("__STOCK_META__", json.dumps(stock_meta, ensure_ascii=False))
    html = html.replace("__BRIEFING_CN_HTML__", briefing_cn_html)
    html = html.replace("__BRIEFING_EN_HTML__", briefing_en_html)
    html = html.replace("__BRIEFING_HIDDEN__", briefing_hidden)
    html = html.replace("__BRIEFING_INFO__", briefing_info)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"[OK] written → {output_path}")


# ---------------------------------------------------------------------------
# HTML template
# Placeholders: __GROUPS__  __RANKINGS__  __RANKINGS_TODAY__  __UPDATED__
#               __RANKING_LIMIT__  __COLS__  __HEIGHT__  __STOCK_META__
#               __BRIEFING_CN__  __BRIEFING_EN__  __BRIEFING_HIDDEN__
# ---------------------------------------------------------------------------
_TEMPLATE = r"""<!-- Copyright (c) 2026 Xuan Luo -- MIT License -->
<!DOCTYPE html>
<html lang="en" data-bb-height="__HEIGHT__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BOOTBLACK</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: transparent; color: #e0e0e0; font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; transition: none; max-width: __MAX_WIDTH__px; margin: 0 auto; }

#header { padding: 22px 32px 16px; border-bottom: 1px solid #2c2c2a; display: flex; align-items: baseline; gap: 18px; }
#header h1 { font-size: 17px; font-weight: 700; letter-spacing: 0.16em; color: #e0e0e0; }
#header .ts { font-size: 11px; color: #555; }

#toggle-bar { padding: 12px 32px; display: flex; gap: 6px; }
.tbtn { background: transparent; border: 1px solid #2e2e2c; color: #555; padding: 3px 14px; border-radius: 3px; cursor: pointer; font-size: 12px; transition: all .15s; }
.tbtn.active { border-color: #4a4a48; color: #ccc; background: #262624; }
.tbtn:hover:not(.active) { border-color: #3a3a38; color: #888; }

#charts { display: grid; grid-template-columns: repeat(__COLS__, 1fr); }
.group-sec { padding: 20px 24px 8px; }
.group-title { font-size: 10px; font-weight: 600; color: #444; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 10px; }
.chart-wrap { position: relative; height: 320px; overflow: visible; }
/* Weaken TradingView attribution logo */
.tv-lightweight-charts a[href*="tradingview"] {
  opacity: 0.12 !important;
  transform: scale(0.55) !important;
  transform-origin: bottom right !important;
}
.chart-el { width: calc(100% - 90px); height: 100%; }

.label-layer { position: absolute; inset: 0; pointer-events: none; overflow: visible; z-index: 6; }
.slabel {
  position: absolute;
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 2px;
  white-space: nowrap;
  pointer-events: auto;
  cursor: pointer;
  background: rgba(20,20,18,0.82);
}
.slabel:hover { opacity: 0.8; }

.c-tooltip {
  position: absolute; background: rgba(30,30,28,0.92); border: 1px solid #2e2e2c;
  border-radius: 4px; padding: 8px 11px; font-size: 11px;
  pointer-events: none; z-index: 50; display: none;
  white-space: nowrap; line-height: 1.9;
}

#spopup {
  position: fixed; background: #2a2a28; border: 1px solid #3a3a38;
  border-radius: 8px; padding: 14px; min-width: 200px; max-width: 300px;
  z-index: 9999; display: none; box-shadow: 0 8px 24px rgba(0,0,0,.6);
  font-size: 12px; color: #e0e0e0;
}
.sp-hr { border-top: 1px solid #3a3a38; margin: 10px 0; }
.sp-row { display: flex; justify-content: space-between; margin-bottom: 6px; }
.sp-row span:first-child { color: #888; font-size: 11px; }
.sp-row span:last-child { font-size: 11px; font-weight: 500; }
.sp-name { font-weight: 600; font-size: 13px; }
.sp-btn { background: #333331; border: 1px solid #3a3a38; color: #aaa; padding: 5px 0; border-radius: 3px; cursor: pointer; font-size: 11px; flex: 1; }
.sp-btn:hover { background: #3a3a38; color: #ccc; }

/* ── Ranking dual-column layout ── */
#ranking { padding: 32px 32px 56px; }
#ranking h2 { font-size: 10px; font-weight: 600; color: #444; letter-spacing: 0.12em; text-transform: uppercase; }
.rank-dual { display: flex; gap: 10px; }
.rank-loss-col, .rank-gain-col { flex: 1; min-width: 0; }

.rank-row-loss, .rank-row-gain {
  display: flex; align-items: center; height: 24px; margin-bottom: 3px;
  cursor: pointer; border-radius: 3px; padding: 0 3px;
  transition: background .1s;
}
.rank-row-loss:hover, .rank-row-gain:hover { background: rgba(255,255,255,0.04); }
.rank-row-empty { height: 24px; margin-bottom: 3px; }

/* Loss column: [bar-area flex:1] [pct fixed] [name fixed] — bar anchors right, grows left */
.rank-row-loss .rl-bar-area { flex: 1; position: relative; height: 14px; overflow: hidden; min-width: 0; }
.rl-bar { position: absolute; right: 0; top: 0; height: 100%; background: #D4667A; border-radius: 3px 0 0 3px; }
.rl-pct { flex-shrink: 0; width: 46px; font-size: 10.5px; color: #D4667A; text-align: right; padding-right: 5px; }
.rl-name { flex-shrink: 0; width: 64px; font-size: 11.5px; color: #999; text-align: left; padding-left: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Gain column: [name fixed] [pct fixed] [bar-area flex:1] — bar anchors left, grows right */
.rg-name { flex-shrink: 0; width: 64px; font-size: 11.5px; color: #999; text-align: right; padding-right: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rg-pct { flex-shrink: 0; width: 46px; font-size: 10.5px; color: #5BAD7F; text-align: left; padding-left: 5px; }
.rank-row-gain .rg-bar-area { flex: 1; position: relative; height: 14px; overflow: hidden; min-width: 0; }
.rg-bar { position: absolute; left: 0; top: 0; height: 100%; background: #5BAD7F; border-radius: 0 3px 3px 0; }

/* ── Daily briefing (newspaper style) ── */
#briefing { padding: 28px 32px 36px; border-bottom: 1px solid #1e1e1c; }
.bf-masthead { display: flex; align-items: baseline; justify-content: space-between; padding-bottom: 10px; border-bottom: 3px double #2e2e2c; margin-bottom: 20px; }
.bf-masthead-left { font-size: 10px; font-weight: 700; letter-spacing: 0.3em; text-transform: uppercase; color: #555; }
.bf-masthead-right { display: flex; align-items: center; gap: 18px; }
.bf-meta { font-size: 10px; color: #3a3a38; letter-spacing: 0.05em; }
.bl-btn { background: none; border: none; font-size: 11px; cursor: pointer; padding: 0; transition: color 0.15s; }
.bf-content { transition: opacity 0.15s; }
.bf-overview { margin-bottom: 18px; padding-bottom: 16px; border-bottom: 1px solid #1e1e1c; }
.bf-overview .bf-text { font-size: 13px; color: #c8c8c8; line-height: 1.85; font-style: italic; }
.bf-stitle { font-size: 8.5px; font-weight: 700; letter-spacing: 0.24em; text-transform: uppercase; color: #4a4a48; margin-bottom: 8px; padding-bottom: 5px; border-bottom: 1px solid #1e1e1c; }
.bf-section .bf-text { font-size: 11.5px; color: #888; line-height: 1.75; }
.bf-text { margin: 0; }
.bf-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px 28px; margin-top: 4px; }
</style>
</head>
<body>
<script>
  if (window.self !== window.top) {
    document.body.style.background = 'transparent';
  } else {
    document.body.style.background = '#27282e';
  }
</script>

<div id="header">
  <h1>BOOTBLACK</h1>
  <div style="margin-left:auto;display:flex;align-items:baseline;gap:10px;">
    <span class="ts">__UPDATED__</span>
    <button class="tbtn" onclick="buildCharts();buildRanking()">Refresh</button>
  </div>
</div>

<div id="briefing"__BRIEFING_HIDDEN__>
  <div class="bf-masthead">
    <span class="bf-masthead-left">Daily Briefing</span>
    <div class="bf-masthead-right">
      <span class="bf-meta">__BRIEFING_INFO__</span>
      <div style="display:flex;gap:10px;">
        <button class="bl-btn" id="bl-cn" onclick="setBriefingLang('cn')">中文</button>
        <button class="bl-btn" id="bl-en" onclick="setBriefingLang('en')">EN</button>
      </div>
    </div>
  </div>
  <div id="bf-cn" class="bf-content">__BRIEFING_CN_HTML__</div>
  <div id="bf-en" class="bf-content" style="display:none">__BRIEFING_EN_HTML__</div>
</div>

<div id="toggle-bar">
  <button class="tbtn active" id="btn-d" onclick="setMode('daily')">Daily</button>
  <button class="tbtn" id="btn-w" onclick="setMode('weekly')">Weekly</button>
  <div style="margin-left:auto;display:flex;gap:6px;">
    <button class="tbtn" id="btn-2w" onclick="setRangeFilter('2w')">2W</button>
    <button class="tbtn" id="btn-2m" onclick="setRangeFilter('2m')">2M</button>
  </div>
</div>

<div id="charts"></div>
<div id="ranking">
  <div style="display:flex;align-items:center;margin-bottom:18px;">
    <h2 id="ranking-title">7-Day Performance</h2>
    <div style="margin-left:auto;display:flex;gap:6px;">
      <button class="tbtn active" id="btn-r1" onclick="setRankingMode('today')">1D</button>
      <button class="tbtn" id="btn-r7" onclick="setRankingMode('7d')">7D</button>
    </div>
  </div>
  <div id="rbars"></div>
</div>

<div id="spopup">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <div><span class="sp-name"></span><span class="sp-code" style="color:#888;font-size:11px;margin-left:6px;"></span></div>
    <span class="sp-market" style="font-size:10px;padding:2px 7px;border-radius:3px;color:#fff;font-weight:500;margin-left:8px;flex-shrink:0;"></span>
  </div>
  <div class="sp-hr"></div>
  <div class="sp-row"><span>Today</span><span class="sp-today"></span></div>
  <div class="sp-row"><span>Price</span><span class="sp-price" style="color:#ccc;"></span></div>
  <div class="sp-row" style="margin-bottom:0;"><span>7D</span><span class="sp-7d"></span></div>
  <div class="sp-desc-block">
    <div class="sp-hr"></div>
    <div style="font-size:10px;color:#555;letter-spacing:0.08em;margin-bottom:5px;">Notes</div>
    <div class="sp-desc" style="font-size:11px;color:#b0b0b0;line-height:1.6;"></div>
  </div>
  <div class="sp-hr"></div>
  <div style="display:flex;gap:6px;">
    <button class="sp-btn sp-ths">同花顺</button>
    <button class="sp-btn sp-xq">雪球</button>
  </div>
</div>

<script>
const GROUPS = __GROUPS__;
const RANKINGS = __RANKINGS__;
const RANKINGS_TODAY = __RANKINGS_TODAY__;
const RANKING_LIMIT = __RANKING_LIMIT__;
const STOCK_META = __STOCK_META__;
const MKTLABEL = { a: 'A', hk: 'HK', us: 'US' };
let mode = 'daily';
let rangeFilter = null;   // null | '2w' | '2m'
let rankingMode = 'today';   // '7d' | 'today'
const chartStates = [];

// ── Time-range helpers ──────────────────────────────────────────────────────

function getCutoffDate(filter) {
  const days = filter === '2w' ? 14 : 60;
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function getDisplayData(rawArr, filter) {
  const data = filter ? rawArr.filter(r => r.time >= getCutoffDate(filter)) : rawArr;
  if (!data.length) return [];
  const base = data[0].value || 1;
  return data.map(r => ({ time: r.time, value: +((r.value - base) / base * 100).toFixed(3) }));
}

function refreshChartData(state) {
  const rawKey = mode + '_raw';
  let maxLen = 1;
  const allDates = new Set();
  state.seriesArr.forEach(({ ser, meta }) => {
    const disp = getDisplayData(meta[rawKey], rangeFilter);
    ser.setData(disp);
    meta._disp = disp;
    maxLen = Math.max(maxLen, disp.length);
    disp.forEach(r => allDates.add(r.time));
  });
  state.maxDataLen = maxLen;
  // Use union of all series dates — mixed markets have different trading calendars,
  // so the combined time axis can have more slots than any single series.
  state.actualMaxIdx = Math.max(allDates.size - 1, 0);
  const maxIdx = state.actualMaxIdx;
  state.chart.timeScale().fitContent();
  requestAnimationFrame(() => {
    const range = state.chart.timeScale().getVisibleLogicalRange();
    if (range && range.to > maxIdx) {
      const span = range.to - range.from;
      state.chart.timeScale().setVisibleLogicalRange({ from: maxIdx - span, to: maxIdx });
    }
    requestAnimationFrame(() => placeLabels(state));
  });
}

function initBriefing() {
  const cnBtn = document.getElementById('bl-cn');
  if (!cnBtn) return;
  cnBtn.style.color = '#e0e0e0';
  document.getElementById('bl-en').style.color = '#555';
}

let _briefingLang = 'cn';
function setBriefingLang(lang) {
  if (lang === _briefingLang) return;
  const from = document.getElementById('bf-' + _briefingLang);
  const to   = document.getElementById('bf-' + lang);
  _briefingLang = lang;
  from.style.opacity = '0';
  setTimeout(function() {
    from.style.display = 'none';
    from.style.opacity = '1';
    to.style.display   = '';
    to.style.opacity   = '0';
    requestAnimationFrame(function() {
      requestAnimationFrame(function() { to.style.opacity = '1'; });
    });
  }, 150);
  document.getElementById('bl-cn').style.color = lang === 'cn' ? '#e0e0e0' : '#555';
  document.getElementById('bl-en').style.color = lang === 'en' ? '#e0e0e0' : '#555';
}

function init() {
  buildCharts();
  buildRanking();
  initBriefing();
}

// ── Chart building ──────────────────────────────────────────────────────────

function buildCharts() {
  const root = document.getElementById('charts');
  root.innerHTML = '';
  chartStates.length = 0;

  GROUPS.forEach(group => {
    const sec = document.createElement('div');
    sec.className = 'group-sec';

    const gtitle = document.createElement('div');
    gtitle.className = 'group-title';
    gtitle.textContent = group.name;
    sec.appendChild(gtitle);

    const wrap = document.createElement('div');
    wrap.className = 'chart-wrap';

    const chartEl = document.createElement('div');
    chartEl.className = 'chart-el';
    wrap.appendChild(chartEl);

    const labelLayer = document.createElement('div');
    labelLayer.className = 'label-layer';
    wrap.appendChild(labelLayer);

    const overlayCanvas = document.createElement('canvas');
    overlayCanvas.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:5;';
    wrap.appendChild(overlayCanvas);

    const cTooltip = document.createElement('div');
    cTooltip.className = 'c-tooltip';
    wrap.appendChild(cTooltip);

    sec.appendChild(wrap);
    root.appendChild(sec);

    const state = { maxDataLen: 0, actualMaxIdx: undefined };

    const chart = LightweightCharts.createChart(chartEl, {
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#4a4a48' },
      localization: { priceFormatter: p => (p >= 0 ? '+' : '') + p.toFixed(1) + '%' },
      grid: { vertLines: { color: '#242422' }, horzLines: { color: '#242422' } },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: '#3a3a38', width: 1, style: 3 },
        horzLine: { color: '#3a3a38', width: 1, style: 3 },
      },
      rightPriceScale: { visible: false },
      leftPriceScale: { visible: true, borderVisible: false },
      timeScale: {
        borderColor: '#2c2c2a',
        timeVisible: true,
        rightOffset: 0,
        tickMarkFormatter: (time, tickMarkType) => {
          let month, day;
          if (typeof time === 'object') {
            month = time.month; day = time.day;
          } else if (typeof time === 'string') {
            const p = time.split('-');
            month = parseInt(p[1], 10); day = parseInt(p[2], 10);
          } else {
            const d = new Date(time * 1000);
            month = d.getUTCMonth() + 1; day = d.getUTCDate();
          }
          if (tickMarkType <= 1) return 'M' + month;
          return month + '/' + day;
        },
      },
      height: 320,
    });

    const seriesArr = group.series.map(s => {
      const ser = chart.addAreaSeries({
        lineColor: s.color,
        topColor: s.color + '26',
        bottomColor: s.color + '04',
        lineWidth: 1.5,
        priceScaleId: 'left',
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 3,
        crosshairMarkerBorderColor: s.color,
        crosshairMarkerBackgroundColor: 'rgba(0,0,0,0.5)',
      });
      return { ser, meta: s };
    });

    // y=0 baseline
    if (seriesArr.length > 0) {
      seriesArr[0].ser.createPriceLine({
        price: 0, color: '#888', lineWidth: 1.5, lineStyle: 0, axisLabelVisible: false,
      });
    }

    // Clamp visible range to current data bounds (respects rangeFilter)
    chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (!range) return;
      const maxIdx = state.actualMaxIdx !== undefined ? state.actualMaxIdx : Math.max(state.maxDataLen, 1) - 1;
      const clampedFrom = Math.max(0, range.from);
      const clampedTo   = Math.min(maxIdx, range.to);
      if (clampedFrom !== range.from || clampedTo !== range.to) {
        requestAnimationFrame(() => {
          chart.timeScale().setVisibleLogicalRange({ from: clampedFrom, to: clampedTo });
        });
      }
      clearTimeout(state._labelTimer);
      state._labelTimer = setTimeout(() => requestAnimationFrame(() => placeLabels(state)), 16);
    });

    chart.subscribeCrosshairMove(param => {
      if (!param.point || !param.time) { cTooltip.style.display = 'none'; return; }
      const rawKey = mode + '_raw';
      const items = [];
      seriesArr.forEach(({ ser, meta }) => {
        const dp = param.seriesData.get(ser);
        if (dp !== undefined && dp.value !== undefined) {
          const rawEntry = meta[rawKey].find(r => r.time === param.time);
          items.push({
            pct: dp.value,
            name: meta.name,
            rawPrice: rawEntry ? rawEntry.value.toFixed(2) : '—',
            dotColor: meta.color,
          });
        }
      });
      if (!items.length) { cTooltip.style.display = 'none'; return; }
      items.sort((a, b) => b.pct - a.pct);
      const lines = items.map(item => {
        const lineColor = item.pct >= 0 ? '#5BAD7F' : '#D4667A';
        const pctStr = (item.pct >= 0 ? '+' : '') + item.pct.toFixed(2) + '%';
        return '<span style="color:' + item.dotColor + '">●</span>' +
          ' <span style="color:' + lineColor + '">' + item.name +
          '  ' + item.rawPrice + '  ' + pctStr + '</span>';
      });
      const timeLabel = typeof param.time === 'object'
        ? param.time.year + '-' + String(param.time.month).padStart(2,'0') + '-' + String(param.time.day).padStart(2,'0')
        : param.time;
      cTooltip.innerHTML =
        '<span style="color:#444;font-size:10px">' + timeLabel + '</span><br>' +
        lines.join('<br>');
      cTooltip.style.display = 'block';
      const x = param.point.x, y = param.point.y;
      cTooltip.style.left = (x + 14) + 'px';
      cTooltip.style.top = Math.max(4, y - 16) + 'px';
    });

    state.chart = chart;
    state.seriesArr = seriesArr;
    state.labelLayer = labelLayer;
    state.overlayCanvas = overlayCanvas;
    state.cTooltip = cTooltip;
    state.chartEl = chartEl;
    chartStates.push(state);
    refreshChartData(state);
  });
}

// ── End-of-series labels ────────────────────────────────────────────────────

function placeLabels(state) {
  const { seriesArr, labelLayer, overlayCanvas, chartEl, chart } = state;

  labelLayer.innerHTML = '';

  // Size canvas from the wrapping container (chart-el + 90px label zone)
  const wrap = overlayCanvas.parentElement;
  const OW = wrap ? wrap.clientWidth : 0;
  const OH = wrap ? wrap.clientHeight : 0;
  if (!OW || !OH) return;
  const dpr = window.devicePixelRatio || 1;
  overlayCanvas.width = Math.round(OW * dpr);
  overlayCanvas.height = Math.round(OH * dpr);
  overlayCanvas.style.width = OW + 'px';
  overlayCanvas.style.height = OH + 'px';
  const ctx = overlayCanvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, OW, OH);

  const chartW = chartEl.clientWidth;   // right boundary of TradingView canvas
  const H = chartEl.clientHeight;
  if (!chartW || !H) return;
  // timeToCoordinate uses time-axis space (origin = right after left price scale)
  // add price scale width to convert to canvas space
  const priceScaleW = chart.priceScale('left').width();

  const positions = [];

  seriesArr.forEach(({ ser, meta }) => {
    const data = meta._disp || meta[mode];
    if (!data || !data.length) return;
    // Find the rightmost data point currently visible on screen
    let pt = null, connX = chartW;
    for (let i = data.length - 1; i >= 0; i--) {
      const rawX = chart.timeScale().timeToCoordinate(data[i].time);
      if (rawX !== null && rawX >= 0 && priceScaleW + rawX <= chartW + 0.5) {
        pt = data[i];
        connX = Math.min(priceScaleW + rawX, chartW);
        break;
      }
    }
    if (!pt) return;
    const y = ser.priceToCoordinate(pt.value);
    if (y === null) return;
    positions.push({ actualY: y, y, pct: pt.value, code: meta.code, color: meta.color, name: meta.name, desc: meta.desc, market: meta.market, connX });
  });

  // Sort by P&L descending: highest gainer at top (smallest y on screen)
  positions.sort((a, b) => b.pct - a.pct);

  const GAP = 18;
  for (let i = 1; i < positions.length; i++) {
    if (positions[i].y - positions[i - 1].y < GAP) {
      positions[i].y = positions[i - 1].y + GAP;
    }
  }

  if (positions.length > 0) {
    const overflow = positions[positions.length - 1].y - (H - 8);
    if (overflow > 0) positions.forEach(p => p.y -= overflow);
  }

  positions.forEach(p => {
    // Connector in the label zone: from chart right edge at actual price Y → label Y
    ctx.save();
    ctx.strokeStyle = p.color;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(p.connX, p.actualY);
    ctx.lineTo(chartW + 6, p.y);
    ctx.stroke();
    ctx.restore();

    const el = document.createElement('div');
    el.className = 'slabel';
    el.textContent = p.name;
    el.style.left = (chartW + 8) + 'px';
    el.style.top = (p.y - 8) + 'px';
    el.style.color = p.color;
    // Left-click: show detail popup
    el.addEventListener('click', e => { e.stopPropagation(); showStockPopup(e, p.code); });
    // Right-click or long-press: jump to THS directly
    el.addEventListener('contextmenu', e => {
      e.preventDefault();
      const m = STOCK_META[p.code];
      if (m) window.open(ths_url(m.code, m.market), '_blank');
    });
    let _lpt = null;
    el.addEventListener('touchstart', () => { _lpt = setTimeout(() => { const m = STOCK_META[p.code]; if (m) window.open(ths_url(m.code, m.market), '_blank'); }, 600); }, { passive: true });
    el.addEventListener('touchend',  () => clearTimeout(_lpt), { passive: true });
    el.addEventListener('touchmove', () => clearTimeout(_lpt), { passive: true });
    labelLayer.appendChild(el);
  });
}

// ── Stock detail popup ───────────────────────────────────────────────────────

function ths_url(code, market) {
  if (market === 'hk') return 'https://stockpage.10jqka.com.cn/HK/' + code + '/';
  return 'https://stockpage.10jqka.com.cn/' + code + '/';
}

function xueqiu_url(code, market) {
  if (market === 'us') return 'https://xueqiu.com/S/' + code;
  if (market === 'hk') return 'https://xueqiu.com/S/HK' + code;
  return 'https://xueqiu.com/S/' + (code.startsWith('6') ? 'SH' : 'SZ') + code;
}

function showStockPopup(e, code) {
  const m = STOCK_META[code];
  if (!m) return;
  const pp = document.getElementById('spopup');

  pp.querySelector('.sp-name').textContent = m.name;
  pp.querySelector('.sp-code').textContent = m.code;

  const badge = pp.querySelector('.sp-market');
  badge.textContent = MKTLABEL[m.market] || m.market;
  badge.style.background = { a: '#3D9162', hk: '#2E7DD1', us: '#8B7EC8' }[m.market] || '#555';

  const todayEl = pp.querySelector('.sp-today');
  todayEl.textContent = (m.change_today >= 0 ? '+' : '') + m.change_today.toFixed(2) + '%';
  todayEl.style.color = m.change_today >= 0 ? '#5BAD7F' : '#D4667A';

  pp.querySelector('.sp-price').textContent = m.last_price.toFixed(2);

  const el7d = pp.querySelector('.sp-7d');
  el7d.textContent = (m.change_7d >= 0 ? '+' : '') + m.change_7d.toFixed(2) + '%';
  el7d.style.color = m.change_7d >= 0 ? '#5BAD7F' : '#D4667A';

  const descBlock = pp.querySelector('.sp-desc-block');
  if (m.desc) {
    pp.querySelector('.sp-desc').textContent = m.desc;
    descBlock.style.display = '';
  } else {
    descBlock.style.display = 'none';
  }

  pp.querySelector('.sp-ths').onclick = () => window.open(ths_url(m.code, m.market), '_blank');
  pp.querySelector('.sp-xq').onclick  = () => window.open(xueqiu_url(m.code, m.market), '_blank');

  // Measure then position
  pp.style.visibility = 'hidden';
  pp.style.display = 'block';
  const ppW = pp.offsetWidth, ppH = pp.offsetHeight;
  const vpW = window.innerWidth, vpH = window.innerHeight;
  const r = e.target.getBoundingClientRect();
  let left = r.right + 8;
  if (left + ppW > vpW - 8) left = r.left - ppW - 8;
  let top = r.top - 20;
  if (top + ppH > vpH - 8) top = vpH - ppH - 8;
  pp.style.left = Math.max(4, left) + 'px';
  pp.style.top  = Math.max(4, top)  + 'px';
  pp.style.visibility = '';
}

document.addEventListener('click', e => {
  const pp = document.getElementById('spopup');
  if (pp.style.display !== 'none' && !pp.contains(e.target)) pp.style.display = 'none';
});

// ── Toggle daily / weekly ───────────────────────────────────────────────────

function setMode(m) {
  mode = m;
  document.getElementById('btn-d').className = 'tbtn' + (m === 'daily' ? ' active' : '');
  document.getElementById('btn-w').className = 'tbtn' + (m === 'weekly' ? ' active' : '');
  chartStates.forEach(state => refreshChartData(state));
}

// ── Time-range filter ───────────────────────────────────────────────────────

function setRangeFilter(f) {
  rangeFilter = (rangeFilter === f) ? null : f;
  document.getElementById('btn-2w').className = 'tbtn' + (rangeFilter === '2w' ? ' active' : '');
  document.getElementById('btn-2m').className = 'tbtn' + (rangeFilter === '2m' ? ' active' : '');
  chartStates.forEach(state => refreshChartData(state));
}

// ── Ranking mode toggle ─────────────────────────────────────────────────────

function setRankingMode(m) {
  rankingMode = m;
  document.getElementById('btn-r1').className = 'tbtn' + (m === 'today' ? ' active' : '');
  document.getElementById('btn-r7').className = 'tbtn' + (m === '7d' ? ' active' : '');
  document.getElementById('ranking-title').textContent =
    m === '7d' ? '7-Day Performance' : "Today's Performance";
  buildRanking();
}

// ── Ranking dual-column bar chart ───────────────────────────────────────────

function stockUrl(r) {
  if (r.market === 'a')  return 'https://stockpage.10jqka.com.cn/' + r.code + '/';
  return 'https://xueqiu.com/S/' + r.code;
}

function buildRanking() {
  const container = document.getElementById('rbars');
  container.innerHTML = '';
  const data = rankingMode === '7d' ? RANKINGS : RANKINGS_TODAY;
  if (!data.length) return;

  // data is sorted ascending; losers at front (most negative first), gainers at back
  const losers = data.filter(r => r.pct < 0).slice(0, RANKING_LIMIT);
  const gainers = data.filter(r => r.pct > 0).reverse().slice(0, RANKING_LIMIT);
  const nRows = Math.max(losers.length, gainers.length);
  if (!nRows) return;

  const maxAbs = Math.max(
    ...losers.map(r => Math.abs(r.pct)),
    ...gainers.map(r => r.pct),
    0.01
  );

  const dual = document.createElement('div');
  dual.className = 'rank-dual';

  const lossCol = document.createElement('div');
  lossCol.className = 'rank-loss-col';

  const gainCol = document.createElement('div');
  gainCol.className = 'rank-gain-col';

  for (let i = 0; i < nRows; i++) {
    // ── Loss row ──
    if (losers[i]) {
      const r = losers[i];
      const w = Math.abs(r.pct) / maxAbs * 100;
      const row = document.createElement('div');
      row.className = 'rank-row-loss';
      row.title = r.name;
      row.onclick = () => window.open(stockUrl(r), '_blank');
      row.innerHTML =
        '<div class="rl-bar-area"><div class="rl-bar" style="width:' + w + '%"></div></div>' +
        '<div class="rl-pct">' + r.pct.toFixed(2) + '%</div>' +
        '<div class="rl-name">' + r.name + '</div>';
      lossCol.appendChild(row);
    } else {
      const empty = document.createElement('div');
      empty.className = 'rank-row-empty';
      lossCol.appendChild(empty);
    }

    // ── Gain row ──
    if (gainers[i]) {
      const r = gainers[i];
      const w = r.pct / maxAbs * 100;
      const row = document.createElement('div');
      row.className = 'rank-row-gain';
      row.title = r.name;
      row.onclick = () => window.open(stockUrl(r), '_blank');
      row.innerHTML =
        '<div class="rg-name">' + r.name + '</div>' +
        '<div class="rg-pct">+' + r.pct.toFixed(2) + '%</div>' +
        '<div class="rg-bar-area"><div class="rg-bar" style="width:' + w + '%"></div></div>';
      gainCol.appendChild(row);
    } else {
      const empty = document.createElement('div');
      empty.className = 'rank-row-empty';
      gainCol.appendChild(empty);
    }
  }

  dual.appendChild(lossCol);
  dual.appendChild(gainCol);
  container.appendChild(dual);
}

init();

// Fine-tune iframe height using layout positions (works regardless of overflow/scrollHeight quirks)
function fitFrame() {
  try {
    if (!window.frameElement) return;
    const ids = ['header', 'briefing', 'toggle-bar', 'charts', 'ranking'];
    const bottom = ids.reduce((max, id) => {
      const el = document.getElementById(id);
      return el ? Math.max(max, el.offsetTop + el.offsetHeight) : max;
    }, 0);
    if (bottom > 0) window.frameElement.style.height = (bottom + 32) + 'px';
  } catch(e) {}
}
fitFrame();
setTimeout(fitFrame, 400);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Test entry point with fake data
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import random

    random.seed(42)
    base_date = date.today() - timedelta(days=90)

    def _fake(name: str, code: str, market: str, price: float) -> dict:
        records, p = [], price
        for i in range(90):
            d = base_date + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            o = p * (1 + random.uniform(-0.015, 0.015))
            c = o * (1 + random.uniform(-0.015, 0.015))
            records.append({
                "date": d.strftime("%Y-%m-%d"),
                "open": round(o, 2), "close": round(c, 2),
                "high": round(max(o, c) * 1.005, 2),
                "low": round(min(o, c) * 0.995, 2),
                "volume": random.randint(500_000, 20_000_000),
            })
            p = c
        return {"name": name, "code": code, "market": market, "data": records}

    test_groups = [
        {"name": "主力股", "stocks": [
            _fake("英伟达",  "NVDA",   "us", 130.0),
            _fake("五粮液",  "000858", "a",  120.0),
            _fake("新易盛",  "300502", "a",  185.0),
            _fake("铖昌科技","001270", "a",   40.0),
        ]},
        {"name": "生物医药", "stocks": [
            _fake("翰森制药","03692",  "hk",  35.0),
            _fake("康诺亚",  "02162",  "hk",  60.0),
            _fake("亚虹医药","688176", "a",   12.0),
            _fake("智翔金泰","688443", "a",   34.0),
            _fake("益方生物","688382", "a",   48.0),
        ]},
    ]

    render(test_groups)
