# Copyright (c) 2026 Xuan Luo
# SPDX-License-Identifier: MIT
"""
main.py — Bootblack pipeline entry point

Normal run:            python src/main.py
Refresh briefing:      python src/main.py --briefing   (calls Claude API, costs ~$0.001)
Test mode:             python src/main.py --test       (synthetic data, skips real API calls)

Scheduled runs never call the briefing API — use --briefing explicitly to refresh.
"""

import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml

import briefing as briefing_mod
import exporter
import fetcher
import renderer
import writer


CONFIG_PATH = ROOT / "config.yaml"


def _step(n: int, total: int, label: str) -> None:
    print(f"[Bootblack] {n:02d}/{total:02d} {label}...")


def _git_push() -> None:
    """git add → commit → push；nothing-to-commit 时静默跳过。"""
    msg = f"update: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    try:
        subprocess.run(
            ["git", "add", "output/bootblack.html"],
            cwd=ROOT, check=True, capture_output=True,
        )
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                print("[Bootblack] nothing to commit, skipping push")
                return
            print(f"[ERROR] git commit failed: {result.stderr.strip()}")
            return
        subprocess.run(
            ["git", "push"],
            cwd=ROOT, check=True, capture_output=True,
        )
        print(f"[OK] pushed to GitHub ({msg})")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] git error: {e.stderr.decode(errors='replace').strip() if e.stderr else e}")


def run() -> None:
    """Full pipeline: fetch → briefing → render → inject → export → push."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    auto_push = cfg.get("git", {}).get("auto_push", False)

    total = 6 if auto_push else 5
    t0 = time.perf_counter()

    _step(1, total, "fetching price data")
    groups = fetcher.fetch_all()

    _step(2, total, "generating briefing")
    brief = briefing_mod.generate(groups, force="--briefing" in sys.argv)

    _step(3, total, "rendering charts")
    renderer.render(groups, briefing=brief)

    _step(4, total, "injecting Obsidian file")
    writer.inject()

    _step(5, total, "exporting stock list")
    exporter.export()

    if auto_push:
        _step(6, total, "pushing to GitHub")
        _git_push()

    elapsed = time.perf_counter() - t0
    print(f"[Bootblack] done  {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Test mode: run renderer / writer / exporter pipeline with synthetic data
# ---------------------------------------------------------------------------
import random


def _fake_stock(name: str, code: str, market: str, price: float) -> dict:
    records, p = [], price
    base = date.today() - timedelta(days=35)
    random.seed(abs(hash(code)) % 2**31)
    for i in range(35):
        d = base + timedelta(days=i)
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


def run_test() -> None:
    """Test mode: run renderer → writer → exporter with synthetic data, skipping real API calls."""
    total = 3
    t0 = time.perf_counter()

    test_groups = [
        {"name": "主力股", "stocks": [
            _fake_stock("五粮液",   "000858", "a",  120.0),
            _fake_stock("新易盛",   "300502", "a",  185.0),
            _fake_stock("铖昌科技", "001270", "a",   40.0),
            _fake_stock("中国科培", "01890",  "hk",   1.5),
        ]},
        {"name": "生物医药", "stocks": [
            _fake_stock("翰森制药", "03692",  "hk",  35.0),
            _fake_stock("康诺亚",   "02162",  "hk",  60.0),
            _fake_stock("亚虹医药", "688176", "a",   12.0),
            _fake_stock("智翔金泰", "688443", "a",   34.0),
            _fake_stock("益方生物", "688382", "a",   48.0),
            _fake_stock("复宏汉霖", "02696",  "hk",  70.0),
            _fake_stock("迈博药业", "02181",  "hk",   0.55),
        ]},
        {"name": "段永平", "stocks": [
            _fake_stock("特斯拉",   "TSLA",   "us", 340.0),
            _fake_stock("拼多多",   "PDD",    "us", 110.0),
            _fake_stock("谷歌",     "GOOGL",  "us", 175.0),
            _fake_stock("伯克希尔", "BRK-B",  "us", 530.0),
            _fake_stock("英伟达",   "NVDA",   "us", 130.0),
        ]},
    ]

    fake_brief = {
        "cn": "测试日报：今日组合整体平稳，合成数据仅供渲染验证，不代表真实行情。",
        "en": "Test briefing: synthetic data, rendering pipeline only. No markets were harmed.",
    }

    _step(1, total, "rendering charts (synthetic data)")
    renderer.render(test_groups, briefing=fake_brief)

    _step(2, total, "injecting Obsidian file")
    writer.inject()

    _step(3, total, "exporting stock list")
    exporter.export()

    elapsed = time.perf_counter() - t0
    print(f"[Bootblack] done  {elapsed:.1f}s")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        run()
