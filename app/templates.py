"""
templates.py — Plantillas de módulos Mission Dashboard

La IA del coach elige entre estas plantillas según el perfil del usuario.
"""
from __future__ import annotations

# Clave = id estable en user_modulos.modulo
MODULE_TEMPLATES: dict[str, dict] = {
    "agenda": {
        "nombre": "Agenda & Bitácora",
        "emoji": "📅",
        "page": "pages/01_Agenda.py",
        "descripcion": "Calendario semanal, bitácora y rachas.",
        "para_quien": "Quien quiere ordenar la semana y revisar avances.",
        "prioridad": 1,
    },
    "finanzas": {
        "nombre": "Finanzas (3 Sobres)",
        "emoji": "💰",
        "page": "pages/02_Finanzas.py",
        "descripcion": "Ingresos, gastos y sobres Supervivencia / Futuro / Ministerio.",
        "para_quien": "Controlar dinero, deudas, ahorro u ofrendas.",
        "prioridad": 2,
    },
    "deep_work": {
        "nombre": "Deep Work",
        "emoji": "⏱️",
        "page": "pages/03_Deep_Work.py",
        "descripcion": "Bloques de enfoque profundo y registro diario.",
        "para_quien": "Estudiar, programar o proyectos con horarios fijos.",
        "prioridad": 3,
    },
    "teologia": {
        "nombre": "Teología / Devocional",
        "emoji": "✝️",
        "page": "pages/04_Teologia.py",
        "descripcion": "Devocional diario y pedidos de oración.",
        "para_quien": "Vida espiritual, instituto bíblico, ministerio.",
        "prioridad": 2,
    },
    "biblioteca": {
        "nombre": "Biblioteca",
        "emoji": "📚",
        "page": "pages/05_Biblioteca.py",
        "descripcion": "Catálogo de libros, progreso y resaltados.",
        "para_quien": "Lectura constante o biblioteca personal.",
        "prioridad": 4,
    },
    "salud": {
        "nombre": "Salud & Energía",
        "emoji": "💪",
        "page": "pages/06_Salud.py",
        "descripcion": "Sueño, ejercicio, energía y Google Fit.",
        "para_quien": "Hábitos físicos, calistenia, sueño y productividad.",
        "prioridad": 3,
    },
    "sandbox": {
        "nombre": "Sandbox",
        "emoji": "🧪",
        "page": "pages/07_Sandbox.py",
        "descripcion": "Ideas, snippets y sesiones de experimentación.",
        "para_quien": "Proyectos creativos, código o experimentos.",
        "prioridad": 5,
    },
    "matrimonio": {
        "nombre": "Matrimonio / Pareja",
        "emoji": "💑",
        "page": "pages/08_Matrimonio.py",
        "descripcion": "Citas, notas y hábitos de conexión.",
        "para_quien": "Cuidar la relación de pareja o matrimonio.",
        "prioridad": 2,
    },
}

# Siempre accesibles (no se ocultan)
CORE_ALWAYS = {"usuarios"}  # página admin

COACH_SYSTEM = """Eres el Coach de Mission Dashboard, un sistema personal cristiano
de hábitos, estudio, finanzas y vida diaria.

Tu trabajo: elegir módulos (plantillas) para UNA persona según su relato.

Reglas:
- Responde SOLO JSON válido, sin markdown ni texto extra.
- Elige entre 3 y 6 módulos de la lista permitida.
- agenda casi siempre conviene si quiere organización semanal.
- No inventes claves fuera de la lista.
- Explica en 1 frase corta por módulo por qué lo elegiste.
- Propón 3 hábitos iniciales simples (clave corta sin espacios, label, emoji, hora opcional).

Formato exacto:
{
  "resumen": "1-2 oraciones motivadoras en español",
  "modulos": ["agenda", "finanzas"],
  "razones": {"agenda": "porque...", "finanzas": "porque..."},
  "habitos": [
    {"clave": "devocional", "label": "Devocional", "emoji": "📖", "hora": "05:45"}
  ]
}
"""


def catalogo_para_prompt() -> str:
    lineas = []
    for key, meta in MODULE_TEMPLATES.items():
        lineas.append(
            f"- {key}: {meta['nombre']} — {meta['descripcion']} "
            f"(ideal: {meta['para_quien']})"
        )
    return "\n".join(lineas)


def claves_validas() -> set[str]:
    return set(MODULE_TEMPLATES.keys())
