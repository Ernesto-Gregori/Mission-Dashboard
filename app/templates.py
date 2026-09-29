"""
templates.py — Plantillas de módulos Mission Dashboard

La IA del coach elige entre estas plantillas según el perfil del usuario.
"""
from __future__ import annotations

# Clave = id estable en user_modulos.modulo. No se renombra.
# nombre = el único nombre del área: menú, título de página y catálogo del Coach.
MODULE_TEMPLATES: dict[str, dict] = {
    "agenda": {
        "nombre": "Revisión semanal",
        "blurb": "Planificar la semana, bloques de enfoque y revisión del domingo.",
        "emoji": "📋",
        "page": "pages/01_Agenda.py",
        "descripcion": "Bitácora de la semana (victorias y reflexión) con tus datos ya calculados.",
        "para_quien": "Quien quiere ordenar la semana y revisar avances.",
        "prioridad": 1,
    },
    "finanzas": {
        "nombre": "Dinero",
        "blurb": "Ingreso, gastos y vencimientos.",
        "emoji": "💰",
        "page": "pages/02_Finanzas.py",
        "descripcion": "Ingreso, gastos, vencimientos y un reparto si quieres usarlo.",
        "para_quien": "Controlar dinero, deudas o ahorro.",
        "prioridad": 2,
    },
    "deep_work": {
        "nombre": "Enfoque",
        "blurb": "Bloques de trabajo concentrado.",
        "emoji": "⏱️",
        "page": "pages/03_Deep_Work.py",
        "descripcion": "Bloques de enfoque profundo y registro diario.",
        "para_quien": "Estudiar, trabajar o proyectos con horarios fijos.",
        "prioridad": 3,
    },
    "teologia": {
        "nombre": "Espiritualidad",
        "blurb": "Una práctica para cuidar lo que te sostiene.",
        "emoji": "✝️",
        "page": "pages/04_Teologia.py",
        "descripcion": "Práctica espiritual, lectura y pedidos.",
        "para_quien": "Quien quiere un espacio de fe o crecimiento interior.",
        "prioridad": 2,
    },
    "biblioteca": {
        "nombre": "Lectura",
        "blurb": "Libros, progreso y resaltados.",
        "emoji": "📚",
        "page": "pages/05_Biblioteca.py",
        "descripcion": "Catálogo de libros, progreso y resaltados.",
        "para_quien": "Lectura constante o biblioteca personal.",
        "prioridad": 4,
    },
    "salud": {
        "nombre": "Cuerpo",
        "blurb": "Sueño, ejercicio y energía.",
        "emoji": "💪",
        "page": "pages/06_Salud.py",
        "descripcion": "Sueño, ejercicio, energía y Google Fit si quieres conectarlo.",
        "para_quien": "Quien quiere registrar el cuerpo sin obligación de entrenar.",
        "prioridad": 3,
    },
    "matrimonio": {
        "nombre": "Relaciones",
        "blurb": "Personas que quieres cuidar: pareja, familia o amigos.",
        "emoji": "💑",
        "page": "pages/08_Matrimonio.py",
        "descripcion": "Citas, notas y hábitos de conexión, sin asumir un estado civil.",
        "para_quien": "Cuidar una relación de pareja, familia o amistad.",
        "prioridad": 2,
    },
}

# Superficies del día. No entran al catálogo del Coach en esta fase.
# Si no hay fila, siguen activas para no cambiar la app de quien ya entra.
SUPERFICIES = ("ritual", "rueda", "alma")

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
