"""URLs estáticas versionadas por contenido."""
from __future__ import annotations

import hashlib


def test_asset_hash_de_contenido():
    from web.deps import STATIC_DIR, asset

    esperado = hashlib.sha256((STATIC_DIR / "css/app.css").read_bytes()).hexdigest()[:10]
    assert asset("css/app.css") == f"/static/css/app.css?v={esperado}"
    assert asset("/css/app.css") == asset("css/app.css")
    assert asset("no/existe.css") == "/static/no/existe.css"


def test_asset_cambia_si_cambia_el_archivo(tmp_path, monkeypatch):
    import web.deps as deps

    monkeypatch.setattr(deps, "STATIC_DIR", tmp_path)
    monkeypatch.setattr(deps, "_asset_cache", {})
    f = tmp_path / "a.css"
    f.write_text("a{}")
    v1 = deps.asset("a.css")
    f.write_text("b{}")
    import os

    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 5))
    assert deps.asset("a.css") != v1


def test_base_html_usa_asset():
    from web.deps import TEMPLATES

    html = TEMPLATES.get_template("base.html").render(title="x")
    assert "/static/css/app.css?v=" in html
    assert "/static/js/htmx.min.js?v=" in html
