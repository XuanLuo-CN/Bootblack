import json
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


def _agg_weekly(records: list) -> list:
    """Return last trading day of each ISO week (weekly close aggregation)."""
    by_week: dict = {}
    for r in records:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        by_week[dt.isocalendar()[:2]] = r
    return sorted(by_week.values(), key=lambda r: r["date"])


def render(groups: list, output_path: Path = OUTPUT_PATH) -> None:
    """
    Render fetcher output to a self-contained HTML dashboard.

    groups: list returned by fetcher.fetch_all()
    """
    meta = _load_meta()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ranking_limit = int(cfg.get("ranking_limit", 10))
    charts_per_row = int(cfg.get("charts_per_row", 2))
    group_max_stocks = int(cfg.get("group_max_stocks", 8))

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

    # Pre-compute page height so writer.py can set iframe height without JS
    n_groups_with_data = sum(1 for g in chart_groups if g["series"])
    n_rank_rows = max(
        min(sum(1 for r in rankings if r["pct"] < 0), ranking_limit),
        min(sum(1 for r in rankings if r["pct"] > 0), ranking_limit),
    )
    n_chart_rows = (n_groups_with_data + charts_per_row - 1) // charts_per_row
    page_height = max(200 + n_chart_rows * 420 + 40 + n_rank_rows * 30 + 200, 1200)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = _TEMPLATE
    html = html.replace("__GROUPS__", json.dumps(chart_groups, ensure_ascii=False))
    html = html.replace("__RANKINGS__", json.dumps(rankings, ensure_ascii=False))
    html = html.replace("__RANKINGS_TODAY__", json.dumps(rankings_today, ensure_ascii=False))
    html = html.replace("__UPDATED__", now)
    html = html.replace("__RANKING_LIMIT__", str(ranking_limit))
    html = html.replace("__COLS__", str(charts_per_row))
    html = html.replace("__HEIGHT__", str(page_height))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"[OK] written → {output_path}")


# ---------------------------------------------------------------------------
# HTML template — placeholders: __GROUPS__  __RANKINGS__  __UPDATED__  __RANKING_LIMIT__
# ---------------------------------------------------------------------------
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-bb-height="__HEIGHT__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BOOTBLACK</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: transparent; color: #e0e0e0; font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; transition: none; }

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
.chart-wrap { position: relative; height: 320px; }
/* Weaken TradingView attribution logo */
.tv-lightweight-charts a[href*="tradingview"] {
  opacity: 0.12 !important;
  transform: scale(0.55) !important;
  transform-origin: bottom right !important;
}
.chart-el { width: 100%; height: 100%; }

.label-layer { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
.slabel {
  position: absolute;
  right: 72px;
  transform: translateY(-50%);
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 2px;
  cursor: default;
  pointer-events: all;
  white-space: nowrap;
  border-left: 2px solid currentColor;
  background: rgba(20,20,18,0.82);
  transition: opacity .1s;
}
.slabel:hover { opacity: 0.85; }

.c-tooltip {
  position: absolute; background: rgba(30,30,28,0.92); border: 1px solid #2e2e2c;
  border-radius: 4px; padding: 8px 11px; font-size: 11px;
  pointer-events: none; z-index: 50; display: none;
  white-space: nowrap; line-height: 1.9;
}

#lpopup {
  position: fixed; background: #252523; border: 1px solid #363634;
  border-radius: 6px; padding: 11px 14px; font-size: 12px;
  max-width: 320px; z-index: 999; display: none;
  box-shadow: 0 8px 24px rgba(0,0,0,.55); pointer-events: none;
}
#lpopup .lp-market { font-size: 10px; color: #555; margin-bottom: 6px; letter-spacing: 0.05em; }
#lpopup .lp-desc { color: #b0b0b0; line-height: 1.6; font-size: 12px; }

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
    <button class="tbtn" onclick="buildCharts();buildRanking()">刷新</button>
  </div>
</div>

<div id="toggle-bar">
  <button class="tbtn active" id="btn-d" onclick="setMode('daily')">日线</button>
  <button class="tbtn" id="btn-w" onclick="setMode('weekly')">周线</button>
  <div style="margin-left:auto;display:flex;gap:6px;">
    <button class="tbtn" id="btn-2w" onclick="setRangeFilter('2w')">2周</button>
    <button class="tbtn" id="btn-2m" onclick="setRangeFilter('2m')">2月</button>
  </div>
</div>

<div id="charts"></div>
<div id="ranking">
  <div style="display:flex;align-items:center;margin-bottom:18px;">
    <h2 id="ranking-title">7-Day Performance</h2>
    <div style="margin-left:auto;display:flex;gap:6px;">
      <button class="tbtn active" id="btn-r7" onclick="setRankingMode('7d')">7日</button>
      <button class="tbtn" id="btn-r1" onclick="setRankingMode('today')">今日</button>
    </div>
  </div>
  <div id="rbars"></div>
</div>

<div id="lpopup">
  <div class="lp-market"></div>
  <div class="lp-desc"></div>
</div>

<script>
const GROUPS = __GROUPS__;
const RANKINGS = __RANKINGS__;
const RANKINGS_TODAY = __RANKINGS_TODAY__;
const RANKING_LIMIT = __RANKING_LIMIT__;
const MKTLABEL = { a: 'A股', hk: '港股', us: '美股' };

let mode = 'daily';
let rangeFilter = null;   // null | '2w' | '2m'
let rankingMode = '7d';   // '7d' | 'today'
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
  state.seriesArr.forEach(({ ser, meta }) => {
    const disp = getDisplayData(meta[rawKey], rangeFilter);
    ser.setData(disp);
    meta._disp = disp;
    maxLen = Math.max(maxLen, disp.length);
  });
  state.maxDataLen = maxLen;
  state.chart.timeScale().fitContent();
  setTimeout(() => placeLabels(state), 150);
}

function init() {
  buildCharts();
  buildRanking();
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

    const cTooltip = document.createElement('div');
    cTooltip.className = 'c-tooltip';
    wrap.appendChild(cTooltip);

    sec.appendChild(wrap);
    root.appendChild(sec);

    const state = { maxDataLen: 0 };

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
      rightPriceScale: { borderColor: '#2c2c2a' },
      timeScale: {
        borderColor: '#2c2c2a',
        timeVisible: true,
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
          if (tickMarkType <= 1) return month + '月';
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
      const maxIdx = Math.max(state.maxDataLen, 1) - 1;
      const clampedFrom = Math.max(0, range.from);
      const clampedTo   = Math.min(maxIdx, range.to);
      if (clampedFrom !== range.from || clampedTo !== range.to) {
        requestAnimationFrame(() => {
          chart.timeScale().setVisibleLogicalRange({ from: clampedFrom, to: clampedTo });
        });
      }
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
    state.cTooltip = cTooltip;
    state.chartEl = chartEl;
    chartStates.push(state);
    refreshChartData(state);
  });
}

// ── End-of-series labels ────────────────────────────────────────────────────

function placeLabels(state) {
  const { chart, seriesArr, labelLayer, chartEl } = state;
  labelLayer.innerHTML = '';
  const H = chartEl.clientHeight;
  const positions = [];

  seriesArr.forEach(({ ser, meta }) => {
    const data = meta._disp || meta[mode];
    if (!data || !data.length) return;
    const lastPt = data[data.length - 1];
    const y = ser.priceToCoordinate(lastPt.value);
    if (y === null || y < 8 || y > H - 8) return;
    positions.push({ y, color: meta.color, name: meta.name, desc: meta.desc, market: meta.market });
  });

  positions.sort((a, b) => a.y - b.y);
  const GAP = 17;
  for (let i = 1; i < positions.length; i++) {
    if (positions[i].y - positions[i - 1].y < GAP) {
      positions[i].y = positions[i - 1].y + GAP;
    }
  }

  positions.forEach(p => {
    const el = document.createElement('div');
    el.className = 'slabel';
    el.textContent = p.name;
    el.style.top = p.y + 'px';
    el.style.color = p.color;
    el.addEventListener('mouseenter', e => showPopup(e, p));
    el.addEventListener('mousemove', e => movePopup(e));
    el.addEventListener('mouseleave', hidePopup);
    labelLayer.appendChild(el);
  });
}

// ── Label popup ─────────────────────────────────────────────────────────────

function showPopup(e, p) {
  const pp = document.getElementById('lpopup');
  pp.querySelector('.lp-market').textContent = MKTLABEL[p.market] || p.market;
  pp.querySelector('.lp-desc').textContent = p.desc || '';
  pp.querySelector('.lp-desc').style.display = p.desc ? '' : 'none';
  pp.style.left = (e.clientX + 14) + 'px';
  pp.style.top = (e.clientY - 10) + 'px';
  pp.style.display = 'block';
}
function movePopup(e) {
  const pp = document.getElementById('lpopup');
  pp.style.left = (e.clientX + 14) + 'px';
  pp.style.top = (e.clientY - 10) + 'px';
}
function hidePopup() { document.getElementById('lpopup').style.display = 'none'; }

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
  document.getElementById('btn-r7').className = 'tbtn' + (m === '7d' ? ' active' : '');
  document.getElementById('btn-r1').className = 'tbtn' + (m === 'today' ? ' active' : '');
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
    const ids = ['header', 'toggle-bar', 'charts', 'ranking'];
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
