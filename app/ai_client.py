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

def _llamar_ai(prompt: str, system: str = "",
               max_tokens: int = 500) -> Optional[str]:
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
            max_tokens=max_tokens,  # ← usa el parámetro
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

def buscar_metadatos_isbn(isbn: str) -> dict:
    """
    Busca metadatos de un libro por ISBN.
    Orden: Open Library → Google Books → Groq completa huecos.
    """
    import requests
    
    metadatos = {}
    isbn_limpio = isbn.replace('-', '').replace(' ', '').strip()
    
    # ── 1. Open Library ──────────────────────────────────────
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpio}&format=json&jscmd=data"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            key = f"ISBN:{isbn_limpio}"
            if key in data:
                libro = data[key]
                metadatos['titulo']          = libro.get('title', '')
                metadatos['subtitulo']       = libro.get('subtitle', '')
                metadatos['editorial']       = (libro.get('publishers') or [{}])[0].get('name', '')
                metadatos['total_paginas']   = libro.get('number_of_pages', 0)
                metadatos['isbn']            = isbn_limpio
                
                # Año de publicación
                fecha = libro.get('publish_date', '')
                if fecha:
                    import re
                    anio_match = re.search(r'\d{4}', fecha)
                    metadatos['anio_publicacion'] = int(anio_match.group()) if anio_match else None
                
                # Autores
                autores = libro.get('authors', [])
                if autores:
                    metadatos['autor'] = autores[0].get('name', '')
                    if len(autores) > 1:
                        metadatos['autores_adicionales'] = [a.get('name','') for a in autores[1:]]
                
                # Temas
                subjects = libro.get('subjects', [])
                if subjects:
                    metadatos['temas_clave'] = [
                        s.get('name', s) if isinstance(s, dict) else str(s)
                        for s in subjects[:8]
                    ]
                
                print(f"[ISBN] Open Library: {metadatos.get('titulo','')}")
    except Exception as e:
        print(f"[ISBN] Open Library error: {e}")
    
    # ── 2. Google Books (completa huecos) ─────────────────────
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpio}"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', [])
            if items:
                info = items[0].get('volumeInfo', {})
                
                # Solo completar lo que falta
                if not metadatos.get('titulo'):
                    metadatos['titulo'] = info.get('title', '')
                if not metadatos.get('autor'):
                    autores = info.get('authors', [])
                    metadatos['autor'] = autores[0] if autores else ''
                    if len(autores) > 1:
                        metadatos['autores_adicionales'] = autores[1:]
                if not metadatos.get('editorial'):
                    metadatos['editorial'] = info.get('publisher', '')
                if not metadatos.get('anio_publicacion'):
                    fecha = info.get('publishedDate', '')
                    if fecha:
                        import re
                        anio_match = re.search(r'\d{4}', fecha)
                        metadatos['anio_publicacion'] = int(anio_match.group()) if anio_match else None
                if not metadatos.get('total_paginas'):
                    metadatos['total_paginas'] = info.get('pageCount', 0)
                if not metadatos.get('descripcion'):
                    metadatos['descripcion'] = info.get('description', '')[:500]
                if not metadatos.get('temas_clave'):
                    metadatos['temas_clave'] = info.get('categories', [])
                
                # Idioma
                metadatos['idioma'] = info.get('language', 'es')
                
                print(f"[ISBN] Google Books: {metadatos.get('titulo','')}")
    except Exception as e:
        print(f"[ISBN] Google Books error: {e}")
    
    # ── 3. Groq completa y categoriza ─────────────────────────
    if metadatos.get('titulo'):
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
  "descripcion_mejorada": "descripción clara y útil de 2-3 oraciones si la actual es pobre",
  "temas_clave": ["lista", "de", "temas", "relevantes", "máximo 6"],
  "subcategorias": ["subcategorías", "específicas", "máximo 3"],
  "confianza_ia": 8
}}"""
            
            respuesta = _llamar_ai(prompt, max_tokens=400)
            if respuesta:
                import re, json
                json_match = re.search(r'\{.*\}', respuesta, re.DOTALL)
                if json_match:
                    extra = json.loads(json_match.group())
                    metadatos['categoria_principal'] = extra.get('categoria_principal', 'Otros')
                    metadatos['subcategorias']       = extra.get('subcategorias', [])
                    metadatos['confianza_ia']        = extra.get('confianza_ia', 7)
                    
                    # Mejorar descripción si Groq la tiene mejor
                    if extra.get('descripcion_mejorada') and len(extra['descripcion_mejorada']) > len(metadatos.get('descripcion', '')):
                        metadatos['descripcion'] = extra['descripcion_mejorada']
                    
                    # Combinar temas
                    temas_extra = extra.get('temas_clave', [])
                    temas_existentes = metadatos.get('temas_clave', [])
                    metadatos['temas_clave'] = list(dict.fromkeys(temas_existentes + temas_extra))[:8]
                    
                    print(f"[ISBN] Groq completó: categoría={metadatos['categoria_principal']}")
        except Exception as e:
            print(f"[ISBN] Groq error: {e}")
    else:
        # Título no encontrado — Groq intenta con solo el ISBN
        try:
            prompt = f"""El ISBN {isbn_limpio} no está en las APIs públicas.
Basándote en tu conocimiento, ¿conoces este libro?
Si lo conoces responde en JSON, si no responde {{"desconocido": true}}:
{{
  "titulo": "",
  "autor": "",
  "editorial": "",
  "anio_publicacion": 0,
  "categoria_principal": "",
  "descripcion": "",
  "temas_clave": [],
  "subcategorias": [],
  "confianza_ia": 3
}}"""
            respuesta = _llamar_ai(prompt, max_tokens=300)
            if respuesta:
                import re, json
                json_match = re.search(r'\{.*\}', respuesta, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    if not data.get('desconocido'):
                        metadatos.update(data)
                        print(f"[ISBN] Groq conoce el libro: {metadatos.get('titulo','')}")
        except Exception as e:
            print(f"[ISBN] Groq fallback error: {e}")
    
    metadatos['isbn']            = isbn_limpio
    metadatos['fuente_metadatos'] = 'ISBN'
    metadatos.setdefault('confianza_ia', 5)
    metadatos.setdefault('temas_clave', [])
    metadatos.setdefault('subcategorias', [])
    metadatos.setdefault('autores_adicionales', [])
    
    return metadatos