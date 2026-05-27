# Copyright (c) 2026 Xuan Luo
# SPDX-License-Identifier: MIT
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
STOCKS_PATH = ROOT / "stocks.yaml"
OUTPUT_PATH = ROOT / "output" / "stocks.md"

MARKET_LABEL = {"a": "A", "hk": "HK", "us": "US"}


def export(output_path: Path = OUTPUT_PATH) -> None:
    """Generate a Markdown stock list from stocks.yaml and write it to output/stocks.md."""
    with open(STOCKS_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Bootblack Stock List",
        "",
        "> Auto-generated. Do not edit manually — modify stocks.yaml instead.",
        f"> Last updated: {now}",
    ]

    for group in cfg.get("groups", []):
        lines.append("")
        lines.append(f"## {group['name']}")
        lines.append("")
        lines.append("| Name | Code | Market | Notes |")
        lines.append("|------|------|--------|-------|")

        for s in group.get("stocks", []):
            name = s["name"]
            code = s["code"]
            market = MARKET_LABEL.get(s["market"], s["market"])
            desc = s.get("desc") or "-"
            # pipe chars break markdown tables
            desc = desc.replace("|", ",")
            lines.append(f"| {name} | {code} | {market} | {desc} |")

    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] stocks.md written → {output_path}")


if __name__ == "__main__":
    export()
    print(Path(OUTPUT_PATH).read_text(encoding="utf-8")[:800])
