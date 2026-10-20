"""Datos que el coach de rutina usa: peso, altura y objetivo."""
from __future__ import annotations

from app.logging_config import get_logger

log = get_logger("perfil_fisico")

SEXOS = ("", "mujer", "hombre", "otro")
OBJETIVOS = ("general", "fuerza", "bajar de peso", "resistencia", "movilidad")


def ensure_perfil_schema() -> None:
    from app.db.core import ejecutar

    try:
        ejecutar(
            """
            CREATE TABLE IF NOT EXISTS perfil_fisico (
                user_id INTEGER PRIMARY KEY,
                peso_kg REAL,
                altura_cm REAL,
                edad INTEGER,
                sexo TEXT,
                objetivo TEXT,
                notas TEXT,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception as e:
        log.warning("ensure_perfil_schema: %s", e)


def _num(valor, lo: float, hi: float) -> float | None:
    if valor is None or str(valor).strip() == "":
        return None
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if n < lo or n > hi:
        return None
    return n


def leer(user_id: int) -> dict:
    from app.db.core import ejecutar

    ensure_perfil_schema()
    rows = (
        ejecutar(
            """
            SELECT peso_kg, altura_cm, edad, sexo, objetivo, notas
            FROM perfil_fisico WHERE user_id = ?
            """,
            [int(user_id)],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return {
            "peso_kg": None,
            "altura_cm": None,
            "edad": None,
            "sexo": "",
            "objetivo": "general",
            "notas": "",
        }
    row = rows[0]
    sexo = str(row.get("sexo") or "")
    objetivo = str(row.get("objetivo") or "general")
    return {
        "peso_kg": row.get("peso_kg"),
        "altura_cm": row.get("altura_cm"),
        "edad": row.get("edad"),
        "sexo": sexo if sexo in SEXOS else "",
        "objetivo": objetivo if objetivo in OBJETIVOS else "general",
        "notas": str(row.get("notas") or ""),
    }


def guardar(
    user_id: int,
    *,
    peso_kg=None,
    altura_cm=None,
    edad=None,
    sexo: str = "",
    objetivo: str = "general",
    notas: str = "",
) -> tuple[bool, str]:
    from app.db.core import ejecutar

    ensure_perfil_schema()
    peso = _num(peso_kg, 30, 300)
    altura = _num(altura_cm, 120, 230)
    edad_n = _num(edad, 14, 90)
    if peso_kg not in (None, "") and peso is None:
        return False, "El peso tiene que estar entre 30 y 300 kg."
    if altura_cm not in (None, "") and altura is None:
        return False, "La altura tiene que estar entre 120 y 230 cm."
    if edad not in (None, "") and edad_n is None:
        return False, "La edad tiene que estar entre 14 y 90."
    sexo_n = sexo if sexo in SEXOS else ""
    objetivo_n = objetivo if objetivo in OBJETIVOS else "general"
    edad_i = int(edad_n) if edad_n is not None else None
    ejecutar(
        """
        INSERT INTO perfil_fisico
            (user_id, peso_kg, altura_cm, edad, sexo, objetivo, notas, actualizado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            peso_kg = excluded.peso_kg,
            altura_cm = excluded.altura_cm,
            edad = excluded.edad,
            sexo = excluded.sexo,
            objetivo = excluded.objetivo,
            notas = excluded.notas,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [
            int(user_id),
            peso,
            altura,
            edad_i,
            sexo_n,
            objetivo_n,
            (notas or "").strip()[:300],
        ],
    )
    return True, "Datos guardados. El coach los usa al armar la rutina."


def texto_para_coach(perfil: dict | None) -> str:
    if not perfil:
        return ""
    partes = []
    if perfil.get("peso_kg"):
        partes.append(f"peso {perfil['peso_kg']:g} kg")
    if perfil.get("altura_cm"):
        partes.append(f"altura {perfil['altura_cm']:g} cm")
    if perfil.get("edad"):
        partes.append(f"edad {int(perfil['edad'])}")
    if perfil.get("sexo"):
        partes.append(f"sexo {perfil['sexo']}")
    if perfil.get("objetivo") and perfil.get("objetivo") != "general":
        partes.append(f"objetivo {perfil['objetivo']}")
    if perfil.get("notas"):
        partes.append(f"notas físicas: {perfil['notas']}")
    if not partes:
        return ""
    return "Datos del usuario: " + "; ".join(partes) + "."
