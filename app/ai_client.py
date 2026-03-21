"""
ai_client.py - Integración con Groq (reemplaza gemini_client.py)
"""

import os
import json
import time
from typing import Optional, Dict, List
from datetime import datetime, date
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODELO = "llama-3.3-70b-versatile"  # Mejor modelo gratuito de Groq

_ESTADO_FILE = Path(__file__).parent / ".ai_state.json"

# ═══════════════════════════════════════════════
# ESTADO PERSISTENTE
# ═══════════════════════════════════════════════

def _cargar_estado() -> dict:
    try:
        if _ESTADO_FILE.exists():
            return json.loads(_ESTADO_FILE.read_text())
    except Exception:
        pass
    return {"bloqueado_hasta": 0.0, "llamadas_hoy": 0, "fecha": str(date.today())}

def _guardar_estado():
    try:
        _ESTADO_FILE.write_text(json.dumps({
            "bloqueado_hasta": _estado["bloqueado_hasta"],
            "llamadas_hoy": _estado["llamadas_hoy"],
            "fecha": str(_estado["fecha_contador"]),
        }))
    except Exception:
        pass

_persistido = _cargar_estado()
_estado = {
    "llamadas_hoy": _persistido.get("llamadas_hoy", 0),
    "fecha_contador": date.fromisoformat(_persistido.get("fecha", str(date.today()))),
    "conexion_ok": None,
    "conexion_ts": 0.0,
    "conexion_ttl": 600,       # Cache 10 min — Groq es estable
    "bloqueado_hasta": _persistido.get("bloqueado_hasta", 0.0),
}

_MAX_LLAMADAS_DIA = 400        # Groq permite 14,400 — usamos 400 de margen

client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[AI] Error inicializando Groq: {e}")

# ═══════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════

def _reiniciar_si_nuevo_dia():
    hoy = date.today()
    if _estado["fecha_contador"] != hoy:
        _estado["llamadas_hoy"] = 0
        _estado["fecha_contador"] = hoy
        _estado["bloqueado_hasta"] = 0.0
        _estado["conexion_ok"] = None
        _guardar_estado()

def _hay_cuota() -> bool:
    _reiniciar_si_nuevo_dia()
    if time.time() < _estado["bloqueado_hasta"]:
        return False
    return _estado["llamadas_hoy"] < _MAX_LLAMADAS_DIA

def _registrar_llamada():
    _estado["llamadas_hoy"] += 1
    _guardar_estado()

def _registrar_error_429(delay: int = 60):
    _estado["bloqueado_hasta"] = time.time() + delay
    _estado["conexion_ok"] = False
    _guardar_estado()
    print(f"[AI] Rate limit. Bloqueado {delay}s.")

def _llamar_ai(prompt: str, system: str = "") -> Optional[str]:
    """Wrapper central — toda llamada pasa por aquí."""
    if not _hay_cuota() or not client:
        return None
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    try:
        response = client.chat.completions.create(
            model=MODELO,
            messages=messages,
            max_tokens=500,
        )
        _registrar_llamada()
        return response.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower():
            _registrar_error_429(65)
        print(f"[AI] Error: {err[:80]}")
        return None

# ═══════════════════════════════════════════════
# API PÚBLICA (mismos nombres que gemini_client)
# ═══════════════════════════════════════════════

def api_key_configurada() -> bool:
    if not GROQ_API_KEY:
        return False
    return len(GROQ_API_KEY) > 20

def verificar_conexion(forzar: bool = False) -> bool:
    if not api_key_configurada() or not client:
        return False
    
    ahora = time.time()
    cache_vigente = (ahora - _estado["conexion_ts"]) < _estado["conexion_ttl"]
    
    if not forzar and _estado["conexion_ok"] is not None and cache_vigente:
        return _estado["conexion_ok"]
    
    if not _hay_cuota():
        return False
    
    resultado = _llamar_ai("OK") is not None
    _estado["conexion_ok"] = resultado
    _estado["conexion_ts"] = ahora
    return resultado

def estado_gemini() -> Dict:
    """Mantiene el nombre para no cambiar app.py."""
    _reiniciar_si_nuevo_dia()
    bloqueado = time.time() < _estado["bloqueado_hasta"]
    sin_cuota = _estado["llamadas_hoy"] >= _MAX_LLAMADAS_DIA
    conectado = _estado["conexion_ok"] is True and not bloqueado
    
    if conectado:
        modo = "online"
    elif bloqueado:
        modo = "offline_rate_limited"
    elif sin_cuota:
        modo = "offline_sin_cuota"
    elif not api_key_configurada():
        modo = "offline_sin_key"
    else:
        modo = "offline_sin_verificar"
    
    return {
        "api_key_configurada": api_key_configurada(),
        "conectado": conectado,
        "llamadas_hoy": _estado["llamadas_hoy"],
        "max_llamadas": _MAX_LLAMADAS_DIA,
        "restantes": max(0, _MAX_LLAMADAS_DIA - _estado["llamadas_hoy"]),
        "modo": modo,
    }

# ═══════════════════════════════════════════════
# FALLBACKS (igual que antes)
# ═══════════════════════════════════════════════

FALLBACKS = {
    "resumen_semanal": "🌟 Modo offline activo. Revisa tus hábitos manualmente hoy.",
    "alerta_matrimonio": "⏰ Son las 20:30. Guarda las pantallas — tiempo sagrado en 30 min. 💑",
    "analisis_salud": "📊 Sigue registrando para ver patrones. Prioriza 7+ horas de sueño.",
    "chat_bienvenida": "¡Hola! Estoy en modo offline. Vuelve en unos minutos.",
    "sugerencia_devocional": "📖 Salmo 119:9-16 — ¿Cómo guardas tus caminos hoy?",
}

def _fallback(tipo: str) -> str:
    return FALLBACKS.get(tipo, "🤖 Modo offline activo.")

SYSTEM_MISION = "Eres la Secretaria IA de Mission Dashboard, asistente personal cristiano para teología, programación, finanzas y matrimonio. Responde en español, de forma breve y práctica."

def chat_simple(mensaje: str, contexto: str = "") -> str:
    resultado = _llamar_ai(mensaje, system=SYSTEM_MISION)
    return resultado or _fallback("chat_bienvenida")

def generar_resumen_semanal(*args, **kwargs) -> str:
    resultado = _llamar_ai(
        "Genera un resumen motivacional semanal. Incluye: victorias posibles, área de mejora y un versículo bíblico. Máximo 200 palabras. Usa markdown.",
        system=SYSTEM_MISION
    )
    return resultado or _fallback("resumen_semanal")

def generar_alerta_matrimonio(contexto: str = "") -> str:
    resultado = _llamar_ai(
        "Genera una alerta cariñosa para las 20:30 recordando preparar tiempo en pareja a las 21:00. Breve y con una acción concreta.",
        system=SYSTEM_MISION
    )
    return resultado or _fallback("alerta_matrimonio")

def analizar_patron_salud(registros: List[Dict]) -> str:
    if len(registros) < 4:
        return "Datos insuficientes. Sigue registrando tu rutina."
    resultado = _llamar_ai(
        f"Analiza correlación ejercicio-productividad: {json.dumps(registros[:5])}. Máximo 3 oraciones.",
        system=SYSTEM_MISION
    )
    return resultado or _fallback("analisis_salud")

def sugerir_lectura_devocional(tema: str = "", pasaje: str = "") -> str:
    resultado = _llamar_ai(
        f"Sugiere un pasaje bíblico relacionado con: '{tema}'. Incluye referencia y una pregunta de reflexión. Máximo 100 palabras.",
        system=SYSTEM_MISION
    )
    return resultado or _fallback("sugerencia_devocional")

def extraer_metadatos_libro(contenido_pdf: bytes, nombre_archivo: str) -> Dict:
    """
    Extrae metadatos reales del PDF usando pdfplumber + Groq.
    Si falla, usa el nombre del archivo como fallback.
    """
    texto_extraido = ""
    
    # ── Extraer texto real con pdfplumber ───────────────────
    try:
        import pdfplumber
        import io
        
        with pdfplumber.open(io.BytesIO(contenido_pdf)) as pdf:
            paginas_a_leer = min(5, len(pdf.pages))  # Solo primeras 5 páginas
            partes = []
            
            for i in range(paginas_a_leer):
                pagina = pdf.pages[i]
                texto = pagina.extract_text()
                if texto:
                    partes.append(texto.strip())
            
            texto_extraido = "\n\n".join(partes)
            total_paginas_real = len(pdf.pages)
            
        print(f"[PDF] Extraídas {paginas_a_leer} páginas, {len(texto_extraido)} caracteres")
        
    except Exception as e:
        print(f"[PDF] Error extrayendo texto: {e}")
        texto_extraido = ""
        total_paginas_real = 0
    
    # ── Limitar texto para no exceder tokens de Groq ────────
    # Groq acepta ~6000 tokens/min — 3000 caracteres es seguro
    texto_para_ia = texto_extraido[:3000] if texto_extraido else f"Nombre del archivo: {nombre_archivo}"
    
    # ── Enviar a Groq para análisis ─────────────────────────
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
    "anio_publicacion": año como número si aparece sino null,
    "total_paginas": {total_paginas_real if total_paginas_real > 0 else "null"},
    "temas_clave": ["tema1", "tema2", "tema3"],
    "confianza_extraccion": número del 1 al 10 según qué tan seguro estás
}}"""

    resultado = _llamar_ai(prompt)
    
    if resultado:
        try:
            # Limpiar posible markdown que Groq agregue
            texto_limpio = resultado.strip()
            if "```" in texto_limpio:
                texto_limpio = texto_limpio.split("```")[1]
                if texto_limpio.startswith("json"):
                    texto_limpio = texto_limpio[4:]
            
            metadatos = json.loads(texto_limpio.strip())
            
            # Garantizar campos obligatorios
            metadatos.setdefault("titulo", nombre_archivo.replace(".pdf", "").replace("_", " ").title())
            metadatos.setdefault("autor", "Desconocido")
            metadatos.setdefault("categoria_principal", "Otros")
            metadatos.setdefault("descripcion", "Sin descripción")
            metadatos.setdefault("temas_clave", [])
            metadatos["fuente_metadatos"] = "IA"
            metadatos["fecha_extraccion"] = datetime.now().isoformat()
            
            # Asegurar total_paginas del PDF real
            if total_paginas_real > 0:
                metadatos["total_paginas"] = total_paginas_real
            
            return metadatos
            
        except json.JSONDecodeError as e:
            print(f"[AI] Error parseando JSON: {e}")
            print(f"[AI] Respuesta recibida: {resultado[:200]}")
    
    # ── Fallback si todo falla ───────────────────────────────
    return {
        "titulo": nombre_archivo.replace(".pdf", "").replace("_", " ").title(),
        "autor": "Desconocido",
        "categoria_principal": "Otros",
        "descripcion": "No se pudo extraer descripción automáticamente.",
        "total_paginas": total_paginas_real,
        "temas_clave": [],
        "confianza_extraccion": 1,
        "fuente_metadatos": "IA",
    }