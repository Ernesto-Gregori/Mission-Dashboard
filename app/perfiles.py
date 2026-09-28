"""Plantillas de alta. Viven en código: sin elección no se siembra nada."""
from __future__ import annotations

PERFILES: tuple[dict, ...] = (
    {
        "id": "blanco",
        "nombre": "Empezar en blanco",
        "detalle": "Sin áreas ni hábitos. Hoy, Semana y Cuenta quedan listos.",
        "modulos": [],
        "habitos": [],
    },
    {
        "id": "diario",
        "nombre": "Día a día",
        "detalle": "Dinero, cuerpo y un hábito de movimiento.",
        "modulos": ["finanzas", "salud"],
        "habitos": [
            {"clave": "movimiento", "label": "Movimiento", "emoji": "🚶", "hora": ""},
        ],
    },
    {
        "id": "estudio",
        "nombre": "Estudio",
        "detalle": "Enfoque, lectura y un hábito para sentarte a leer.",
        "modulos": ["deep_work", "biblioteca"],
        "habitos": [
            {"clave": "lectura", "label": "Lectura", "emoji": "📚", "hora": ""},
        ],
    },
    {
        "id": "vinculos",
        "nombre": "Vínculos",
        "detalle": "Personas que quieres cuidar, con un hábito de conexión.",
        "modulos": ["matrimonio"],
        "habitos": [
            {"clave": "conexion", "label": "Conexión", "emoji": "💬", "hora": ""},
        ],
    },
    {
        "id": "practica",
        "nombre": "Práctica interior",
        "detalle": "Una práctica espiritual y el cuidado del cuerpo.",
        "modulos": ["teologia", "salud"],
        "habitos": [
            {"clave": "practica", "label": "Práctica", "emoji": "🕯️", "hora": ""},
        ],
    },
)

_POR_ID = {p["id"]: p for p in PERFILES}


def listar_perfiles() -> list[dict]:
    return [dict(p) for p in PERFILES]


def obtener_perfil(perfil_id: str) -> dict | None:
    p = _POR_ID.get((perfil_id or "").strip())
    return dict(p) if p else None
