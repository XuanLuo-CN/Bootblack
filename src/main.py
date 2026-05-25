"""
main.py — Bootblack 全流程入口

正常运行：  python src/main.py
测试模式：  python src/main.py --test   （用假数据，跳过真实 API 调用）
"""

import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml

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
                print("[Bootblack] 无变更，跳过推送")
                return
            print(f"[ERROR] git commit 失败：{result.stderr.strip()}")
            return
        subprocess.run(
            ["git", "push"],
            cwd=ROOT, check=True, capture_output=True,
        )
        print(f"[OK] 已推送到 GitHub（{msg}）")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] git 操作失败：{e.stderr.decode(errors='replace').strip() if e.stderr else e}")


def run() -> None:
    """完整流程：抓取 → 渲染 → 注入 → 导出 → 推送。"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    auto_push = cfg.get("git", {}).get("auto_push", False)

    total = 5 if auto_push else 4
    t0 = time.perf_counter()

    _step(1, total, "抓取股价数据")
    groups = fetcher.fetch_all()

    _step(2, total, "生成可视化图表")
    renderer.render(groups)

    _step(3, total, "注入 Obsidian 文件")
    writer.inject()

    _step(4, total, "导出股票清单")
    exporter.export()

    if auto_push:
        _step(5, total, "推送到 GitHub")
        _git_push()

    elapsed = time.perf_counter() - t0
    print(f"[Bootblack] 完成  耗时 {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# 测试模式：用假数据验证 renderer / writer / exporter 三步管道
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
    """测试模式：假数据跑完 renderer → writer → exporter，跳过真实 API。"""
    total = 3
    t0 = time.perf_counter()

    test_groups = [
        {"name": "主力股", "stocks": [
            _fake_stock("英伟达",   "NVDA",   "us", 130.0),
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
    ]

    _step(1, total, "生成可视化图表（假数据）")
    renderer.render(test_groups)

    _step(2, total, "注入 Obsidian 文件")
    writer.inject()

    _step(3, total, "导出股票清单")
    exporter.export()

    elapsed = time.perf_counter() - t0
    print(f"[Bootblack] 完成  耗时 {elapsed:.1f}s")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        run()
