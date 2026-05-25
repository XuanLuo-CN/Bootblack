from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
STOCKS_PATH = ROOT / "stocks.yaml"
OUTPUT_PATH = ROOT / "output" / "stocks.md"

MARKET_ZH = {"a": "A股", "hk": "港股", "us": "美股"}


def export(output_path: Path = OUTPUT_PATH) -> None:
    """从 stocks.yaml 生成 Markdown 股票清单，写入 output/stocks.md。"""
    with open(STOCKS_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 鞋童股票清单",
        "",
        "> 自动生成，请勿手动编辑。如需修改请编辑 stocks.yaml",
        f"> 最后更新：{now}",
    ]

    for group in cfg.get("groups", []):
        lines.append("")
        lines.append(f"## {group['name']}")
        lines.append("")
        lines.append("| 名称 | 代码 | 市场 | 描述 |")
        lines.append("|------|------|------|------|")

        for s in group.get("stocks", []):
            name = s["name"]
            code = s["code"]
            market = MARKET_ZH.get(s["market"], s["market"])
            desc = s.get("desc") or "-"
            # 描述中的竖线会破坏 Markdown 表格，替换为顿号
            desc = desc.replace("|", "、")
            lines.append(f"| {name} | {code} | {market} | {desc} |")

    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] stocks.md 已写入 → {output_path}")


if __name__ == "__main__":
    export()
    print(Path(OUTPUT_PATH).read_text(encoding="utf-8")[:800])
