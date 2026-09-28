"""CSS tokens: secondary colors live in :root, not on selectors."""
import re
from pathlib import Path

CSS = Path("web/static/css/app.css")

# Los bordes que dibujan un control tienen que distinguirse del fondo: WCAG 1.4.11 pide 3:1.
CONTRASTE_MINIMO = 3.0
SUPERFICIES = ("--bg", "--bg-elev", "--bg-hover")
# Selectores cuyo borde es el contorno visible de un control.
CONTORNOS_DE_CONTROL = ("input, select, textarea", ".btn.secondary", ".nav-toggle", ".coach-module-option")
ESCALA_TEXTO = ("--text-xs", "--text-sm", "--text-base", "--text-lg", "--text-xl", "--text-2xl")
ESCALA_ESPACIO = ("--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6")


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


def _bloque(css: str, selector: str) -> str:
    """El cuerpo de la primera regla con ese selector exacto."""
    patron = re.compile(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", re.MULTILINE)
    encontrado = patron.search(css)
    assert encontrado, f"no existe la regla {selector}"
    return encontrado.group(1)


def _tokens(bloque: str) -> dict[str, str]:
    return {f"--{n}": v.strip() for n, v in re.findall(r"--([\w-]+):\s*([^;]+);", bloque)}


def _luminancia(hexa: str) -> float:
    canales = [int(hexa.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]


def _contraste(uno: str, otro: str) -> float:
    a, b = _luminancia(uno), _luminancia(otro)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_secondary_colors_live_in_tokens():
    root, rest = _root_and_rest(CSS.read_text())
    assert "--on-accent:" in root
    assert "--ok-text:" in root
    assert "#04101f" in root
    assert "#9be9a8" in root
    assert "#04101f" not in rest
    assert "#9be9a8" not in rest


def test_el_borde_de_un_control_se_ve_sobre_cualquier_fondo():
    css = CSS.read_text()
    for tema in (":root", '[data-theme="light"]'):
        tokens = _tokens(_bloque(css, tema))
        borde = tokens["--border-strong"]
        for superficie in SUPERFICIES:
            razon = _contraste(borde, tokens[superficie])
            assert razon >= CONTRASTE_MINIMO, f"{tema}: --border-strong sobre {superficie} da {razon:.2f}:1"


def test_los_controles_usan_el_borde_fuerte():
    css = CSS.read_text()
    for selector in CONTORNOS_DE_CONTROL:
        bloque = _bloque(css, selector)
        assert "var(--border-strong)" in bloque, f"{selector} dibuja su contorno con un borde decorativo"


def test_los_tamanos_de_texto_salen_de_la_escala():
    css = CSS.read_text()
    root, rest = _root_and_rest(css)
    for paso in ESCALA_TEXTO:
        assert f"{paso}:" in root, f"falta el paso {paso} en la escala"
        assert f"var({paso})" in rest, f"el paso {paso} no lo usa nadie"
    sueltos = [v for v in re.findall(r"font-size:\s*([^;}]+)", rest) if "var(--text-" not in v]
    # El texto dentro del SVG de la rueda escala con el viewBox, no con la escala tipográfica.
    assert sueltos == ["14px"], f"tamaños fuera de la escala: {sueltos}"


def test_los_espacios_salen_de_la_escala():
    root, rest = _root_and_rest(CSS.read_text())
    for paso in ESCALA_ESPACIO:
        assert f"{paso}:" in root, f"falta el paso {paso} en la escala"
        assert f"var({paso})" in rest, f"el paso {paso} no lo usa nadie"
