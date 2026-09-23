"""Information architecture — grouped hubs instead of a flat page dump.

Duplicate surfaces (ritual/rueda/foco, coach/alma, familia, billing) stay reachable, but the sidebar only lists one entry per job.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request

from app.onboarding import listar_modulos_usuario, usuario_onboarding_completo
from app.templates import MODULE_TEMPLATES

# (id, sidebar label, path prefixes, related module keys, always visible)
_HUB_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "hoy",
        "label": "Hoy",
        "group": "Día",
        "always": True,
        "prefixes": (),
        "exact": ("/app",),
        "also": ("/app/foco", "/app/ritual"),
    },
    {
        "id": "guia",
        "label": "Guía",
        "group": "Día",
        "always": True,
        "prefixes": ("/app/asistente", "/app/coach"),
    },
    {
        "id": "semana",
        "label": "Semana",
        "group": "Día",
        "always": True,
        "prefixes": ("/app/planificador", "/app/m/agenda", "/app/m/deep_work", "/app/revision", "/app/rueda"),
        "modules": ("agenda", "deep_work"),
    },
    {
        "id": "dinero",
        "label": "Dinero",
        "group": "Vida",
        "prefixes": ("/app/m/finanzas", "/app/presupuesto"),
        "modules": ("finanzas",),
    },
    {
        "id": "hogar",
        "label": "Hogar",
        "group": "Vida",
        "prefixes": ("/app/m/matrimonio", "/app/familia"),
        "modules": ("matrimonio",),
        "admin": True,
    },
    {
        "id": "cuerpo",
        "label": "Cuerpo",
        "group": "Vida",
        "prefixes": ("/app/m/salud",),
        "modules": ("salud",),
    },
    {
        "id": "fe",
        "label": "Fe",
        "group": "Vida",
        "prefixes": ("/app/m/teologia",),
        "modules": ("teologia",),
    },
    {
        "id": "lectura",
        "label": "Lectura",
        "group": "Vida",
        "prefixes": ("/app/m/biblioteca",),
        "modules": ("biblioteca",),
    },
    {
        "id": "ideas",
        "label": "Ideas",
        "group": "Vida",
        "prefixes": ("/app/m/sandbox",),
        "modules": ("sandbox",),
    },
    {
        "id": "cuenta",
        "label": "Cuenta",
        "group": "Cuenta",
        "always": True,
        "prefixes": ("/app/usuarios", "/app/billing"),
    },
)

GROUP_ORDER = ("Día", "Vida", "Cuenta")


def modulos_nav(user_id: int) -> list[dict]:
    rows = listar_modulos_usuario(user_id)
    activos = {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}
    return [
        {
            **meta,
            "clave": key,
            "activo": key in activos,
            "href": f"/app/m/{key}",
        }
        for key, meta in MODULE_TEMPLATES.items()
    ]


def _activos(user_id: int) -> set[str]:
    rows = listar_modulos_usuario(user_id)
    return {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}


def _norm_path(path: str) -> str:
    p = (path or "/").rstrip("/")
    return p or "/"


def _matches(path: str, hub: dict[str, Any]) -> bool:
    p = _norm_path(path)
    for exact in hub.get("exact") or ():
        if p == _norm_path(exact):
            return True
    for also in hub.get("also") or ():
        if p == _norm_path(also) or p.startswith(_norm_path(also) + "/"):
            return True
    for pref in hub.get("prefixes") or ():
        root = _norm_path(pref)
        if p == root or p.startswith(root + "/"):
            return True
    return False


def _is_admin(user: dict) -> bool:
    return str(user.get("rol") or "").lower() == "admin"


def _hub_href(hub_id: str, user: dict, activos: set[str]) -> str:
    if hub_id == "hoy":
        return "/app"
    if hub_id == "guia":
        uid = int(user["id"])
        if usuario_onboarding_completo(uid):
            return "/app/asistente"
        return "/app/coach"
    if hub_id == "semana":
        return "/app/planificador"
    if hub_id == "dinero":
        return "/app/m/finanzas"
    if hub_id == "hogar":
        if "matrimonio" in activos:
            return "/app/m/matrimonio"
        return "/app/familia"
    if hub_id == "cuerpo":
        return "/app/m/salud"
    if hub_id == "fe":
        return "/app/m/teologia"
    if hub_id == "lectura":
        return "/app/m/biblioteca"
    if hub_id == "ideas":
        return "/app/m/sandbox"
    if hub_id == "cuenta":
        return "/app/usuarios"
    return "/app"


def _visible(hub: dict[str, Any], user: dict, activos: set[str], onboarded: bool) -> bool:
    if not onboarded:
        return hub["id"] in {"guia", "cuenta"}
    if hub.get("always"):
        return True
    mods = tuple(hub.get("modules") or ())
    if mods and any(m in activos for m in mods):
        return True
    if hub.get("admin") and _is_admin(user):
        return True
    return False


def build_sidebar(user: dict, request: Request) -> list[dict]:
    uid = int(user["id"])
    activos = _activos(uid)
    onboarded = usuario_onboarding_completo(uid)
    path = request.url.path
    groups: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
    for hub in _HUB_SPECS:
        if not _visible(hub, user, activos, onboarded):
            continue
        item = {
            "id": hub["id"],
            "label": hub["label"],
            "href": _hub_href(hub["id"], user, activos),
            "active": _matches(path, hub),
        }
        groups[hub["group"]].append(item)
    out = []
    for label in GROUP_ORDER:
        links = groups[label]
        if links:
            out.append({"label": label, "links": links})
    return out


def current_hub_id(path: str) -> str | None:
    p = _norm_path(path)
    for hub in _HUB_SPECS:
        if _matches(p, hub):
            return hub["id"]
    return None


def hub_tabs(user: dict, request: Request) -> list[dict]:
    """Sibling links inside the current hub."""
    uid = int(user["id"])
    activos = _activos(uid)
    if not usuario_onboarding_completo(uid):
        return []
    path = request.url.path
    hub = current_hub_id(path)
    tabs: list[dict] = []
    if hub == "guia":
        tabs = [
            {
                "href": "/app/asistente",
                "label": "Conversar",
                "active": path.startswith("/app/asistente"),
            },
            {
                "href": "/app/coach",
                "label": "Sistema",
                "active": path.startswith("/app/coach"),
            },
        ]
    elif hub == "semana":
        tabs = [
            {
                "href": "/app/planificador",
                "label": "Planificador",
                "active": path.startswith("/app/planificador"),
            },
        ]
        if "deep_work" in activos:
            tabs.append(
                {
                    "href": "/app/m/deep_work",
                    "label": "Enfoque",
                    "active": path.startswith("/app/m/deep_work"),
                }
            )
        tabs.append(
            {
                "href": "/app/revision",
                "label": "Revisión",
                "active": path.startswith("/app/revision"),
            }
        )
    elif hub == "dinero":
        mes = request.query_params.get("mes") or request.session.get("fin_mes") or ""
        anio = request.query_params.get("anio") or request.session.get("fin_anio") or ""
        qs = f"?mes={mes}&anio={anio}" if mes and anio else ""
        tabs = [
            {
                "href": f"/app/m/finanzas{qs}",
                "label": "Mes",
                "active": _norm_path(path) == "/app/m/finanzas",
            },
            {
                "href": f"/app/m/finanzas/vencimientos{qs}",
                "label": "Vencimientos",
                "active": path.startswith("/app/m/finanzas/vencimientos"),
            },
            {
                "href": f"/app/m/finanzas/precios{qs}",
                "label": "Precios supermercados",
                "active": path.startswith("/app/m/finanzas/precios"),
            },
        ]
    elif hub == "hogar":
        if "matrimonio" in activos:
            tabs.append(
                {
                    "href": "/app/m/matrimonio",
                    "label": "Pareja",
                    "active": path.startswith("/app/m/matrimonio"),
                }
            )
        if _is_admin(user):
            tabs.append(
                {
                    "href": "/app/familia",
                    "label": "Familia",
                    "active": path.startswith("/app/familia"),
                }
            )
    elif hub == "cuenta":
        tabs = [
            {
                "href": "/app/usuarios",
                "label": "Cuenta",
                "active": path.startswith("/app/usuarios"),
            },
            {
                "href": "/app/billing",
                "label": "Planes",
                "active": path.startswith("/app/billing"),
            },
        ]
    # Drop empty / single-tab bars (no siblings to jump to).
    if len(tabs) < 2:
        return []
    return tabs


def dashboard_hubs(user: dict) -> list[dict]:
    """Cards on Hoy: one per visible life area, with child links."""
    uid = int(user["id"])
    activos = _activos(uid)
    onboarded = usuario_onboarding_completo(uid)
    children = {
        "hoy": [],
        "guia": [
            {"label": "Alma", "href": "/app/asistente"},
            {"label": "Coach", "href": "/app/coach"},
        ],
        "semana": [
            {"label": "Planificador", "href": "/app/planificador"},
            {"label": "Revisión", "href": "/app/revision"},
        ],
        "dinero": [],
        "hogar": [],
        "cuerpo": [{"label": "Salud", "href": "/app/m/salud", "clave": "salud"}],
        "fe": [{"label": "Teología", "href": "/app/m/teologia", "clave": "teologia"}],
        "lectura": [{"label": "Biblioteca", "href": "/app/m/biblioteca", "clave": "biblioteca"}],
        "ideas": [{"label": "Sandbox", "href": "/app/m/sandbox", "clave": "sandbox"}],
        "cuenta": [
            {"label": "Usuarios", "href": "/app/usuarios"},
            {"label": "Planes", "href": "/app/billing"},
        ],
    }
    if "deep_work" in activos:
        children["semana"].append({"label": "Enfoque", "href": "/app/m/deep_work", "clave": "deep_work"})
    if "finanzas" in activos:
        children["dinero"] = [
            {"label": "Mes", "href": "/app/m/finanzas", "clave": "finanzas"},
            {"label": "Vencimientos", "href": "/app/m/finanzas/vencimientos", "clave": "finanzas"},
            {"label": "Precios", "href": "/app/m/finanzas/precios", "clave": "finanzas"},
        ]
    if "matrimonio" in activos:
        children["hogar"].append({"label": "Pareja", "href": "/app/m/matrimonio", "clave": "matrimonio"})
    if _is_admin(user):
        children["hogar"].append({"label": "Familia", "href": "/app/familia"})

    out = []
    for hub in _HUB_SPECS:
        if hub["id"] == "hoy":
            continue
        if not _visible(hub, user, activos, onboarded):
            continue
        kids = children.get(hub["id"]) or []
        if hub["id"] in {"cuerpo", "fe", "lectura", "ideas"} and not any(
            k.get("clave") in activos for k in kids if k.get("clave")
        ):
            continue
        if hub["id"] == "hogar" and not kids:
            continue
        out.append(
            {
                "id": hub["id"],
                "label": hub["label"],
                "href": _hub_href(hub["id"], user, activos),
                "descripcion": _HUB_BLURB.get(hub["id"], ""),
                "children": kids,
                "activo": True,
            }
        )
    return out


_HUB_BLURB = {
    "guia": "Alma para el día a día; el Coach arma el sistema.",
    "semana": "Planificar la semana, bloques de enfoque y revisión del domingo.",
    "dinero": "Ingreso repartido en sobres, vencimientos y precios.",
    "hogar": "Pareja y comparativa familiar.",
    "cuerpo": "Sueño, ejercicio y energía.",
    "fe": "Devocional y oración.",
    "lectura": "Libros, progreso y resaltados.",
    "ideas": "Proyectos, snippets y experimentos.",
    "cuenta": "Plan, Telegram y usuarios.",
}


def attach_nav(request: Request, ctx: dict) -> dict:
    user = ctx.get("user")
    if not user or ctx.get("hide_nav"):
        return ctx
    ctx.setdefault("nav_groups", build_sidebar(user, request))
    ctx.setdefault("hub_tabs", hub_tabs(user, request))
    ctx.setdefault("modulos_nav", modulos_nav(int(user["id"])))
    return ctx
