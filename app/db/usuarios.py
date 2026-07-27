"""Usuarios / auth (PBKDF2) + campos de plan."""
from __future__ import annotations

import hashlib
import secrets as _secrets

from app.db.core import ejecutar


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if not salt:
        salt = _secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    )
    return digest.hex(), salt


def verificar_password(password: str, password_hash: str, salt: str) -> bool:
    candidato, _ = _hash_password(password, salt)
    return _secrets.compare_digest(candidato, password_hash)


def contar_usuarios() -> int:
    from app.logging_config import get_logger

    try:
        rows = ejecutar(
            "SELECT COUNT(*) AS n FROM usuarios WHERE activo = 1",
            fetchall=True,
        ) or []
        return int(rows[0]["n"]) if rows else 0
    except Exception as e:
        get_logger("database").exception("contar_usuarios falló: %s", e)
        return 0


def _ensure_plan_columns() -> None:
    try:
        from app.billing import ensure_billing_schema

        ensure_billing_schema()
    except Exception:
        for sql in (
            "ALTER TABLE usuarios ADD COLUMN plan TEXT DEFAULT 'free'",
            "ALTER TABLE usuarios ADD COLUMN plan_expira_en TEXT",
            "ALTER TABLE usuarios ADD COLUMN coach_ia_usado INTEGER DEFAULT 0",
        ):
            try:
                ejecutar(sql)
            except Exception:
                pass


def crear_usuario(
    username: str,
    password: str,
    rol: str = "admin",
    plan: str = "free",
) -> tuple[bool, str]:
    from app.security import username_valido

    _ensure_plan_columns()
    username = (username or "").strip().lower()
    if not username_valido(username):
        return False, "Usuario: 3–32 caracteres, solo a-z, 0-9 y _"
    if len(password or "") < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    if rol not in ("admin", "usuario"):
        rol = "usuario"
    plan = (plan or "free").strip().lower()
    if plan not in ("free", "premium", "familia"):
        plan = "free"
    existentes = ejecutar(
        "SELECT id FROM usuarios WHERE username = ?",
        [username],
        fetchall=True,
    ) or []
    if existentes:
        return False, "Ese nombre de usuario ya existe"
    password_hash, salt = _hash_password(password)
    try:
        ejecutar(
            """
            INSERT INTO usuarios
                (username, password_hash, salt, rol, activo, plan, coach_ia_usado)
            VALUES (?, ?, ?, ?, 1, ?, 0)
            """,
            [username, password_hash, salt, rol, plan],
        )
        try:
            from app.audit import registrar

            registrar(
                "crear_usuario",
                "usuarios",
                username,
                {"username": username, "rol": rol, "plan": plan},
            )
        except Exception:
            pass
        return True, "Usuario creado"
    except Exception as e:
        # Fallback si columnas plan aún no existen en BD vieja
        try:
            ejecutar(
                """
                INSERT INTO usuarios (username, password_hash, salt, rol, activo)
                VALUES (?, ?, ?, ?, 1)
                """,
                [username, password_hash, salt, rol],
            )
            return True, "Usuario creado"
        except Exception as e2:
            print(f"[auth] crear_usuario: {e} / {e2}")
            return False, "No se pudo crear el usuario"


def _row_usuario(u: dict) -> dict:
    return {
        "id": u["id"],
        "username": u["username"],
        "rol": u["rol"],
        "plan": (u.get("plan") or "free"),
        "plan_expira_en": u.get("plan_expira_en"),
        "coach_ia_usado": int(u.get("coach_ia_usado") or 0),
    }


def obtener_usuario_activo(user_id: int) -> dict | None:
    """Recarga perfil desde BD (sesión / desactivación / plan)."""
    _ensure_plan_columns()
    rows = ejecutar(
        """
        SELECT id, username, rol, activo, plan, plan_expira_en, coach_ia_usado
        FROM usuarios
        WHERE id = ? AND activo = 1
        """,
        [int(user_id)],
        fetchall=True,
    ) or []
    if not rows:
        # Fallback columnas antiguas
        rows = ejecutar(
            """
            SELECT id, username, rol, activo
            FROM usuarios
            WHERE id = ? AND activo = 1
            """,
            [int(user_id)],
            fetchall=True,
        ) or []
        if not rows:
            return None
        u = rows[0]
        return {
            "id": u["id"],
            "username": u["username"],
            "rol": u["rol"],
            "plan": "free",
            "plan_expira_en": None,
            "coach_ia_usado": 0,
        }
    return _row_usuario(rows[0])


def autenticar_usuario(username: str, password: str) -> dict | None:
    _ensure_plan_columns()
    username = (username or "").strip().lower()
    try:
        rows = ejecutar(
            """
            SELECT id, username, password_hash, salt, rol, activo,
                   plan, plan_expira_en, coach_ia_usado
            FROM usuarios
            WHERE username = ? AND activo = 1
            """,
            [username],
            fetchall=True,
        ) or []
    except Exception:
        rows = ejecutar(
            """
            SELECT id, username, password_hash, salt, rol, activo
            FROM usuarios
            WHERE username = ? AND activo = 1
            """,
            [username],
            fetchall=True,
        ) or []
    if not rows:
        return None
    u = rows[0]
    if not verificar_password(password, u["password_hash"], u["salt"]):
        return None
    return {
        "id": u["id"],
        "username": u["username"],
        "rol": u["rol"],
        "plan": u.get("plan") or "free",
        "plan_expira_en": u.get("plan_expira_en"),
        "coach_ia_usado": int(u.get("coach_ia_usado") or 0),
    }


def listar_usuarios() -> list:
    _ensure_plan_columns()
    try:
        return ejecutar(
            """
            SELECT id, username, rol, activo, creado_en,
                   plan, plan_expira_en, coach_ia_usado
            FROM usuarios
            ORDER BY id
            """,
            fetchall=True,
        ) or []
    except Exception:
        return ejecutar(
            """
            SELECT id, username, rol, activo, creado_en
            FROM usuarios
            ORDER BY id
            """,
            fetchall=True,
        ) or []
