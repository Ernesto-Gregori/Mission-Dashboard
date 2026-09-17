"""CSS tokens: secondary colors live in :root, not on selectors."""
from pathlib import Path

CSS = Path("web/static/css/app.css")


def _root_and_rest(css: str) -> tuple[str, str]:
    start = css.index(":root")
    brace = css.index("{", start)
    depth = 0
    for i, ch in enumerate(css[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return css[start : i + 1], css[i + 1 :]
    raise AssertionError("unterminated :root block")


def test_secondary_colors_live_in_tokens():
    root, rest = _root_and_rest(CSS.read_text())
    assert "--on-accent:" in root
    assert "--ok-text:" in root
    assert "#04101f" in root
    assert "#9be9a8" in root
    assert "#04101f" not in rest
    assert "#9be9a8" not in rest
