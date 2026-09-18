"""Biblioteca de ejercicios: schema, validación de video, análisis y UI."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.exercises import (
    agregar_equipment,
    apply_analysis,
    crear_exercise,
    listar_equipment,
    listar_exercises,
    mark_failed,
    obtener_exercise,
)
from app.exercise_analysis import parse_analysis_payload
from app.exercise_uploads import VideoUploadError, looks_like_mp4_or_mov, save_exercise_video
from app.tenant import as_user


SAMPLE_ANALYSIS = {
    "nombre_ejercicio": "Swing con pesa rusa",
    "grupos_musculares_primarios": ["glúteos", "isquiotibiales"],
    "grupos_musculares_secundarios": ["core"],
    "equipamiento_detectado": ["pesa rusa"],
    "nivel_dificultad": "intermedio",
    "tipo_movimiento": "fuerza",
    "series_reps_mencionadas": None,
    "series_reps_sugeridas": "3×10-12",
    "cues_de_forma": ["Bisagra de cadera", "Caderas explosivas"],
    "duracion_estimada_segundos": None,
    "confianza_analisis": "alta",
}

VALID_JSON = json.dumps(SAMPLE_ANALYSIS, ensure_ascii=False)


def _ftyp_bytes(n: int = 2048) -> bytes:
    return b"\x00\x00\x00\x18ftypisom" + b"\x00" * n


@pytest.fixture()
def web_client(monkeypatch):
    import tempfile

    td = Path(tempfile.mkdtemp())
    db_path = td / "web_test.db"

    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.setenv("EXERCISE_STORAGE_DIR", str(td / "ex_uploads"))
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
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)

    from web.app import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client


def _setup_salud(client: TestClient, username: str = "ex_user") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "prueba",
            "objetivos": "ejercicio",
            "tiempo": "20",
            "notas": "",
            "areas": ["salud"],
        },
        follow_redirects=False,
    )
    client.post(
        "/app/coach/activar",
        data={"modulos": ["salud"]},
        follow_redirects=False,
    )


def test_schema_creates_exercise_tables(web_client):
    import app.db.core as core

    tables = {
        r["name"]
        for r in (core.ejecutar("SELECT name FROM sqlite_master WHERE type='table'", fetchall=True) or [])
    }
    assert "exercises" in tables
    assert "user_equipment" in tables
    cols = {
        r["name"]
        for r in (core.ejecutar("PRAGMA table_info(exercises)", fetchall=True) or [])
    }
    for needed in (
        "user_id",
        "source_video_url",
        "source_platform",
        "nombre_ejercicio",
        "grupos_musculares_primarios",
        "status",
        "creado_en",
        "actualizado_en",
    ):
        assert needed in cols


def test_parse_analysis_accepts_fenced_json_and_nulls():
    fenced = f"```json\n{VALID_JSON}\n```"
    parsed = parse_analysis_payload(fenced)
    assert parsed["nombre_ejercicio"] == "Swing con pesa rusa"
    assert parsed["series_reps_mencionadas"] is None
    assert parsed["nivel_dificultad"] == "intermedio"
    assert parsed["tipo_movimiento"] == "fuerza"


def test_parse_analysis_rejects_missing_name():
    bad = dict(SAMPLE_ANALYSIS, nombre_ejercicio="")
    with pytest.raises(Exception):
        parse_analysis_payload(json.dumps(bad))


def test_looks_like_mp4_magic():
    assert looks_like_mp4_or_mov(_ftyp_bytes())
    assert not looks_like_mp4_or_mov(b"RIFF....WEBM")
    assert not looks_like_mp4_or_mov(b"short")


def test_save_rejects_webm(tmp_path, monkeypatch):
    monkeypatch.setenv("EXERCISE_STORAGE_DIR", str(tmp_path))
    with pytest.raises(VideoUploadError):
        save_exercise_video(1, b"\x1aE\xdf\xa3" + b"\x00" * 200, "clip.webm", "video/webm")


def test_save_rejects_too_large(tmp_path, monkeypatch):
    monkeypatch.setenv("EXERCISE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("EXERCISE_VIDEO_MAX_MB", "0.001")
    with pytest.raises(VideoUploadError, match="MB"):
        save_exercise_video(1, _ftyp_bytes(4000), "clip.mp4", "video/mp4")


def test_salud_muestra_biblioteca_y_boton(web_client):
    _setup_salud(web_client)
    r = web_client.get("/app/m/salud")
    assert r.status_code == 200
    assert "Agregar ejercicio desde video".encode() in r.content
    assert b'href="/app/m/salud?tab=ejercicios"' in r.content

    r = web_client.get("/app/m/salud?tab=ejercicios")
    assert r.status_code == 200
    assert "Mis ejercicios".encode() in r.content
    assert b'accept="video/mp4,video/quicktime,.mp4,.mov"' in r.content
    assert b"capture=" not in r.content
    assert b"instagram" in r.content.lower() or b"Instagram" in r.content
    assert "Equipamiento disponible".encode() in r.content
    assert b"/app/m/salud/ejercicios/subir" in r.content


def test_upload_rejects_wrong_format(web_client):
    _setup_salud(web_client, "ex_badfmt")
    r = web_client.post(
        "/app/m/salud/ejercicios/subir",
        files={"video": ("clip.webm", BytesIO(b"not-a-video"), "video/webm")},
        data={"source_platform": "tiktok"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    loc = r.headers.get("location", "")
    assert "tab=ejercicios" in loc
    assert "error=" in loc


def test_upload_and_analysis_ready(web_client, monkeypatch):
    _setup_salud(web_client, "ex_ok")
    monkeypatch.setattr("app.exercise_uploads.probe_video_duration", lambda p: 12.0)

    def fake_run(eid, uid):
        apply_analysis(eid, uid, SAMPLE_ANALYSIS)

    monkeypatch.setattr("web.routers.ejercicios.run_exercise_analysis", fake_run)

    r = web_client.post(
        "/app/m/salud/ejercicios/subir",
        files={"video": ("swing.mp4", BytesIO(_ftyp_bytes()), "video/mp4")},
        data={"source_platform": "instagram"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Swing con pesa rusa".encode() in r.content
    assert "pesa rusa".encode() in r.content
    assert "gl".encode() in r.content  # glúteos
    assert b"source_video_url" not in r.content
    assert b"data/uploads" not in r.content

    rows = listar_exercises(1)
    assert len(rows) == 1
    assert rows[0]["status"] == "ready"
    assert rows[0]["source_platform"] == "instagram"
    assert rows[0]["nombre_ejercicio"] == "Swing con pesa rusa"


def test_processing_then_failed_retry(web_client, monkeypatch):
    _setup_salud(web_client, "ex_fail")
    monkeypatch.setattr("app.exercise_uploads.probe_video_duration", lambda p: 8.0)

    calls = {"n": 0}

    def fake_run(eid, uid):
        calls["n"] += 1
        if calls["n"] == 1:
            mark_failed(eid, uid, "JSON inválido de prueba")
        else:
            apply_analysis(eid, uid, SAMPLE_ANALYSIS)

    monkeypatch.setattr("web.routers.ejercicios.run_exercise_analysis", fake_run)

    r = web_client.post(
        "/app/m/salud/ejercicios/subir",
        files={"video": ("plank.mp4", BytesIO(_ftyp_bytes()), "video/mp4")},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Reintentar análisis".encode() in r.content
    assert "JSON inválido".encode() in r.content

    rows = listar_exercises(1)
    assert rows[0]["status"] == "failed"
    eid = rows[0]["id"]

    r = web_client.post(
        f"/app/m/salud/ejercicios/{eid}/reintentar",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Swing con pesa rusa".encode() in r.content
    assert obtener_exercise(eid, 1)["status"] == "ready"


def test_edit_exercise_and_detail(web_client, monkeypatch):
    _setup_salud(web_client, "ex_edit")
    monkeypatch.setattr("app.exercise_uploads.probe_video_duration", lambda p: 10.0)
    monkeypatch.setattr(
        "web.routers.ejercicios.run_exercise_analysis",
        lambda eid, uid: apply_analysis(eid, uid, SAMPLE_ANALYSIS),
    )
    web_client.post(
        "/app/m/salud/ejercicios/subir",
        files={"video": ("swing.mp4", BytesIO(_ftyp_bytes()), "video/mp4")},
        follow_redirects=True,
    )
    eid = listar_exercises(1)[0]["id"]

    r = web_client.get(f"/app/m/salud/ejercicios/{eid}")
    assert r.status_code == 200
    assert b'id="ex-name"' in r.content
    assert b'for="ex-name"' in r.content
    assert "Cues de forma".encode() in r.content
    assert b"/app/m/salud/ejercicios/" in r.content and b"/video" in r.content

    r = web_client.post(
        f"/app/m/salud/ejercicios/{eid}/editar",
        data={
            "nombre_ejercicio": "Swing ruso modificado",
            "grupos_musculares_primarios": "glúteos, espalda baja",
            "grupos_musculares_secundarios": "core",
            "equipamiento_detectado": "pesa rusa",
            "nivel_dificultad": "avanzado",
            "tipo_movimiento": "pliométrico",
            "series_reps_mencionadas": "4x12",
            "series_reps_sugeridas": "4×8-10",
            "cues_de_forma": "Pecho alto\nCierra glúteos arriba",
            "confianza_analisis": "media",
            "source_platform": "tiktok",
            "duracion_estimada_segundos": "",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Swing ruso modificado".encode() in r.content
    row = obtener_exercise(eid, 1)
    assert row["nivel_dificultad"] == "avanzado"
    assert row["tipo_movimiento"] == "pliométrico"
    assert "espalda baja" in row["grupos_musculares_primarios"]
    assert row["source_platform"] == "tiktok"


def test_user_isolation_and_equipment(web_client):
    _setup_salud(web_client, "ex_iso")
    with as_user({"id": 1, "username": "ex_iso"}):
        crear_exercise(1, "data/uploads/exercises/1/aaaa.mp4", "otro")
        apply_analysis(listar_exercises(1)[0]["id"], 1, SAMPLE_ANALYSIS)
        ok, _ = agregar_equipment(1, "banda elástica")
        assert ok

    from app.database import crear_usuario

    crear_usuario("otro_ex", "password1", rol="usuario")
    with as_user({"id": 2, "username": "otro_ex"}):
        assert listar_exercises(2) == []
        assert listar_equipment(2) == []
        assert obtener_exercise(listar_exercises(1)[0]["id"], 2) is None

    r = web_client.post(
        "/app/m/salud/equipamiento",
        data={"equipment_name": "pesa rusa"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "pesa rusa".encode() in r.content

    names = [e["equipment_name"] for e in listar_equipment(1)]
    assert "banda elástica" in names
    assert "pesa rusa" in names


def test_pipeline_marks_failed_on_bad_ai(web_client, monkeypatch, tmp_path):
    _setup_salud(web_client, "ex_pipe")
    from app.exercise_analysis import run_exercise_analysis

    monkeypatch.setattr("app.exercise_uploads.probe_video_duration", lambda p: 5.0)
    monkeypatch.setattr(
        "app.exercise_analysis.extract_keyframes",
        lambda video, dest, duration=None: [_write_jpg(dest)],
    )
    monkeypatch.setattr("app.exercise_analysis.extract_audio_wav", lambda v, d: None)
    monkeypatch.setattr("app.exercise_analysis.transcribe_audio", lambda p: "")
    monkeypatch.setattr(
        "app.exercise_analysis.complete_multimodal",
        lambda *a, **k: "esto no es json",
    )

    video = tmp_path / "clip.mp4"
    video.write_bytes(_ftyp_bytes())
    rel = f"data/uploads/exercises/1/{video.name}"
    # save into the configured storage dir used by the app
    from app.exercise_uploads import user_dir

    dest = user_dir(1) / video.name
    dest.write_bytes(_ftyp_bytes())
    rel = f"data/uploads/exercises/1/{dest.name}"
    eid = crear_exercise(1, rel, None)
    run_exercise_analysis(eid, 1)
    row = obtener_exercise(eid, 1)
    assert row["status"] == "failed"


def test_pipeline_surface_groq_vision_error(web_client, monkeypatch, tmp_path):
    _setup_salud(web_client, "ex_groq")
    from app.exercise_ai import ExerciseAIError
    from app.exercise_analysis import run_exercise_analysis

    monkeypatch.setattr("app.exercise_uploads.probe_video_duration", lambda p: 5.0)
    monkeypatch.setattr(
        "app.exercise_analysis.extract_keyframes",
        lambda video, dest, duration=None: [_write_jpg(dest)],
    )
    monkeypatch.setattr("app.exercise_analysis.extract_audio_wav", lambda v, d: None)
    monkeypatch.setattr("app.exercise_analysis.transcribe_audio", lambda p: "")

    def _boom(*a, **k):
        raise ExerciseAIError(
            "El modelo de visión «scout» no está disponible en Groq. "
            "Usa GROQ_VISION_MODEL=qwen/qwen3.6-27b."
        )

    monkeypatch.setattr("app.exercise_analysis.complete_multimodal", _boom)
    from app.exercise_uploads import user_dir

    dest = user_dir(1) / "clip.mp4"
    dest.write_bytes(_ftyp_bytes())
    rel = f"data/uploads/exercises/1/{dest.name}"
    eid = crear_exercise(1, rel, None)
    run_exercise_analysis(eid, 1)
    row = obtener_exercise(eid, 1)
    assert row["status"] == "failed"
    assert "visión" in (row.get("error_message") or "")
    assert "qwen" in (row.get("error_message") or "")


def _write_jpg(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    p = dest / "frame_001.jpg"
    p.write_bytes(b"\xff\xd8\xff\xd9")
    return p


def test_extract_keyframes_samples_short_clip(tmp_path):
    from app.ffmpeg_bin import resolve_ffmpeg

    clip = tmp_path / "clip.mp4"
    try:
        ffmpeg = resolve_ffmpeg()
    except FileNotFoundError:
        pytest.skip("ffmpeg no está instalado en este entorno")
    try:
        proc = __import__("subprocess").run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=160x120:d=4",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-t",
                "4",
                str(clip),
            ],
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.skip("ffmpeg no está instalado en este entorno")
    if proc.returncode != 0 or not clip.is_file():
        pytest.skip("ffmpeg/libx264 no disponible para generar el clip de prueba")
    from app.exercise_analysis import extract_keyframes

    frames = extract_keyframes(clip, tmp_path / "frames", duration=4.0)
    assert 1 <= len(frames) <= 10
    assert all(p.suffix == ".jpg" and p.is_file() for p in frames)


def test_duration_over_hard_max_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("EXERCISE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("EXERCISE_VIDEO_HARD_MAX_SECONDS", "90")
    monkeypatch.setattr("app.exercise_uploads.probe_video_duration", lambda p: 140.0)
    with pytest.raises(VideoUploadError, match="140"):
        save_exercise_video(1, _ftyp_bytes(), "long.mp4", "video/mp4")


def test_fail_stale_processing_reclaims_hung_jobs(web_client):
    from app.db.core import ejecutar
    from app.db.exercises import fail_stale_processing

    _setup_salud(web_client, "ex_stale")
    eid = crear_exercise(1, "data/uploads/exercises/1/gone.mp4", None)
    ejecutar(
        "UPDATE exercises SET actualizado_en = datetime('now', '-10 minutes') WHERE id = ?",
        [eid],
    )
    n = fail_stale_processing(1, older_than_s=120)
    assert n == 1
    row = obtener_exercise(eid, 1)
    assert row["status"] == "failed"
    assert "interrumpió" in (row.get("error_message") or "")


def test_missing_video_hides_retry_button(web_client):
    _setup_salud(web_client, "ex_miss")
    eid = crear_exercise(1, "data/uploads/exercises/1/gone.mp4", None)
    mark_failed(eid, 1, "No se encontró el video subido.")
    r = web_client.get("/app/m/salud?tab=ejercicios")
    assert r.status_code == 200
    assert "Sube el clip otra vez".encode() in r.content
    # El botón de reintentar no debe aparecer para este error
    assert r.content.count("Reintentar análisis".encode()) == 0
