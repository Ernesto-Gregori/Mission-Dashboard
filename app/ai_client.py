"""
ai_client.py - Integración con Groq — compatible Streamlit Cloud
Fixes:
  1. Lee GROQ_API_KEY desde st.secrets (producción) con fallback a .env (local)
  2. Estado en memoria (no filesystem) — Streamlit Cloud es efímero
  3. verificar_conexion() sin llamada real a la API
  4. client inicializado lazy para no fallar en import
"""

import os
import time
import json
from typing import Optional, Dict, List
from datetime import datetime, date
from pathlib import Path

# ── Dotenv solo en local ──────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════════
# LEER API KEY — st.secrets (Cloud) con fallback a .env (local)
# ═══════════════════════════════════════════════════════════════

def _get_api_key() -> str:
    """
    Orden de prioridad:
      1. st.secrets / env / .streamlit/secrets.toml  ← app.secrets
    """
    from app.secrets import get_secret

    return get_secret("GROQ_API_KEY", "")


MODELO = "llama-3.3-70b-versatile"

# ═══════════════════════════════════════════════════════════════
# ESTADO EN MEMORIA — no depende del filesystem
# (Streamlit Cloud resetea el disco en cada redeployment)
# ═══════════════════════════════════════════════════════════════

_estado = {
    "llamadas_hoy":    0,
    "fecha_contador":  date.today(),
    "conexion_ok":     None,   # None = no verificado aún
    "conexion_ts":     0.0,
    "conexion_ttl":    600,    # 10 min de cache
    "bloqueado_hasta": 0.0,
}

_MAX_LLAMADAS_DIA = 400

# ═══════════════════════════════════════════════════════════════
# CLIENT LAZY — se inicializa la primera vez que se necesita
# ═══════════════════════════════════════════════════════════════

_client = None

def _get_client():
    """Retorna el cliente Groq, inicializándolo si es necesario."""
    global _client
    if _client is not None:
        return _client

    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        from groq import Groq
        _client = Groq(api_key=api_key)
        return _client
    except Exception as e:
        print(f"[AI] Error inicializando Groq: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ═══════════════════════════════════════════════════════════════

def _reiniciar_si_nuevo_dia():
    hoy = date.today()
    if _estado["fecha_contador"] != hoy:
        _estado["llamadas_hoy"]    = 0
        _estado["fecha_contador"]  = hoy
        _estado["bloqueado_hasta"] = 0.0
        _estado["conexion_ok"]     = None

def _hay_cuota() -> bool:
    _reiniciar_si_nuevo_dia()
    if time.time() < _estado["bloqueado_hasta"]:
        return False
    return _estado["llamadas_hoy"] < _MAX_LLAMADAS_DIA

def _registrar_llamada():
    _estado["llamadas_hoy"] += 1

def _registrar_error_429(delay: int = 65):
    _estado["bloqueado_hasta"] = time.time() + delay
    _estado["conexion_ok"]     = False
    print(f"[AI] Rate limit. Bloqueado {delay}s.")

def _llamar_ai(
    prompt: str,
    system: str = "",
    max_tokens: int = 500,
) -> Optional[str]:
    """Llama a Groq. Retorna texto o None si falla."""
    if not _hay_cuota():
        return None

    # Cuota por plan (Free: techo mensual en uso_ia)
    try:
        from app.billing import cuota_ia_ok, registrar_llamada_ia

        if not cuota_ia_ok():
            print("[AI] Cuota de plan agotada este mes")
            return None
    except Exception:
        pass

    client = _get_client()
    if not client:
        return None

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=MODELO,
            messages=messages,
            max_tokens=max_tokens,
        )
        _registrar_llamada()
        try:
            from app.billing import registrar_llamada_ia

            registrar_llamada_ia()
        except Exception:
            pass
        # Marcar conexión como ok al primer éxito
        _estado["conexion_ok"] = True
        _estado["conexion_ts"] = time.time()
        return response.choices[0].message.content

    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower():
            _registrar_error_429(65)
        else:
            # Otro error de red / auth — no bloquear indefinidamente
            _estado["conexion_ok"] = False
            _estado["conexion_ts"] = time.time()
        print(f"[AI] Error: {err[:120]}")
        return None

# ═══════════════════════════════════════════════════════════════
# API PÚBLICA
# ═══════════════════════════════════════════════════════════════

def api_key_configurada() -> bool:
    key = _get_api_key()
    return bool(key) and len(key) > 20

def verificar_conexion(forzar: bool = False) -> bool:
    """
    Verifica si la API key está configurada y el cliente se puede crear.
    NO hace una llamada real a la API — evita loop de verificación.
    La conexión real se confirma en el primer chat_simple() exitoso.
    """
    if not api_key_configurada():
        return False

    ahora         = time.time()
    cache_vigente = (ahora - _estado["conexion_ts"]) < _estado["conexion_ttl"]

    # Si ya tenemos un resultado cacheado y no forzamos, usarlo
    if not forzar and _estado["conexion_ok"] is not None and cache_vigente:
        return _estado["conexion_ok"]

    # Verificación ligera: ¿el cliente se puede crear?
    client = _get_client()
    resultado = client is not None

    _estado["conexion_ok"] = resultado
    _estado["conexion_ts"] = ahora
    return resultado

def estado_gemini() -> Dict:
    """Mantiene el nombre original para no cambiar main.py."""
    _reiniciar_si_nuevo_dia()

    bloqueado = time.time() < _estado["bloqueado_hasta"]
    sin_cuota = _estado["llamadas_hoy"] >= _MAX_LLAMADAS_DIA
    key_ok    = api_key_configurada()

    # conexion_ok None significa "no verificado" — asumimos True si hay key
    conexion_real = _estado["conexion_ok"]
    conectado = key_ok and not bloqueado and not sin_cuota and (
        conexion_real is not False  # None o True → consideramos conectado
    )

    if not key_ok:
        modo = "offline_sin_key"
    elif bloqueado:
        modo = "offline_rate_limited"
    elif sin_cuota:
        modo = "offline_sin_cuota"
    elif conectado:
        modo = "online"
    else:
        modo = "offline_sin_verificar"

    return {
        "api_key_configurada": key_ok,
        "conectado":           conectado,
        "llamadas_hoy":        _estado["llamadas_hoy"],
        "max_llamadas":        _MAX_LLAMADAS_DIA,
        "restantes":           max(0, _MAX_LLAMADAS_DIA - _estado["llamadas_hoy"]),
        "modo":                modo,
    }

# ═══════════════════════════════════════════════════════════════
# FALLBACKS
# ═══════════════════════════════════════════════════════════════

FALLBACKS = {
    "resumen_semanal":        "🌟 Modo offline activo. Revisa tus hábitos manualmente hoy.",
    "alerta_matrimonio":      "⏰ Son las 20:30. Guarda las pantallas — tiempo sagrado en 30 min. 💑",
    "analisis_salud":         "📊 Sigue registrando para ver patrones. Prioriza 7+ horas de sueño.",
    "chat_bienvenida":        "🤖 Sin respuesta de la IA. Verifica la API key en Secrets.",
    "sugerencia_devocional":  "📖 Salmo 119:9-16 — ¿Cómo guardas tus caminos hoy?",
}

def _fallback(tipo: str) -> str:
    return FALLBACKS.get(tipo, "🤖 Modo offline activo.")

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE NEGOCIO
# ═══════════════════════════════════════════════════════════════

SYSTEM_MISION = (
    "Eres la Secretaria IA de Mission Dashboard, asistente personal cristiano "
    "para teología, programación, finanzas y matrimonio. "
    "Responde en español, de forma breve y práctica."
)

def chat_simple(mensaje: str, contexto: str = "") -> str:
    """
    Chat con Groq.
    `contexto` = system prompt del módulo (Finanzas, Salud, Agenda, etc.).
    Si viene vacío, usa SYSTEM_MISION.
    """
    system = (contexto or "").strip() or SYSTEM_MISION
    resultado = _llamar_ai(mensaje, system=system)
    return resultado or _fallback("chat_bienvenida")


def probar_groq() -> dict:
    """Diagnóstico rápido de GROQ_API_KEY + una llamada mínima."""
    info = {
        "api_key_configurada": api_key_configurada(),
        "modelo": MODELO,
        "ok": False,
        "mensaje": "",
    }
    if not info["api_key_configurada"]:
        info["mensaje"] = "Falta GROQ_API_KEY en secrets o .env"
        return info
    resp = _llamar_ai(
        "Responde solo: OK",
        system="Eres un checker. Responde exactamente OK.",
        max_tokens=8,
    )
    if resp and "OK" in resp.upper():
        info["ok"] = True
        info["mensaje"] = f"Groq responde ({MODELO})"
    elif resp:
        info["ok"] = True
        info["mensaje"] = f"Groq respondió: {resp[:80]}"
    else:
        info["mensaje"] = "No hubo respuesta (cuota, red o clave inválida)"
    return info

def generar_resumen_semanal(*args, **kwargs) -> str:
    resultado = _llamar_ai(
        "Genera un resumen motivacional semanal. Incluye: victorias posibles, "
        "área de mejora y un versículo bíblico. Máximo 200 palabras. Usa markdown.",
        system=SYSTEM_MISION,
    )
    return resultado or _fallback("resumen_semanal")

def generar_alerta_matrimonio(contexto: str = "") -> str:
    resultado = _llamar_ai(
        "Genera una alerta cariñosa para las 20:30 recordando preparar tiempo "
        "en pareja a las 21:00. Breve y con una acción concreta.",
        system=SYSTEM_MISION,
    )
    return resultado or _fallback("alerta_matrimonio")

def analizar_patron_salud(registros: List[Dict]) -> str:
    if len(registros) < 4:
        return "Datos insuficientes. Sigue registrando tu rutina."
    resultado = _llamar_ai(
        f"Analiza correlación ejercicio-productividad: {json.dumps(registros[:5])}. "
        "Máximo 3 oraciones.",
        system=SYSTEM_MISION,
    )
    return resultado or _fallback("analisis_salud")

def sugerir_lectura_devocional(tema: str = "", pasaje: str = "") -> str:
    resultado = _llamar_ai(
        f"Sugiere un pasaje bíblico relacionado con: '{tema}'. "
        "Incluye referencia y una pregunta de reflexión. Máximo 100 palabras.",
        system=SYSTEM_MISION,
    )
    return resultado or _fallback("sugerencia_devocional")

def extraer_metadatos_libro(contenido_pdf: bytes, nombre_archivo: str) -> Dict:
    """Extrae metadatos reales del PDF usando pdfplumber + Groq."""
    texto_extraido   = ""
    total_paginas_real = 0

    try:
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(contenido_pdf)) as pdf:
            total_paginas_real = len(pdf.pages)
            partes = []
            for i in range(min(5, total_paginas_real)):
                texto = pdf.pages[i].extract_text()
                if texto:
                    partes.append(texto.strip())
            texto_extraido = "\n\n".join(partes)
        print(f"[PDF] {min(5, total_paginas_real)} páginas, {len(texto_extraido)} chars")
    except Exception as e:
        print(f"[PDF] Error extrayendo texto: {e}")

    texto_para_ia = texto_extraido[:3000] if texto_extraido else f"Nombre del archivo: {nombre_archivo}"

    prompt = f"""Analiza este libro y extrae sus metadatos.

TEXTO DEL LIBRO (primeras páginas):
{texto_para_ia}

Nombre del archivo: {nombre_archivo}

Responde ÚNICAMENTE con JSON válido, sin markdown ni explicaciones:
{{
    "titulo": "título exacto del libro",
    "autor": "nombre completo del autor principal",
    "categoria_principal": "una de: Teologia/Programacion/Matrimonio/Filosofia/Liderazgo/Historia/Otros",
    "descripcion": "resumen del libro en 2-3 oraciones basado en el contenido real",
    "editorial": "editorial si aparece, sino null",
    "anio_publicacion": "año como número si aparece sino null",
    "total_paginas": {total_paginas_real if total_paginas_real > 0 else "null"},
    "temas_clave": ["tema1", "tema2", "tema3"],
    "confianza_extraccion": "número del 1 al 10"
}}"""

    resultado = _llamar_ai(prompt)

    if resultado:
        try:
            texto_limpio = resultado.strip()
            if "```" in texto_limpio:
                texto_limpio = texto_limpio.split("```")[1]
                if texto_limpio.startswith("json"):
                    texto_limpio = texto_limpio[4:]

            metadatos = json.loads(texto_limpio.strip())
            metadatos.setdefault("titulo", nombre_archivo.replace(".pdf", "").replace("_", " ").title())
            metadatos.setdefault("autor", "Desconocido")
            metadatos.setdefault("categoria_principal", "Otros")
            metadatos.setdefault("descripcion", "Sin descripción")
            metadatos.setdefault("temas_clave", [])
            metadatos["fuente_metadatos"]  = "IA"
            metadatos["fecha_extraccion"]  = datetime.now().isoformat()
            if total_paginas_real > 0:
                metadatos["total_paginas"] = total_paginas_real
            return metadatos

        except json.JSONDecodeError as e:
            print(f"[AI] Error parseando JSON: {e} | resp: {resultado[:200]}")

    return {
        "titulo":               nombre_archivo.replace(".pdf", "").replace("_", " ").title(),
        "autor":                "Desconocido",
        "categoria_principal":  "Otros",
        "descripcion":          "No se pudo extraer descripción automáticamente.",
        "total_paginas":        total_paginas_real,
        "temas_clave":          [],
        "confianza_extraccion": 1,
        "fuente_metadatos":     "IA",
    }

def buscar_metadatos_isbn(isbn: str) -> dict:
    """Busca metadatos por ISBN: Open Library → Google Books → Groq."""
    import re
    import requests

    metadatos   = {}
    isbn_limpio = isbn.replace("-", "").replace(" ", "").strip()

    # ── 1. Open Library ──────────────────────────────────────
    try:
        url  = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpio}&format=json&jscmd=data"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            key  = f"ISBN:{isbn_limpio}"
            if key in data:
                libro = data[key]
                metadatos["titulo"]       = libro.get("title", "")
                metadatos["subtitulo"]    = libro.get("subtitle", "")
                metadatos["editorial"]    = (libro.get("publishers") or [{}])[0].get("name", "")
                metadatos["total_paginas"]= libro.get("number_of_pages", 0)
                metadatos["isbn"]         = isbn_limpio
                fecha = libro.get("publish_date", "")
                if fecha:
                    m = re.search(r"\d{4}", fecha)
                    metadatos["anio_publicacion"] = int(m.group()) if m else None
                autores = libro.get("authors", [])
                if autores:
                    metadatos["autor"] = autores[0].get("name", "")
                    if len(autores) > 1:
                        metadatos["autores_adicionales"] = [a.get("name", "") for a in autores[1:]]
                subjects = libro.get("subjects", [])
                if subjects:
                    metadatos["temas_clave"] = [
                        s.get("name", s) if isinstance(s, dict) else str(s)
                        for s in subjects[:8]
                    ]
                print(f"[ISBN] Open Library: {metadatos.get('titulo', '')}")
    except Exception as e:
        print(f"[ISBN] Open Library error: {e}")

    # ── 2. Google Books ───────────────────────────────────────
    try:
        url  = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpio}"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data  = resp.json()
            items = data.get("items", [])
            if items:
                info = items[0].get("volumeInfo", {})
                if not metadatos.get("titulo"):
                    metadatos["titulo"] = info.get("title", "")
                if not metadatos.get("autor"):
                    autores = info.get("authors", [])
                    metadatos["autor"] = autores[0] if autores else ""
                    if len(autores) > 1:
                        metadatos["autores_adicionales"] = autores[1:]
                if not metadatos.get("editorial"):
                    metadatos["editorial"] = info.get("publisher", "")
                if not metadatos.get("anio_publicacion"):
                    fecha = info.get("publishedDate", "")
                    if fecha:
                        m = re.search(r"\d{4}", fecha)
                        metadatos["anio_publicacion"] = int(m.group()) if m else None
                if not metadatos.get("total_paginas"):
                    metadatos["total_paginas"] = info.get("pageCount", 0)
                if not metadatos.get("descripcion"):
                    metadatos["descripcion"] = info.get("description", "")[:500]
                if not metadatos.get("temas_clave"):
                    metadatos["temas_clave"] = info.get("categories", [])
                metadatos["idioma"] = info.get("language", "es")
                print(f"[ISBN] Google Books: {metadatos.get('titulo', '')}")
    except Exception as e:
        print(f"[ISBN] Google Books error: {e}")

    # ── 3. Groq — categoriza y completa ──────────────────────
    if metadatos.get("titulo"):
        try:
            prompt = f"""Dados estos metadatos de un libro, completa y mejora la información:

Título: {metadatos.get('titulo', '')}
Autor: {metadatos.get('autor', '')}
Editorial: {metadatos.get('editorial', '')}
Descripción actual: {metadatos.get('descripcion', 'Sin descripción')[:200]}
Temas actuales: {metadatos.get('temas_clave', [])}

Responde SOLO en JSON válido sin texto adicional:
{{
  "categoria_principal": "una de: Teologia, Programacion, Matrimonio, Filosofia, Liderazgo, Historia, Otros",
  "descripcion_mejorada": "descripción clara y útil de 2-3 oraciones",
  "temas_clave": ["lista", "de", "temas", "máximo 6"],
  "subcategorias": ["subcategorías", "máximo 3"],
  "confianza_ia": 8
}}"""
            respuesta = _llamar_ai(prompt, max_tokens=400)
            if respuesta:
                json_match = re.search(r"\{.*\}", respuesta, re.DOTALL)
                if json_match:
                    extra = json.loads(json_match.group())
                    metadatos["categoria_principal"] = extra.get("categoria_principal", "Otros")
                    metadatos["subcategorias"]       = extra.get("subcategorias", [])
                    metadatos["confianza_ia"]        = extra.get("confianza_ia", 7)
                    if extra.get("descripcion_mejorada") and len(extra["descripcion_mejorada"]) > len(metadatos.get("descripcion", "")):
                        metadatos["descripcion"] = extra["descripcion_mejorada"]
                    temas = list(dict.fromkeys(metadatos.get("temas_clave", []) + extra.get("temas_clave", [])))
                    metadatos["temas_clave"] = temas[:8]
        except Exception as e:
            print(f"[ISBN] Groq error: {e}")
    else:
        try:
            prompt = f"""El ISBN {isbn_limpio} no está en las APIs públicas.
Basándote en tu conocimiento, ¿conoces este libro?
Si lo conoces responde en JSON, si no responde {{"desconocido": true}}:
{{
  "titulo": "", "autor": "", "editorial": "",
  "anio_publicacion": 0, "categoria_principal": "",
  "descripcion": "", "temas_clave": [],
  "subcategorias": [], "confianza_ia": 3
}}"""
            respuesta = _llamar_ai(prompt, max_tokens=300)
            if respuesta:
                json_match = re.search(r"\{.*\}", respuesta, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    if not data.get("desconocido"):
                        metadatos.update(data)
        except Exception as e:
            print(f"[ISBN] Groq fallback error: {e}")

    metadatos["isbn"]             = isbn_limpio
    metadatos["fuente_metadatos"] = "ISBN"
    metadatos.setdefault("confianza_ia", 5)
    metadatos.setdefault("temas_clave", [])
    metadatos.setdefault("subcategorias", [])
    metadatos.setdefault("autores_adicionales", [])

    return metadatos