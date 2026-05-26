"""
briefing.py — Bilingual daily market briefing via Claude API.

Normal pipeline runs use cached briefing and never call the API.
Pass force=True (via --briefing CLI flag) to regenerate.
"""

import json
import re
from datetime import date
from pathlib import Path

import anthropic
import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
SECRETS_PATH = ROOT / ".secrets.yaml"
CACHE_PATH = ROOT / "output" / "briefing_cache.json"

# (input $/MTok, output $/MTok) — used for cost estimates
_PRICING = {
    "claude-haiku-4-5":   (0.80,  4.00),
    "claude-haiku-4-6":   (0.80,  4.00),
    "claude-sonnet-4-5":  (3.00, 15.00),
    "claude-sonnet-4-6":  (3.00, 15.00),
    "claude-opus-4-7":   (15.00, 75.00),
}

_SYSTEM = (
    "You are a sharp, concise financial analyst covering a private portfolio. "
    "Given today's stock performance data, write a daily market briefing. "
    "Focus on notable movers, patterns, and overall portfolio sentiment. "
    "Be specific and factual — no filler. "
    "The English version should read like a Reuters wire brief "
    "with a dry, slightly sardonic undertone. Keep it under 80 words."
)

_LANG_INSTRUCTION = (
    "\nWrite both versions with this exact structure: "
    "an untitled overview paragraph first, then one paragraph per portfolio group "
    "with the group name as a **bold heading** on its own line.\n"
    "Use this format exactly:\n"
    "[CN]\n"
    "（总体概述，无标题）\n\n"
    "**组名**\n"
    "（该组分析）\n\n"
    "[EN]\n"
    "(overall summary, no heading)\n\n"
    "**Group Name**\n"
    "(group analysis)"
)


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _call_cost(model: str, input_tok: int, output_tok: int) -> float:
    for prefix, (inp, out) in _PRICING.items():
        if model.startswith(prefix):
            return (input_tok * inp + output_tok * out) / 1_000_000
    return 0.0


def _build_prompt(groups: list[dict]) -> str:
    today = date.today().isoformat()
    lines = [f"Portfolio performance as of {today}:\n"]
    for group in groups:
        lines.append(f"Group: {group['name']}")
        for s in group.get("stocks", []):
            d = s.get("data", [])
            if not d:
                continue
            last = d[-1]
            open_p = float(last.get("open") or 0)
            close_p = float(last.get("close") or 0)
            today_pct = (close_p - open_p) / open_p * 100 if open_p else 0.0
            base_7d = float(d[max(0, len(d) - 8)].get("close") or close_p) or 1
            week_pct = (close_p - base_7d) / base_7d * 100
            st = "+" if today_pct >= 0 else ""
            sw = "+" if week_pct >= 0 else ""
            lines.append(
                f"  {s['name']} ({s['code']}, {s['market'].upper()}): "
                f"today {st}{today_pct:.1f}%,  7-day {sw}{week_pct:.1f}%,  price {close_p:.2f}"
            )
        lines.append("")
    lines.append(_LANG_INSTRUCTION)
    return "\n".join(lines)


def _parse_response(text: str) -> tuple[str, str]:
    cn_m = re.search(r"\[CN\]\s*\n(.*?)(?=\[EN\]|\Z)", text, re.DOTALL)
    en_m = re.search(r"\[EN\]\s*\n(.*?)(?=\[CN\]|\Z)", text, re.DOTALL)
    cn = cn_m.group(1).strip() if cn_m else ""
    en = en_m.group(1).strip() if en_m else ""
    return cn, en


def generate(groups: list[dict], force: bool = False) -> dict:
    """
    Return a bilingual briefing dict.

    force=False (default): return cached entry without calling the API.
                           Returns {} if no cache exists yet.
    force=True:            always call the API, update cache and cost counters.
    """
    cache = _load_cache()

    today = date.today().isoformat()
    already_today = cache.get("generated_date") == today and (cache.get("cn") or cache.get("en"))

    if not force:
        if cache.get("cn") or cache.get("en"):
            print("[CACHE] briefing: using cached entry (run with --briefing to refresh)")
        else:
            print("[SKIP]  briefing: no cache — run with --briefing to generate")
        return cache

    if already_today:
        print(f"[SKIP]  briefing: already generated today ({today}), skipping API call")
        return cache

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    briefing_cfg = cfg.get("briefing", {})
    model  = briefing_cfg.get("model", "claude-haiku-4-5-20251001")
    credit = float(briefing_cfg.get("credit", 0.0))

    # Load api_key from .secrets.yaml (gitignored) first, fall back to config.yaml
    api_key = None
    if SECRETS_PATH.exists():
        with open(SECRETS_PATH, encoding="utf-8") as f:
            secrets = yaml.safe_load(f) or {}
        api_key = secrets.get("briefing", {}).get("api_key")
    if not api_key:
        api_key = briefing_cfg.get("api_key") or None

    prompt = _build_prompt(groups)
    print(f"[OK]   briefing: calling Claude API ({model})...")
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    cn, en = _parse_response(raw)

    if not cn or not en:
        print(f"[WARN] briefing: could not parse CN/EN sections:\n{raw[:300]}")

    last_cost  = _call_cost(model, message.usage.input_tokens, message.usage.output_tokens)
    call_count = cache.get("call_count", 0) + 1
    total_cost = cache.get("total_cost_usd", 0.0) + last_cost

    days_remaining = None
    if credit > 0 and call_count > 0 and total_cost > 0:
        avg = total_cost / call_count
        remaining = credit - total_cost
        days_remaining = max(0, int(remaining / avg)) if avg > 0 else None

    entry = {
        "generated_date": date.today().isoformat(),
        "cn":             cn,
        "en":             en,
        "call_count":     call_count,
        "last_cost_usd":  round(last_cost, 6),
        "total_cost_usd": round(total_cost, 6),
        "days_remaining": days_remaining,
    }
    _save_cache(entry)
    print(
        f"[OK]   briefing: done  "
        f"tokens {message.usage.input_tokens}+{message.usage.output_tokens}  "
        f"cost ${last_cost:.4f}  total ${total_cost:.4f}"
    )
    return entry
