import json
import time
from datetime import date, timedelta
from pathlib import Path

import baostock as bs
import pandas as pd
import yaml
import yfinance as yf

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
STOCKS_PATH = ROOT / "stocks.yaml"


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _window() -> tuple[str, str]:
    """Return (start, end) as YYYY-MM-DD strings for the past 90 calendar days."""
    end = date.today()
    start = end - timedelta(days=90)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _bs_prefix(code: str) -> str:
    """Return 'sh' or 'sz' baostock market prefix based on stock code."""
    return "sh" if code.startswith("6") else "sz"


def fetch_a(code: str) -> list[dict]:
    """A-share daily OHLCV via baostock (post-rights adjusted, hfq)."""
    start, end = _window()
    rs = bs.query_history_k_data_plus(
        f"{_bs_prefix(code)}.{code}",
        "date,open,close,high,low,volume",
        start_date=start, end_date=end,
        frequency="d", adjustflag="2",
    )
    if rs.error_code != "0":
        raise RuntimeError(f"baostock {rs.error_code}: {rs.error_msg}")
    records = []
    while rs.next():
        row = rs.get_row_data()
        try:
            records.append({
                "date": row[0],
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "volume": int(float(row[5])),
            })
        except (ValueError, IndexError):
            continue
    return records


def fetch_hk(code: str) -> list[dict]:
    """HK-listed stock OHLCV via yfinance (leading zeros stripped, .HK suffix)."""
    df = yf.Ticker(f"{code.lstrip('0')}.HK").history(period="3mo").reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={
        "Date": "date", "Open": "open", "Close": "close",
        "High": "high", "Low": "low", "Volume": "volume",
    })[["date", "open", "close", "high", "low", "volume"]]
    return df.to_dict(orient="records")


def fetch_us(code: str) -> list[dict]:
    """US-listed stock OHLCV via yfinance for the past month."""
    df = yf.Ticker(code).history(period="3mo").reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={
        "Date": "date", "Open": "open", "Close": "close",
        "High": "high", "Low": "low", "Volume": "volume",
    })[["date", "open", "close", "high", "low", "volume"]]
    return df.to_dict(orient="records")


_FETCHERS = {"a": fetch_a, "hk": fetch_hk, "us": fetch_us}


def _load_cache(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_all() -> list[dict]:
    """
    Fetch OHLCV data for every stock in stocks.yaml.

    Returns groups structure: [{"name": str, "stocks": [{name, code, market, data}]}]
    Failed stocks are skipped with a warning; cache in output/cache.json avoids
    redundant network calls within the same day.
    """
    config = _load_yaml(CONFIG_PATH)
    stocks_cfg = _load_yaml(STOCKS_PATH)

    cache_dir = ROOT / config.get("data", {}).get("cache_dir", "output")
    cache_path = cache_dir / "cache.json"
    today = date.today().isoformat()

    cache = _load_cache(cache_path)
    cache_dirty = False
    result = []

    lg = bs.login()
    if lg.error_code != "0":
        print(f"[WARN] baostock login failed: {lg.error_msg}")

    try:
        for group in stocks_cfg["groups"]:
            group_out = {"name": group["name"], "stocks": []}

            for stock in group["stocks"]:
                name, code, market = stock["name"], stock["code"], stock["market"]
                key = f"{today}:{code}"

                if key in cache:
                    data = cache[key]
                    d_range = f"{data[0]['date']} ~ {data[-1]['date']}" if data else "no data"
                    print(f"[CACHE] {name} ({code}, {market}): {len(data)} records [{d_range}]")
                    group_out["stocks"].append(
                        {"name": name, "code": code, "market": market, "data": data}
                    )
                    continue

                fetcher = _FETCHERS.get(market)
                if fetcher is None:
                    print(f"[WARN] Unknown market '{market}' for {name} ({code})")
                    continue

                for attempt in range(3):
                    try:
                        if attempt:
                            time.sleep(3 * attempt)
                        data = fetcher(code)
                        cache[key] = data
                        cache_dirty = True
                        group_out["stocks"].append(
                            {"name": name, "code": code, "market": market, "data": data}
                        )
                        d_range = f"{data[0]['date']} ~ {data[-1]['date']}" if data else "no data"
                        print(f"[OK]   {name} ({code}, {market}): {len(data)} records [{d_range}]")
                        break
                    except Exception as exc:
                        if attempt == 2:
                            print(f"[WARN] {name} ({code}, {market}): {exc}")
                        else:
                            print(f"[RETRY {attempt+1}] {name} ({code}): {exc}")

            result.append(group_out)
    finally:
        bs.logout()

    if cache_dirty:
        _save_cache(cache_path, cache)

    return result


if __name__ == "__main__":
    groups = fetch_all()
    print("\n── Summary ──")
    for g in groups:
        print(f"  {g['name']}: {len(g['stocks'])} stocks fetched")
