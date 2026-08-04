"""Smoke tests — esqueleto FastAPI + HTMX + Coach."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "web_test.db"

    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.delenv("MISSION_WEB", raising=False)

    import app.db.core as core

    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setattr(core, "usar_turso", lambda: False)

    # Evitar llamadas reales a Groq en coach
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)

    from web.app import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client


def _setup_user(client: TestClient, username: str = "admin_web") -> None:
    r = client.post(
        "/setup",
        data={
            "username": username,
            "password": "password1",
            "password2": "password1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)


def test_health(web_client):
    r = web_client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["framework"] == "fastapi+htmx"


def test_setup_redirects_to_coach(web_client):
    r = web_client.get("/login", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/setup" in r.headers.get("location", "")

    _setup_user(web_client)

    # Sin onboarding → /app redirige a coach
    r = web_client.get("/app", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/app/coach" in r.headers.get("location", "")

    r = web_client.get("/app/coach")
    assert r.status_code == 200
    assert b"Coach" in r.content
    assert b"Cu" in r.content or b"llam" in r.content  # formulario perfil


def test_coach_flow_activa_modulos(web_client):
    _setup_user(web_client, "coach_user")

    r = web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "recien casado",
            "objetivos": "finanzas y pareja",
            "tiempo": "15-20 min",
            "notas": "",
            "areas": ["finanzas", "pareja"],
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "/app/coach" in r.headers.get("location", "")

    r = web_client.get("/app/coach")
    assert r.status_code == 200
    assert b"sistema propuesto" in r.content.lower() or b"Activar" in r.content

    # Activar agenda + finanzas + matrimonio (Free admin es premium en setup)
    r = web_client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "finanzas", "matrimonio"]},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "/app" in r.headers.get("location", "")

    r = web_client.get("/app")
    assert r.status_code == 200
    assert b"Control de mando" in r.content
    assert b"activo" in r.content
    assert b"badge stub" not in r.content and b">stub<" not in r.content

    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200
    assert b"Finanzas" in r.content
    assert b"Nuevo gasto" in r.content or b"ingreso" in r.content.lower()

    # Guardar ingreso + gasto
    r = web_client.post(
        "/app/m/finanzas/periodo",
        data={"mes": "7", "anio": "2026", "monto": "1000", "notas": "test"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)

    r = web_client.post(
        "/app/m/finanzas/gasto",
        data={
            "fecha": "2026-07-15",
            "sobre": "Supervivencia",
            "subcategoria": "Comida",
            "descripcion": "super",
            "monto": "50",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"super" in r.content


def test_secrets_reads_env(monkeypatch, tmp_path):
    from app import secrets as sec

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_from_env_12345678901234567890")
    sec.clear_secrets_cache()
    assert sec.get_secret("GROQ_API_KEY").startswith("gsk_test_from_env")

    from app.ai_client import api_key_configurada, _get_api_key

    assert _get_api_key().startswith("gsk_test")
    assert api_key_configurada() is True


def test_require_auth_redirect(web_client):
    r = web_client.get("/app", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")


def test_admin_setup_tiene_google_premium(web_client):
    """Setup crea admin premium → Salud muestra Conectar Google (no paywall Fit)."""
    _setup_user(web_client, "admin_prem")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "soltero",
            "objetivos": "todo",
            "tiempo": "20",
            "notas": "",
            "areas": ["salud", "agenda", "finanzas"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["salud", "agenda", "finanzas"]},
        follow_redirects=False,
    )
    r = web_client.get("/app/billing")
    assert r.status_code == 200
    assert b"Premium" in r.content or b"premium" in r.content.lower()

    r = web_client.get("/app/m/salud")
    assert r.status_code == 200
    # No debe exigir upgrade para Google si es admin/premium
    assert b"requiere plan Premium" not in r.content
    assert b"Conectar con Google" in r.content or b"Vinculado" in r.content or b"Google Fit" in r.content


def test_checkout_success_banner_y_refresh(web_client):
    """/?checkout=success y /app/billing?checkout=success muestran banner y limpian query."""
    _setup_user(web_client, "pay_banner")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "soltero",
            "objetivos": "premium",
            "tiempo": "20",
            "notas": "",
            "areas": ["finanzas"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["finanzas"]},
        follow_redirects=False,
    )

    # Retorno canónico FastAPI
    r = web_client.get(
        "/app/billing?checkout=success&plan=premium",
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert r.headers.get("location", "").startswith("/app/billing")
    assert "checkout=" not in r.headers.get("location", "")

    r = web_client.get("/app/billing")
    assert r.status_code == 200
    assert b"Pago recibido" in r.content
    # Admin setup es premium → mensaje con plan activo
    assert b"Plan activo" in r.content or b"Premium" in r.content

    # Cancel
    r = web_client.get("/app/billing?checkout=cancel", follow_redirects=False)
    assert r.status_code in (303, 307)
    r = web_client.get("/app/billing")
    assert r.status_code == 200
    assert b"Checkout cancelado" in r.content

    # Compat: /?checkout=success → billing
    r = web_client.get("/?checkout=success&plan=premium", follow_redirects=False)
    assert r.status_code in (303, 307)
    loc = r.headers.get("location", "")
    assert "/app/billing" in loc
    assert "checkout=success" in loc


def test_deep_work_dia_y_bloque(web_client):
    _setup_user(web_client, "dw_user")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "soltero",
            "objetivos": "enfoque",
            "tiempo": "30",
            "notas": "",
            "areas": ["deep_work"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["deep_work"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/m/deep_work")
    assert r.status_code == 200, r.text[:500]
    assert b"Deep Work" in r.content

    r = web_client.post(
        "/app/m/deep_work/bloque",
        data={
            "nombre": "Codigo manana",
            "hora_inicio": "06:15",
            "hora_fin": "08:00",
            "tipo": "Código",
            "color": "Azul",
            "dias": ["1", "2", "3", "4", "5", "6", "7"],
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Codigo manana" in r.content

    from app.timezone_config import hoy as _hoy

    fecha = str(_hoy())
    r = web_client.get(f"/app/m/deep_work?tab=dia&fecha={fecha}")
    assert r.status_code == 200
    assert b"Codigo manana" in r.content

    # Extraer bloque_id del HTML (hidden input)
    import re

    m = re.search(rb'name="bloque_id" value="(\d+)"', r.content)
    assert m, r.content[:800]
    bid = m.group(1).decode()

    r = web_client.post(
        "/app/m/deep_work/sesion",
        data={
            "fecha": fecha,
            "bloque_id": bid,
            "estado": "Completado",
            "notas": "pomodoro ok",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Completado" in r.content or b"pomodoro" in r.content

    r = web_client.get("/app/m/deep_work?tab=semana")
    assert r.status_code == 200
    assert b"Semana" in r.content


def test_teologia_devocional_y_pedido(web_client):
    _setup_user(web_client, "teo_user")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "casado",
            "objetivos": "fe",
            "tiempo": "20",
            "notas": "",
            "areas": ["teologia"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["teologia"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/m/teologia")
    assert r.status_code == 200, r.text[:500]
    assert b"Teolog" in r.content or b"Devocional" in r.content

    from app.timezone_config import hoy as _hoy

    fecha = str(_hoy())
    r = web_client.post(
        "/app/m/teologia/devocional",
        data={
            "fecha": fecha,
            "pasaje_referencia": "Juan 15:1-8",
            "version_biblia": "NVI",
            "pasaje_texto": "Yo soy la vid",
            "observacion": "vid y pámpanos",
            "interpretacion": "union con Cristo",
            "aplicacion": "permanecer en El",
            "conexion_instituto": "",
            "conexion_situacion": "",
            "oracion_escrita": "Senor ayudame",
            "duracion_minutos": "25",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Juan 15" in r.content

    r = web_client.get("/app/m/teologia?tab=historial")
    assert r.status_code == 200
    assert b"Juan 15" in r.content

    r = web_client.post(
        "/app/m/teologia/pedido",
        data={
            "titulo": "Sabiduria en decisiones",
            "descripcion": "trabajo y estudio",
            "categoria": "Personal",
            "urgencia": "3",
            "dias": ["1", "2", "3", "4", "5"],
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Sabiduria" in r.content


def test_matrimonio_cita_nota_habito(web_client):
    _setup_user(web_client, "mat_user")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "casado",
            "objetivos": "pareja",
            "tiempo": "20",
            "notas": "",
            "areas": ["pareja"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["matrimonio"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/m/matrimonio")
    assert r.status_code == 200, r.text[:500]
    assert b"Matrimonio" in r.content or b"Citas" in r.content

    from app.timezone_config import hoy as _hoy

    fecha = str(_hoy())
    r = web_client.post(
        "/app/m/matrimonio/cita",
        data={
            "fecha": fecha,
            "hora": "19:30",
            "ambito": "Matrimonio",
            "tipo_cita": "Cena_Romantica",
            "titulo": "Cena aniversario",
            "lugar": "Casa",
            "presupuesto": "40",
            "descripcion": "Velas y musica",
            "preparacion": "Comprar flores",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Cena aniversario" in r.content

    r = web_client.post(
        "/app/m/matrimonio/nota",
        data={
            "categoria": "Ideas_Regalo",
            "contenido": "Quiere un libro de poesia",
            "contexto": "Despues de la cena",
            "fecha_mencion": fecha,
            "urgencia": "3",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"poesia" in r.content

    r = web_client.get("/app/m/matrimonio?tab=habitos")
    assert r.status_code == 200

    r = web_client.post(
        "/app/m/matrimonio/habito",
        data={
            "fecha": fecha,
            "minutos": "45",
            "satisfaccion": "5",
            "tipo_conexion": "Cena",
            "iniciado_por": "Ambos",
            "notas": "Buen momento",
            "modo_pareja": "1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"45" in r.content or b"Cena" in r.content


def test_sandbox_idea_snippet_sesion(web_client):
    _setup_user(web_client, "sb_user")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "estudiante",
            "objetivos": "ideas y codigo",
            "tiempo": "20",
            "notas": "",
            "areas": ["ideas"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["sandbox"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/m/sandbox")
    assert r.status_code == 200, r.text[:500]
    assert b"Sandbox" in r.content or b"Ideas" in r.content

    from app.timezone_config import hoy as _hoy

    fecha = str(_hoy())
    r = web_client.post(
        "/app/m/sandbox/idea",
        data={
            "titulo": "API FastAPI demo",
            "descripcion": "Prototipo HTMX",
            "dominio": "Programacion",
            "categoria": "Web_App",
            "estado": "Investigando",
            "prioridad": "4",
            "motivacion": "8",
            "etiquetas": "htmx, fastapi",
            "notas": "MVP",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"API FastAPI demo" in r.content

    r = web_client.post(
        "/app/m/sandbox/snippet",
        data={
            "titulo": "Hello HTMX",
            "descripcion": "snippet base",
            "lenguaje": "Python",
            "codigo": "print('hola')",
            "tags": "demo",
            "dominio": "Programacion",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Hello HTMX" in r.content
    assert b"print" in r.content

    r = web_client.post(
        "/app/m/sandbox/sesion",
        data={
            "fecha": fecha,
            "duracion": "45",
            "satisfaccion": "8",
            "dominio": "Programacion",
            "tipo": "Codificando",
            "proyecto_id": "",
            "descripcion": "Port sandbox a HTMX",
            "codigo": "",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Port sandbox" in r.content or b"Codificando" in r.content

    r = web_client.get("/app/m/sandbox?tab=mentor")
    assert r.status_code == 200
    assert b"Mentor" in r.content


def test_usuarios_admin_crear_plan_backup(web_client):
    _setup_user(web_client, "usr_admin")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "admin",
            "objetivos": "gestion",
            "tiempo": "10",
            "notas": "",
            "areas": ["finanzas"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["finanzas"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/usuarios")
    assert r.status_code == 200, r.text[:500]
    assert b"Usuarios" in r.content or b"plan" in r.content.lower()
    assert b"/app/usuarios" in r.content or b"Gesti" in r.content

    r = web_client.get("/app/usuarios?tab=gestion")
    assert r.status_code == 200
    assert b"usr_admin" in r.content

    r = web_client.post(
        "/app/usuarios/crear",
        data={
            "username": "esposa_demo",
            "password": "password1",
            "password2": "password1",
            "rol": "usuario",
            "plan": "free",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"esposa_demo" in r.content

    # id del usuario creado
    from app.database import listar_usuarios

    rows = listar_usuarios()
    nuevo = next(u for u in rows if u["username"] == "esposa_demo")

    r = web_client.post(
        "/app/usuarios/plan",
        data={"user_id": str(nuevo["id"]), "plan": "premium", "expira": ""},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"premium" in r.content.lower() or b"Plan" in r.content

    r = web_client.get("/app/usuarios?tab=auditoria")
    assert r.status_code == 200

    r = web_client.post("/app/usuarios/backup", follow_redirects=True)
    assert r.status_code == 200
    assert b"Backup" in r.content or b"backup" in r.content


def test_biblioteca_catalogo_y_progreso(web_client):
    _setup_user(web_client, "bib_user")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "soltero",
            "objetivos": "lectura",
            "tiempo": "20",
            "notas": "",
            "areas": ["biblioteca"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["biblioteca"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/m/biblioteca")
    assert r.status_code == 200, r.text[:500]
    assert b"Biblioteca" in r.content

    r = web_client.post(
        "/app/m/biblioteca/nuevo",
        data={
            "titulo": "Proverbios para la vida",
            "autor": "Anonimo",
            "categoria": "Teologia",
            "total_paginas": "200",
            "descripcion": "sabiduria",
            "estado": "leyendo",
            "isbn": "",
            "editorial": "",
            "anio": "2020",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Proverbios" in r.content

    r = web_client.get("/app/m/biblioteca?tab=leyendo")
    assert r.status_code == 200
    assert b"Proverbios" in r.content

    import re

    m = re.search(rb'/biblioteca/libro/(\d+)/progreso', r.content)
    assert m, r.content[:600]
    lid = m.group(1).decode()
    r = web_client.post(
        f"/app/m/biblioteca/libro/{lid}/progreso",
        data={"pagina_actual": "40", "estado": "leyendo", "next_tab": "leyendo"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"40" in r.content


def test_tenant_uid_in_threadpool_via_finanzas(web_client):
    """
    Regresión: sync endpoint + uid() en threadpool (como uvicorn).
    Sin TenantMiddleware → RuntimeError: No hay usuario autenticado (uid).
    """
    _setup_user(web_client, "tenant_tp")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "soltero",
            "objetivos": "orden",
            "tiempo": "15",
            "notas": "",
            "areas": ["finanzas"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["finanzas"]},
        follow_redirects=False,
    )
    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200, r.text[:500]
    assert b"Finanzas" in r.content
    assert b"Internal Server Error" not in r.content
    assert b"No hay usuario autenticado" not in r.content


def test_agenda_calendario_y_bitacora(web_client):
    _setup_user(web_client, "agenda_user")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "casado",
            "objetivos": "orden semanal",
            "tiempo": "20",
            "notas": "",
            "areas": ["agenda", "finanzas"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "finanzas"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/m/agenda")
    assert r.status_code == 200, r.text[:500]
    assert b"Agenda" in r.content
    assert b"Calendario" in r.content
    assert b"Nuevo evento" in r.content

    r = web_client.post(
        "/app/m/agenda/evento",
        data={
            "fecha": "2026-07-28",
            "titulo": "Lectura test",
            "tipo": "Lectura",
            "hora_inicio": "19:30",
            "hora_fin": "20:30",
            "descripcion": "demo",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Lectura test" in r.content

    r = web_client.get("/app/m/agenda?tab=bitacora")
    assert r.status_code == 200
    assert b"Bit" in r.content or b"victorias" in r.content.lower()

    from app.db.agenda import obtener_lunes_semana
    from app.timezone_config import hoy as _hoy

    lun = obtener_lunes_semana(_hoy()).isoformat()
    r = web_client.post(
        "/app/m/agenda/bitacora",
        data={
            "semana_inicio": lun,
            "victoria_1": "Orar diario",
            "victoria_2": "Deep work",
            "victoria_3": "Cita",
            "ingreso_actual": "1000",
            "aporte_transicion": "50",
            "presupuesto_cita": "200",
            "semaforo_superv": "verde",
            "semaforo_ahorros": "amarillo",
            "semaforo_extras": "verde",
            "actividad_cita": "Cena",
            "costo_cita": "150",
            "libro_actual": "Proverbios",
            "pagina_actual": "10",
            "frase_favorita": "El temor de Jehova",
            "pendientes_soltar": "emails",
            "reflexion_semana": "Buena semana",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Orar diario" in r.content or b"guardada" in r.content.lower() or b"Bit" in r.content

    r = web_client.get("/app/m/agenda?tab=historial")
    assert r.status_code == 200
    assert b"Historial" in r.content
    assert lun.encode() in r.content or b"Orar" in r.content


def test_salud_registro_y_oauth_callback(web_client, monkeypatch):
    _setup_user(web_client, "salud_user")
    web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "soltero",
            "objetivos": "energia",
            "tiempo": "20",
            "notas": "",
            "areas": ["salud"],
        },
        follow_redirects=False,
    )
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["salud"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/m/salud")
    assert r.status_code == 200, r.text[:500]
    assert b"Salud" in r.content
    assert b"Registro" in r.content or b"sue" in r.content.lower()

    r = web_client.post(
        "/app/m/salud/guardar",
        data={
            "fecha": "2026-07-28",
            "horas_sueno": "7.5",
            "calidad_sueno": "8",
            "hora_dormir": "22:30",
            "hora_despertar": "05:30",
            "energia_manana": "8",
            "energia_tarde": "6",
            "energia_noche": "5",
            "hizo_ejercicio": "on",
            "tipo_ejercicio": "Calistenia",
            "duracion_minutos": "40",
            "intensidad": "7",
            "notas_ejercicio": "pullups",
            "zonas": ["Pecho", "Espalda"],
            "productividad_percibida": "8",
            "fuente_datos": "manual",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"pullups" in r.content or b"Calistenia" in r.content or b"7.5" in r.content

    r = web_client.get("/app/m/salud?tab=historial")
    assert r.status_code == 200
    assert b"2026-07-28" in r.content

    # Callback sin code/state → redirect error
    r = web_client.get("/oauth/google/callback", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "salud" in r.headers.get("location", "")

    # Callback con state inválido
    r = web_client.get(
        "/oauth/google/callback?code=fake&state=bad",
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    loc = r.headers.get("location", "")
    assert "google=err" in loc or "salud" in loc

    # Redirect URI desde APP_URL
    monkeypatch.setenv("APP_URL", "http://127.0.0.1:8000")
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    from app.google_fit import get_oauth_redirect_uri

    assert get_oauth_redirect_uri() == "http://127.0.0.1:8000/oauth/google/callback"


def test_coach_briefing_cruzado(web_client, monkeypatch):
    """Briefing en /app/coach: genera insights heurísticos y aparece en dashboard."""
    monkeypatch.setattr("app.coach_insights._llamar_llm_briefing", lambda signals: None)

    _setup_user(web_client, "briefing_admin")
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "finanzas", "deep_work"]},
        follow_redirects=False,
    )

    r = web_client.get("/app/coach")
    assert r.status_code == 200
    assert b"Briefing cruzado" in r.content

    r = web_client.post("/app/coach/briefing", follow_redirects=False)
    assert r.status_code in (303, 307)

    r = web_client.get("/app/coach")
    assert r.status_code == 200
    body = r.content.lower()
    assert b"briefing generado" in body or b"faltan datos" in body or b"periodo estable" in body
    assert b"cupo esta semana" in body

    r = web_client.get("/app")
    assert r.status_code == 200
    assert b"Del Coach" in r.content


def test_tenant_contextvar_copied_to_threadpool():
    """El ContextVar seteado en el hilo async se copia al threadpool (mecanismo)."""
    import asyncio

    from starlette.concurrency import run_in_threadpool

    from app.tenant import reset_current_user, set_current_user, uid

    async def _run():
        token = set_current_user({"id": 42, "username": "tp"})
        try:
            got = await run_in_threadpool(uid)
            assert got == 42
        finally:
            reset_current_user(token)

    asyncio.run(_run())
