"""Fit y precios a la hora que elige cada persona. Corre en el proceso web."""
from __future__ import annotations

import logging
import threading

from app.timezone_config import ahora, hoy, iso_ahora

log = logging.getLogger("mission.nightly")

_precio_lock = threading.Lock()
_fit_lock = threading.Lock()


def _usuarios_activos() -> list[dict]:
    from app.db.core import ejecutar
    from app.db.usuarios import obtener_usuario_activo

    rows = (
        ejecutar(
            "SELECT id FROM usuarios WHERE COALESCE(activo, 1) = 1",
            fetchall=True,
        )
        or []
    )
    usuarios = []
    for row in rows:
        user = obtener_usuario_activo(int(row["id"]))
        if user:
            usuarios.append(user)
    return usuarios


def importar_fit_vencidos(momento=None) -> int:
    """Importa el día de hoy para quien está en la ventana y aún no corrió."""
    momento = momento or ahora()
    if not _fit_lock.acquire(blocking=False):
        return 0
    try:
        return _importar_fit(momento)
    finally:
        _fit_lock.release()


def _importar_fit(momento) -> int:
    from app.fit_import import importar_dia
    from app.sync_horario import en_ventana, leer, marcar
    from app.tenant import reset_current_user, set_current_user

    hechos = 0
    for user in _usuarios_activos():
        uid = int(user["id"])
        prefs = leer(uid)
        if not prefs["fit_activo"]:
            continue
        if not en_ventana(prefs["hora_fit"], momento, prefs.get("ultimo_fit")):
            continue
        token = set_current_user(user)
        try:
            ok, msg = importar_dia(hoy())
            if ok:
                marcar(uid, "ultimo_fit", iso_ahora())
                hechos += 1
            else:
                log.info("fit nocturno user=%s omitido: %s", uid, msg)
        except Exception:
            log.exception("fit nocturno user=%s", uid)
        finally:
            reset_current_user(token)
    return hechos


def _alguien_pide_precios(momento) -> bool:
    from app.sync_horario import en_ventana, leer

    usuarios = _usuarios_activos()
    if not usuarios:
        return False
    for user in usuarios:
        prefs = leer(int(user["id"]))
        if not prefs["precios_activo"]:
            continue
        if en_ventana(prefs["hora_precios"], momento, None):
            return True
    return False


def _precios_ya_hoy(momento) -> bool:
    from app.sync_horario import leer

    marca = leer(0).get("ultimo_precios")
    if not marca:
        return False
    return str(marca)[:10] == momento.date().isoformat()


def actualizar_precios_si_toca(momento=None) -> bool:
    """Un solo catálogo compartido. Corre una vez al día, en la ventana de alguien."""
    from app.scrapers import SCRAPERS, run_scraper
    from app.sync_horario import marcar

    momento = momento or ahora()
    if not _precio_lock.acquire(blocking=False):
        return False
    try:
        if _precios_ya_hoy(momento) or not _alguien_pide_precios(momento):
            return False
        for key in SCRAPERS:
            try:
                run_scraper(key)
            except Exception:
                log.exception("precios nocturnos %s", key)
        marcar(0, "ultimo_precios", iso_ahora())
        return True
    finally:
        _precio_lock.release()


def run_nightly_jobs_once() -> tuple[int, bool]:
    fit = importar_fit_vencidos()
    precios = actualizar_precios_si_toca()
    if fit or precios:
        log.info("nightly fit=%s precios=%s", fit, precios)
    return fit, precios
