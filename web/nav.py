"""Information architecture — one sidebar entry per job, pages as hub tabs."""
from __future__ import annotations

from typing import Any

from fastapi import Request

from app.onboarding import (
    listar_modulos_usuario,
    modulo_activo,
    usuario_onboarding_completo,
)
from app.templates import MODULE_TEMPLATES

_HUB_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "hoy",
        "label": "Hoy",
        "group": "Día",
        "always": True,
        "exact": ("/app",),
        "also": ("/app/foco", "/app/ritual"),
    },
    {
        "id": "semana",
        "label": "Semana",
        "blurb": "Planificar la semana, bloques de enfoque y revisión del domingo.",
        "group": "Día",
        "always": True,
        "prefixes": ("/app/planificador", "/app/m/agenda", "/app/m/deep_work", "/app/revision", "/app/rueda"),
    },
    {
        "id": "dinero",
        "label": "Dinero",
        "group": "Áreas",
        "prefixes": ("/app/m/finanzas", "/app/presupuesto"),
        "modules": ("finanzas",),
    },
    {
        "id": "cuerpo",
        "label": "Cuerpo",
        "group": "Áreas",
        "prefixes": ("/app/m/salud",),
        "modules": ("salud",),
    },
    {
        "id": "espiritualidad",
        "label": "Espiritualidad",
        "group": "Áreas",
        "prefixes": ("/app/m/teologia",),
        "modules": ("teologia",),
    },
    {
        "id": "lectura",
        "label": "Lectura",
        "group": "Áreas",
        "prefixes": ("/app/m/biblioteca",),
        "modules": ("biblioteca",),
    },
    {
        "id": "relaciones",
        "label": "Relaciones",
        "group": "Áreas",
        "prefixes": ("/app/m/matrimonio",),
        "modules": ("matrimonio",),
    },
    {
        "id": "ideas",
        "label": "Ideas",
        "group": "Áreas",
        "prefixes": ("/app/m/sandbox",),
        "modules": ("sandbox",),
    },
    {
        "id": "alma",
        "label": "Alma",
        "group": "Sistema",
        "prefixes": ("/app/asistente",),
        "modules": ("alma",),
    },
    {
        "id": "cuenta",
        "label": "Cuenta",
        "group": "Sistema",
        "always": True,
        "prefixes": ("/app/coach", "/app/configuracion", "/app/usuarios", "/app/billing", "/app/familia"),
    },
)

_HUB_HREF = {
    "hoy": "/app",
    "semana": "/app/planificador",
    "dinero": "/app/m/finanzas",
    "cuerpo": "/app/m/salud",
    "espiritualidad": "/app/m/teologia",
    "lectura": "/app/m/biblioteca",
    "relaciones": "/app/m/matrimonio",
    "ideas": "/app/m/sandbox",
    "alma": "/app/asistente",
    "cuenta": "/app/coach",
}

# Hubs con tarjeta propia en Hoy.
_HUB_CARDS = ("semana", "dinero", "cuerpo", "espiritualidad", "lectura", "relaciones", "ideas")

GROUP_ORDER = ("Día", "Áreas", "Sistema")


def _activos(user_id: int) -> set[str]:
    rows = listar_modulos_usuario(user_id)
    activos = {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}
    for clave in ("ritual", "rueda", "alma"):
        if modulo_activo(clave, user_id):
            activos.add(clave)
        else:
            activos.discard(clave)
    return activos


def _area(hub: dict[str, Any]) -> dict | None:
    """El área que da nombre al hub, si el hub es exactamente un área."""
    mods = hub.get("modules") or ()
    if len(mods) == 1 and mods[0] in MODULE_TEMPLATES:
        return MODULE_TEMPLATES[mods[0]]
    return None


def _hub_label(hub: dict[str, Any]) -> str:
    area = _area(hub)
    return str(area["nombre"]) if area else hub["label"]


def _hub_blurb(hub: dict[str, Any]) -> str:
    area = _area(hub)
    return str(area["blurb"]) if area else str(hub.get("blurb") or "")


def _norm_path(path: str) -> str:
    p = (path or "/").rstrip("/")
    return p or "/"


def _matches(path: str, hub: dict[str, Any]) -> bool:
    p = _norm_path(path)
    if any(p == _norm_path(e) for e in hub.get("exact") or ()):
        return True
    for root in (*(hub.get("also") or ()), *(hub.get("prefixes") or ())):
        r = _norm_path(root)
        if p == r or p.startswith(r + "/"):
            return True
    return False


def _is_admin(user: dict) -> bool:
    return str(user.get("rol") or "").lower() == "admin"


def _visible(hub: dict[str, Any], activos: set[str], onboarded: bool) -> bool:
    if not onboarded:
        return hub["id"] == "cuenta"
    if hub.get("always"):
        return True
    return any(m in activos for m in hub.get("modules") or ())


def build_sidebar(user: dict, request: Request) -> list[dict]:
    uid = int(user["id"])
    activos = _activos(uid)
    onboarded = usuario_onboarding_completo(uid)
    path = request.url.path
    groups: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
    for hub in _HUB_SPECS:
        if not _visible(hub, activos, onboarded):
            continue
        groups[hub["group"]].append(
            {
                "id": hub["id"],
                "label": _hub_label(hub),
                "href": _HUB_HREF[hub["id"]],
                "active": _matches(path, hub),
            }
        )
    return [{"label": g, "links": groups[g]} for g in GROUP_ORDER if groups[g]]


def current_hub_id(path: str) -> str | None:
    for hub in _HUB_SPECS:
        if _matches(path, hub):
            return hub["id"]
    return None


def _tab(href: str, label: str, active: bool) -> dict:
    return {"href": href, "label": label, "active": active}


def hub_tabs(user: dict, request: Request) -> list[dict]:
    """Sibling links inside the current hub."""
    uid = int(user["id"])
    if not usuario_onboarding_completo(uid):
        return []
    activos = _activos(uid)
    path = request.url.path
    hub = current_hub_id(path)
    tabs: list[dict] = []
    if hub == "semana":
        tabs.append(_tab("/app/planificador", "Planificador", path.startswith("/app/planificador")))
        if "deep_work" in activos:
            tabs.append(
                _tab(
                    "/app/m/deep_work",
                    MODULE_TEMPLATES["deep_work"]["nombre"],
                    path.startswith("/app/m/deep_work"),
                )
            )
        tabs.append(_tab("/app/revision", "Revisión", path.startswith("/app/revision")))
    elif hub == "dinero":
        mes = request.query_params.get("mes") or request.session.get("fin_mes") or ""
        anio = request.query_params.get("anio") or request.session.get("fin_anio") or ""
        qs = f"?mes={mes}&anio={anio}" if mes and anio else ""
        tabs = [
            _tab(f"/app/m/finanzas{qs}", "Mes", _norm_path(path) == "/app/m/finanzas"),
            _tab(
                f"/app/m/finanzas/vencimientos{qs}",
                "Vencimientos",
                path.startswith("/app/m/finanzas/vencimientos"),
            ),
            _tab(
                f"/app/m/finanzas/precios{qs}",
                "Precios supermercados",
                path.startswith("/app/m/finanzas/precios"),
            ),
        ]
    elif hub == "cuenta":
        tabs = [
            _tab("/app/coach", "Mi sistema", path.startswith("/app/coach")),
            _tab("/app/configuracion", "Configuración", path.startswith("/app/configuracion")),
            _tab("/app/billing", "Plan y cobros", path.startswith("/app/billing")),
            _tab("/app/usuarios", "Telegram y usuarios", path.startswith("/app/usuarios")),
        ]
        if _is_admin(user):
            tabs.append(_tab("/app/familia", "Familia", path.startswith("/app/familia")))
    return tabs if len(tabs) >= 2 else []


def dashboard_hubs(user: dict) -> list[dict]:
    """Cards on Hoy: Semana plus each active life area, with child links."""
    uid = int(user["id"])
    activos = _activos(uid)
    if not usuario_onboarding_completo(uid):
        return []
    children: dict[str, list[dict]] = {
        "semana": [
            {"label": "Planificador", "href": "/app/planificador"},
            *(
                [{"label": MODULE_TEMPLATES["deep_work"]["nombre"], "href": "/app/m/deep_work"}]
                if "deep_work" in activos
                else []
            ),
            {"label": "Revisión", "href": "/app/revision"},
        ],
        "dinero": [
            {"label": "Mes", "href": "/app/m/finanzas"},
            {"label": "Vencimientos", "href": "/app/m/finanzas/vencimientos"},
            {"label": "Precios", "href": "/app/m/finanzas/precios"},
        ],
    }
    out = []
    for hub in _HUB_SPECS:
        if hub["id"] not in _HUB_CARDS or not _visible(hub, activos, True):
            continue
        out.append(
            {
                "id": hub["id"],
                "label": _hub_label(hub),
                "href": _HUB_HREF[hub["id"]],
                "descripcion": _hub_blurb(hub),
                "children": children.get(hub["id"], []),
                "activo": True,
            }
        )
    return out


def attach_nav(request: Request, ctx: dict) -> dict:
    user = ctx.get("user")
    if not user or ctx.get("hide_nav"):
        return ctx
    ctx.setdefault("nav_groups", build_sidebar(user, request))
    ctx.setdefault("hub_tabs", hub_tabs(user, request))
    return ctx
