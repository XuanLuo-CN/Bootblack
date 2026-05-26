import re
import shutil
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
HTML_PATH = ROOT / "output" / "bootblack.html"
BAK_PATH = ROOT / "output" / "market.md.bak"

# data-id attribute as unique anchor, replacing the old HTML comment markers
_IFRAME_PATTERN = re.compile(
    r'<iframe\s[^>]*data-id="bootblack"[^>]*>.*?</iframe>',
    re.DOTALL,
)
# legacy comment marker format, migrated automatically on inject
_LEGACY_PATTERN = re.compile(
    r'<!-- BOOTBLACK_START -->.*?<!-- BOOTBLACK_END -->',
    re.DOTALL,
)


def _load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_height(html_path: Path) -> int:
    """Read pre-computed page height from the generated HTML."""
    try:
        content = html_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'data-bb-height="(\d+)"', content)
        return int(m.group(1)) if m else 2000
    except Exception:
        return 2000


def _build_block(html_path: Path) -> str:
    """Build the injection block: a data-id-tagged iframe whose height comes from the pre-computed HTML value."""
    src = html_path.resolve().as_uri()
    height = _read_height(html_path)
    ts = int(time.time())
    return (
        f'<iframe data-id="bootblack" src="{src}?t={ts}" '
        f'width="100%" height="{height}" frameborder="0" style="display:block"></iframe>'
    )


def inject(md_path: Path | None = None, html_path: Path = HTML_PATH) -> None:
    """
    Inject bootblack.html as an iframe into the Obsidian md file.

    - If a data-id="bootblack" iframe already exists, replace it in-place.
    - Otherwise, append it at the end of the file.
    - Backs up the original file to output/market.md.bak before writing.
    """
    config = _load_config()

    if md_path is None:
        raw = config.get("obsidian", {}).get("md_path", "")
        if not raw or raw == "PLACEHOLDER":
            print("[ERROR] obsidian.md_path not configured in config.yaml")
            return
        md_path = Path(raw)

    if not md_path.exists():
        print(f"[ERROR] target md file not found: {md_path}")
        return

    if not html_path.exists():
        print(f"[ERROR] HTML file not found: {html_path} — run renderer.py first")
        return

    BAK_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(md_path, BAK_PATH)
    print(f"[OK] backup written → {BAK_PATH}")

    original = md_path.read_text(encoding="utf-8")
    block = _build_block(html_path)

    if _LEGACY_PATTERN.search(original):
        original = _LEGACY_PATTERN.sub(block, original)
        updated = original
        action = "migrated legacy markers and replaced iframe"
    elif _IFRAME_PATTERN.search(original):
        updated = _IFRAME_PATTERN.sub(block, original)
        action = "replaced existing iframe"
    else:
        sep = "\n\n" if not original.endswith("\n\n") else "\n"
        updated = original.rstrip("\n") + sep + block + "\n"
        action = "appended iframe at end of file"

    md_path.write_text(updated, encoding="utf-8")
    print(f"[OK] {action} → {md_path}")


# ---------------------------------------------------------------------------
# Test entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile

    # case 1: no existing marker — triggers append
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write("# Market Monitor\n\nBody content.\n")
        tmp1 = Path(f.name)

    print("── case 1: no existing marker ──")
    inject(md_path=tmp1)
    result1 = tmp1.read_text(encoding="utf-8")
    assert 'data-id="bootblack"' in result1, "append failed"
    print(result1[-300:])

    # case 2: marker present — triggers replacement
    print("\n── case 2: marker present, replacing ──")
    inject(md_path=tmp1)
    result2 = tmp1.read_text(encoding="utf-8")
    assert result2.count('data-id="bootblack"') == 1, "expected exactly 1 iframe after replace"
    print(f"iframe count correct (1), total length {len(result2)} chars")

    tmp1.unlink()
    print("\n[PASS] both cases passed")
