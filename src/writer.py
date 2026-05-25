import re
import shutil
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
HTML_PATH = ROOT / "output" / "bootblack.html"
BAK_PATH = ROOT / "output" / "market.md.bak"

# data-id 属性作为唯一锚点，替代之前的 HTML 注释标记
_IFRAME_PATTERN = re.compile(
    r'<iframe\s[^>]*data-id="bootblack"[^>]*>.*?</iframe>',
    re.DOTALL,
)
# 旧版注释标记格式，注入时自动迁移
_LEGACY_PATTERN = re.compile(
    r'<!-- BOOTBLACK_START -->.*?<!-- BOOTBLACK_END -->',
    re.DOTALL,
)


def _load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_height(html_path: Path) -> int:
    """从生成的 HTML 中读取预计算的页面高度。"""
    try:
        content = html_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'data-bb-height="(\d+)"', content)
        return int(m.group(1)) if m else 2000
    except Exception:
        return 2000


def _build_block(html_path: Path) -> str:
    """构造注入内容：带 data-id 标识的 iframe，高度由 HTML 预计算值决定。"""
    src = html_path.resolve().as_uri()
    height = _read_height(html_path)
    ts = int(time.time())
    return (
        f'<iframe data-id="bootblack" src="{src}?t={ts}" '
        f'width="100%" height="{height}" frameborder="0" style="display:block"></iframe>'
    )


def inject(md_path: Path | None = None, html_path: Path = HTML_PATH) -> None:
    """
    将 bootblack.html 以 iframe 形式注入 Obsidian md 文件。

    - 若已有 data-id="bootblack" 的 iframe，原地替换
    - 若不存在，在文件末尾追加
    - 注入前备份原文件到 output/market.md.bak
    """
    config = _load_config()

    if md_path is None:
        raw = config.get("obsidian", {}).get("md_path", "")
        if not raw or raw == "PLACEHOLDER":
            print("[ERROR] config.yaml 中 obsidian.md_path 未配置，请先填写路径。")
            return
        md_path = Path(raw)

    if not md_path.exists():
        print(f"[ERROR] 目标 md 文件不存在：{md_path}")
        return

    if not html_path.exists():
        print(f"[ERROR] HTML 文件不存在：{html_path}，请先运行 renderer.py。")
        return

    BAK_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(md_path, BAK_PATH)
    print(f"[OK] 已备份原文件 → {BAK_PATH}")

    original = md_path.read_text(encoding="utf-8")
    block = _build_block(html_path)

    # 迁移旧版注释标记格式
    if _LEGACY_PATTERN.search(original):
        original = _LEGACY_PATTERN.sub(block, original)
        updated = original
        action = "迁移旧版标记并替换 iframe"
    elif _IFRAME_PATTERN.search(original):
        updated = _IFRAME_PATTERN.sub(block, original)
        action = "替换已有 iframe"
    else:
        sep = "\n\n" if not original.endswith("\n\n") else "\n"
        updated = original.rstrip("\n") + sep + block + "\n"
        action = "末尾追加 iframe"

    md_path.write_text(updated, encoding="utf-8")
    print(f"[OK] {action} → {md_path}")


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile

    # 用临时 md 文件模拟两种情形

    # 情形 1：标记不存在，触发末尾追加
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write("# 市场监控\n\n这里是正文内容。\n")
        tmp1 = Path(f.name)

    print("── 情形 1：标记不存在 ──")
    inject(md_path=tmp1)
    result1 = tmp1.read_text(encoding="utf-8")
    assert _START in result1 and _END in result1, "追加失败"
    print("内容预览：")
    print(result1[-300:])

    # 情形 2：标记已存在，触发替换
    print("\n── 情形 2：标记已存在，执行替换 ──")
    inject(md_path=tmp1)
    result2 = tmp1.read_text(encoding="utf-8")
    assert result2.count(_START) == 1, "替换后标记数量不为 1"
    print(f"注入区块数量正确（1 个），全文共 {len(result2)} 字符。")

    # 清理
    tmp1.unlink()
    print("\n[PASS] 两种情形均通过。")
