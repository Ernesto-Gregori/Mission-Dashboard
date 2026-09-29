"""Idioma de la interfaz. Español es el origen; inglés se aplica al HTML ya renderizado
y, en el bot, al texto plano de cada respuesta."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from app.i18n_frases import FRASES
from app.i18n_telegram import FRASES as FRASES_TG
from app.i18n_telegram import PATRONES as _PATRONES_TG_SRC

IDIOMAS = ("es", "en")
COOKIE = "mission_lang"
_MAX_AGE = 60 * 60 * 24 * 365

# Nombres de la cuenta original. No entran al catálogo: en inglés siguen igual.
_NO_TRADUCIR = {
    "Teología / Devocional",
    "Matrimonio / Pareja",
    "Fe",
    "Pareja",
    "Deep Work",
    "Biblioteca",
    "Salud & Energía",
    "Mission Dashboard",
    "Español",
    "English",
}

# Frases completas. No se reemplaza por subcadena: «Hoy» dentro de una oración no cambia.
CATALOGO = {
    # Cromo
    "Saltar al contenido": "Skip to content",
    "Navegación principal": "Main navigation",
    "En esta sección": "In this section",
    "Hoy": "Today",
    "Semana": "Week",
    "Cuenta": "Account",
    "Alma": "Assistant",
    "Dinero": "Money",
    "Cuerpo": "Body",
    "Día": "Day",
    "Áreas": "Areas",
    "Rueda": "Wheel",
    "Datos": "Data",
    "Conexiones": "Connections",
    "Sistema": "System",
    "Configuración": "Settings",
    "Tema oscuro": "Dark theme",
    "Tema claro": "Light theme",
    "Cerrar sesión": "Sign out",
    "Idioma": "Language",
    "Idioma de la interfaz": "Interface language",
    # Nombres neutros
    "Finanzas": "Finance",
    "Enfoque": "Focus",
    "Espiritualidad": "Spirituality",
    "Lectura": "Reading",
    "Salud": "Health",
    "Relaciones": "Relationships",
    "Revisión semanal": "Weekly review",
    "Vínculos": "Connections",
    "Revisión": "Review",
    "Planificador": "Planner",
    "Mes": "Month",
    "Vencimientos": "Bills",
    "Precios supermercados": "Grocery prices",
    "Precios": "Prices",
    "Mi sistema": "My system",
    "Editar hábitos": "Edit habits",
    "Plan y cobros": "Plan and billing",
    "Telegram y usuarios": "Telegram and users",
    "Familia": "Family",
    # Auth
    "Acceso privado — FastAPI + HTMX": "Private access — FastAPI + HTMX",
    "Usuario": "Username",
    "Contraseña": "Password",
    "Entrar": "Sign in",
    "Privacidad": "Privacy",
    "Términos": "Terms",
    "Primer acceso": "First sign-in",
    "Crea el usuario administrador. La contraseña se guarda con hash (mín. 8).": "Create the administrator. The password is stored hashed (min. 8).",
    "Repetir contraseña": "Repeat password",
    "Crear y entrar": "Create and sign in",
    "Usuario o contraseña incorrectos.": "Wrong username or password.",
    "Las contraseñas no coinciden.": "Passwords do not match.",
    "Inicio · Mission": "Home · Mission",
    "Elige cómo empezar": "Choose how to start",
    "Coach — cuéntame de ti": "Coach — tell me about you",
    "Coach — tu sistema": "Coach — your system",
    "Política de privacidad": "Privacy policy",
    "Términos de servicio": "Terms of service",
    "Tablero privado de hábitos, agenda, salud y finanzas.": "Private board for habits, schedule, health, and money.",
    "Para qué pide Google": "Why it asks for Google",
    "Volver al acceso": "Back to sign in",
    # Hoy
    "Agenda de hoy": "Today's schedule",
    "Línea de tiempo": "Timeline",
    "Nada agendado para hoy.": "Nothing scheduled for today.",
    "Sincronizar Calendar": "Sync Calendar",
    "Ritual y hábitos": "Ritual and habits",
    "Registrado hoy.": "Logged today.",
    "Guardar ritual": "Save ritual",
    "Tus áreas": "Your areas",
    "Del Coach": "From the Coach",
    "Ver briefing completo →": "See the full briefing →",
    "Tu sistema quedó configurado con el Coach.": "Your system was set up with the Coach.",
    "Todavía no activaste áreas. Hoy, Semana y Cuenta siguen aquí. Puedes armarlas en": "You have not turned on any areas yet. Today, Week, and Account are still here. Set them up in",
    "Planificar la semana, bloques de enfoque y revisión del domingo.": "Plan the week, focus blocks, and the Sunday review.",
    "Ingreso repartido en sobres, vencimientos y precios.": "Income split into envelopes, bills, and prices.",
    "Sueño, ejercicio y energía.": "Sleep, exercise, and energy.",
    "Devocional y oración.": "Devotional and prayer.",
    "Libros, progreso y resaltados.": "Books, progress, and highlights.",
    "Citas, notas y conexión.": "Dates, notes, and connection.",
    "Ingreso, gastos y vencimientos.": "Income, expenses, and bills.",
    "Bloques de trabajo concentrado.": "Blocks of focused work.",
    "Una práctica para cuidar lo que te sostiene.": "A practice for what sustains you.",
    "Personas que quieres cuidar: pareja, familia o amigos.": "People you want to care for: partner, family, or friends.",
    # Configuración
    "Tus áreas y el día a día. Apagar un área lo esconde y deja tus registros donde están.": "Your areas and the day to day. Turning an area off hides it and leaves your records in place.",
    "Todavía no hay áreas. Hoy, Semana y Cuenta siguen disponibles.": "No areas yet. Today, Week, and Account stay available.",
    "Día y asistente": "Day and assistant",
    "Ritual": "Ritual",
    "Gratitud e intención en Hoy": "Gratitude and intention on Today",
    "Rueda de la vida": "Life wheel",
    "Marca las que entran en la revisión. Mínimo 3.": "Check the ones that appear in the review. At least 3.",
    "Nueva área": "New area",
    "Mostrar": "Show",
    "Deja al menos 3 áreas en la rueda.": "Leave at least 3 areas on the wheel.",
    "La rueda admite hasta 12 áreas.": "The wheel allows up to 12 areas.",
    "La puntuación de la revisión semanal": "The weekly review score",
    "La asistente": "The assistant",
    "Primera pregunta del ritual": "First ritual question",
    "Segunda pregunta del ritual": "Second ritual question",
    "El día en el plan empieza a las": "The planned day starts at",
    "y termina a las": "and ends at",
    "Moneda": "Currency",
    "Método": "Method",
    "Sobres": "Envelopes",
    "Porcentajes": "Percentages",
    "Categorías": "Categories",
    "Nueva categoría": "New category",
    "Ej: Mascotas": "E.g. Pets",
    "Frecuencia de hábitos": "Habit frequency",
    "Todos los días": "Every day",
    "Entre semana": "Weekdays",
    "Fin de semana": "Weekend",
    "Solo los lunes": "Mondays only",
    "Días concretos": "Specific days",
    "Solo se guardan si eliges Días concretos.": "They are saved only if you choose Specific days.",
    "Elige al menos un día.": "Choose at least one day.",
    "Guardar": "Save",
    "Configuración guardada.": "Settings saved.",
    "Tus datos": "Your data",
    "Descargar una copia": "Download a copy",
    "La exportación está en Premium.": "Export is part of Premium.",
    "El plan Free no incluye exportación.": "The Free plan does not include export.",
    "Eliminar la cuenta": "Delete account",
    "Borra tu usuario y tus registros. No se puede deshacer.": "Deletes your user and your records. This cannot be undone.",
    "Eliminar cuenta": "Delete account",
    "El coach sigue disponible para rearmar el sistema.": "The coach is still available to rebuild the system.",
    "Gratitud": "Gratitude",
    "Intención": "Intention",
    "Sueño": "Sleep",
    "Energía de la mañana": "Morning energy",
    "Energía de la tarde": "Afternoon energy",
    "Energía de la noche": "Evening energy",
    "Tres cosas por las que estoy agradecido": "Three things I am grateful for",
    "Lo único que, si lo hago, el día ya valió": "The one thing that makes the day count",
    # Coach y plantillas
    "Coach Mission Dashboard": "Mission Dashboard coach",
    "Elige una plantilla. Si no eliges, no se crea ningún hábito ni área.": "Pick a template. If you do not pick one, no habit or area is created.",
    "Cómo quieres empezar": "How do you want to start",
    "Empezar": "Start",
    "Prefiero contárselo al coach": "I would rather tell the coach",
    "Empezar en blanco": "Start blank",
    "Sin áreas ni hábitos. Hoy, Semana y Cuenta quedan listos.": "No areas or habits. Today, Week, and Account are ready.",
    "Día a día": "Day to day",
    "Dinero, cuerpo y un hábito de movimiento.": "Money, body, and a movement habit.",
    "Estudio": "Study",
    "Enfoque, lectura y un hábito para sentarte a leer.": "Focus, reading, and a habit to sit down and read.",
    "Personas que quieres cuidar, con un hábito de conexión.": "People you want to care for, with a connection habit.",
    "Práctica interior": "Inner practice",
    "Una práctica espiritual y el cuidado del cuerpo.": "A spiritual practice and care for the body.",
    "¿Cómo te llamo?": "What should I call you?",
    "¿En qué etapa estás?": "What stage are you in?",
    "¿Qué quieres mejorar o registrar?": "What do you want to improve or track?",
    "Áreas importantes ahora": "Areas that matter now",
    "Tiempo al día para el sistema": "Time per day for the system",
    "Algo más (opcional)": "Anything else (optional)",
    "Continuar →": "Continue →",
    "Hábitos diarios": "Daily habits",
    "Aparecen como checklist en Hoy. Archivar un hábito lo oculta sin borrar su historial.": "They show up as a checklist on Today. Archiving a habit hides it without deleting its history.",
    "Emoji": "Emoji",
    "Nombre": "Name",
    "Hora (opcional)": "Time (optional)",
    "Archivar": "Archive",
    "Todavía no tienes hábitos activos.": "You do not have active habits yet.",
    "Nuevo hábito": "New habit",
    "Agregar": "Add",
    "Reactivar": "Reactivate",
    "Ninguna área activa.": "No active area.",
    "Abrir configuración": "Open settings",
    "para renombrar, apagar o cambiar el ritual sin pasar por el coach.": "to rename, turn off, or change the ritual without the coach.",
    "✏️ Cambiar mis áreas con el coach": "✏️ Change my areas with the coach",
    "Plan Free: el Coach IA de setup es una sola vez.": "Free plan: the AI setup coach runs once.",
    "Desbloquear reconfiguración (Premium)": "Unlock reconfiguration (Premium)",
    "Disponibles en Premium": "Available on Premium",
    "Ver planes": "See plans",
    "Elegir este plan": "Choose this plan",
    "Tu plan actual": "Your current plan",
    "Tu sistema propuesto": "Your proposed system",
    "Hábitos sugeridos": "Suggested habits",
    "← Atrás": "← Back",
    "✅ Activar mi sistema": "✅ Activate my system",
    "Ver Premium": "See Premium",
    # Acciones comunes
    "Cancelar": "Cancel",
    "Eliminar": "Delete",
    "Editar": "Edit",
    "Buscar": "Search",
    "Filtrar": "Filter",
    "Aplicar": "Apply",
    "Volver": "Back",
    "← Volver": "← Back",
    "Guardar cambios": "Save changes",
    "Actualizar": "Update",
    "Agregar bloque": "Add block",
    "Título": "Title",
    "Notas": "Notes",
    "Fecha": "Date",
    "Inicio": "Start",
    "Fin": "End",
    "Tipo": "Type",
    "Lunes": "Monday",
    "Domingo": "Sunday",
    "La semana empieza": "The week starts",
    "Todo el día": "All day",
    "Siguiente ▶": "Next ▶",
    "◀ Anterior": "◀ Previous",
    "Conectar en Configuración": "Connect in Settings",
    "Conectar Google y Telegram": "Connect Google and Telegram",
    "Sincronizar ahora": "Sync now",
    "Ver planes": "See plans",
    # Asistente
    "Asistente personal. Nada del dashboard se comparte hasta que lo marques.": "Personal assistant. Nothing from the dashboard is shared until you check it.",
    "Qué puede leer Alma": "What the assistant can read",
    "Por defecto, nada. Cada categoría es un permiso explícito.": "Nothing by default. Each category is an explicit permission.",
    "Guardar permisos": "Save permissions",
    "Conversación": "Conversation",
    "Borrar historial": "Clear history",
    "Mensaje": "Message",
    "Permisos de este mensaje": "Permissions for this message",
    "Enviar a Alma": "Send to the assistant",
    "Briefing de la mañana": "Morning briefing",
    "Activar": "Enable",
    "Hora": "Time",
    "Guardar briefing": "Save briefing",
    # Plan y avisos
    "Plan actual:": "Current plan:",
    "Áreas ilimitadas": "Unlimited areas",
    "Coach reconfigurable": "Coach can be reconfigured",
    "Briefings diarios": "Daily briefings",
    "Google Fit / Calendar": "Google Fit / Calendar",
    "Error": "Error",
    "usuario": "user",
    "admin": "admin",
}

for _clave, _valor in FRASES.items():
    CATALOGO.setdefault(_clave, _valor)
for _clave, _valor in FRASES_TG.items():
    CATALOGO.setdefault(_clave, _valor)

_PATRONES = (
    (re.compile(r"^(\d+) áreas activas$"), r"\1 active areas"),
    (re.compile(r"^Archivados \((\d+)\)$"), r"Archived (\1)"),
    (re.compile(r"^Demasiados intentos\. Espera (\d+)s\.$"), r"Too many attempts. Wait \1s."),
    (re.compile(r"^Cupo esta semana: (\d+)/(\d+)\.$"), r"Quota this week: \1/\2."),
    (re.compile(r"^Semana (\d{2}/\d{2}) — (\d{2}/\d{2}/\d{4})$"), r"Week \1 — \2"),
    (re.compile(r"^Días seguidos cumpliendo: (.+)$"), r"Days in a row met: \1"),
    (re.compile(r"^3 sobres · (.+)$"), r"3 envelopes · \1"),
    (re.compile(r"^3 sobres \(([\d/]+)\)$"), r"3 envelopes (\1)"),
    (re.compile(r"^Disponible: (.+)$"), r"Available: \1"),
    (
        re.compile(r"^Sugerido desde tus vencimientos de ingreso \((.+)\)\. Guárdalo para usarlo este mes\.$"),
        r"Suggested from your income bills (\1). Save it to use it this month.",
    ),
    (re.compile(r"^No se pudo guardar la imagen: (.+)$"), r"Could not save the image: \1"),
    (re.compile(r"^Supermercado desconocido: (.+)$"), r"Unknown store: \1"),
    (re.compile(r"^No se pudo actualizar (.+): (.+)$"), r"Could not update \1: \2"),
    (
        re.compile(r"^Código generado\. Vence en 10 minutos\. Código: (\d+)$"),
        r"Code generated. It expires in 10 minutes. Code: \1",
    ),
    (re.compile(r"^Pago recibido\. Plan activo: (.+)\.$"), r"Payment received. Active plan: \1."),
    (
        re.compile(
            r"^Pago recibido( \(.*\))?\. Si tu plan aún aparece Free, espera unos segundos y recarga — "
            r"el webhook de Stripe actualiza Turso\.$"
        ),
        r"Payment received\1. If your plan still shows Free, wait a few seconds and reload — "
        r"the Stripe webhook updates the database.",
    ),
    (re.compile(r"^Fit: (.+)$"), r"Fit: \1"),
    (re.compile(r"^Rueda de la vida · (.+) / 10$"), r"Life wheel · \1 / 10"),
    (re.compile(r"^Rueda de la vida con (\d+) áreas$"), r"Life wheel with \1 areas"),
    (re.compile(r"^(\d+) días de racha$"), r"\1-day streak"),
    (re.compile(r"^✝️ (\d+) días$"), r"✝️ \1 days"),
    (
        re.compile(r"^Una lectura de tus áreas juntas\. Cupo esta semana: (\d+)/(\d+)\.$"),
        r"A reading of your areas together. Quota this week: \1/\2.",
    ),
    (
        re.compile(r"^Una lectura de tus áreas juntas\. Cupo esta semana: ilimitado\.$"),
        r"A reading of your areas together. Quota this week: unlimited.",
    ),
    (re.compile(r"^Generado (.+) · ventana (\d+) días$"), r"Generated \1 · \2-day window"),
    (re.compile(r"^(\d+) días · (\d+) min$"), r"\1 days · \2 min"),
    (re.compile(r"^JSON inválido: (.+)$"), r"Invalid JSON: \1"),
    (re.compile(r"^Última actualización: (.+)$"), r"Last update: \1"),
    (re.compile(r"^(\d+) productos$"), r"\1 products"),
    (
        re.compile(r"^(\d+) productos indexados\. Usa la búsqueda o actualiza una tienda\.$"),
        r"\1 products indexed. Use search or refresh a store.",
    ),
    (re.compile(r"^· sueño (.+)h · ⚡(.+)$"), r"· sleep \1h · ⚡\2"),
    (re.compile(r"^· 💪 ejercicio\s*(\d*)min$"), r"· 💪 exercise \1min"),
    (re.compile(r"^Día (\d+) · (.+) · \$(.+)$"), r"Day \1 · \2 · $\3"),
    (re.compile(r"^Eliminar gasto (.+)$"), r"Delete expense \1"),
    (re.compile(r"^Eliminar (.+)$"), r"Delete \1"),
    (re.compile(r"^💰 Sobres de (.+)$"), r"💰 Envelopes for \1"),
    (re.compile(r"^(.+) · pág\. (\d+)/(\d+)$"), r"\1 · p. \2/\3"),
    (re.compile(r"^(.+) · pág\. (\d+)$"), r"\1 · p. \2"),
    (re.compile(r"^pág\. (\d+)/(—|\d+) · ([\d.]+)%$"), r"p. \1/\2 · \3%"),
    (re.compile(r"^(.*?) · Free: máx\. (\d+) áreas$"), r"\1 · Free: max. \2 areas"),
    (
        re.compile(r"^Tu plan permite máximo (\d+) áreas\.$"),
        r"Your plan allows at most \1 areas.",
    ),
    (
        re.compile(r"^Tu plan permite máximo (\d+) áreas\. Desmarca (\d+) o pasa a Premium\.$"),
        r"Your plan allows at most \1 areas. Uncheck \2 or move to Premium.",
    ),
    (
        re.compile(
            r"^Tu plan Free permite (\d+) áreas activas\. Puedes cambiar cuáles están activas, "
            r"o pasar a Premium para tenerlas todas\.$"
        ),
        r"Your Free plan allows \1 active areas. You can change which ones are on, "
        r"or move to Premium to have them all.",
    ),
)

_PATRONES_TG = tuple((re.compile(patron), reemplazo) for patron, reemplazo in _PATRONES_TG_SRC)

_ESTADO_EN = {"Completado": "Done", "Parcial": "Partial", "Postergado": "Postponed"}
_MOMENTO_EN = {"manana": "morning", "tarde": "afternoon", "noche": "evening"}
_RE_GASTO = re.compile(r"^Anoté \$([0-9.]+) en «(.+)» → (.+) \((.+)\)\.$")
_RE_LISTO = re.compile(r"^Listo: ahora está en (.+) \((.+)\)\.$")
_RE_SOBRE = re.compile(r"^Sobre más justo: (🟢|🟡|🔴) (.+) \$(\d+)$")
_RE_LUZ = re.compile(r"^(🟢|🟡|🔴) (.+): \$(\d+) de \$(\d+)$")
_RE_CUERPO = re.compile(r"^Cuerpo: (.+)$")
_RE_ROJOS = re.compile(r"^Sobres en rojo: (.+)$")
_RE_AREA_AYUDA = re.compile(
    r"^El área «(.+)» está apagada\. Se prende en la app, en Cuenta → Configuración\. No listo comandos\.$"
)
_RE_AREA_OFF = re.compile(
    r"^El área «(.+)» está apagada, así que no guardé nada\. "
    r"Actívala en la app, en Cuenta → Configuración\.$"
)
_RE_ENERGIA = re.compile(r"^Anoté energía de (manana|tarde|noche) en (\d)/5\.$")
_RE_BLOQUE = re.compile(r"^(\d{2}:\d{2}) (.+) · (Completado|Parcial|Postergado)$")
_RE_ESTADO = re.compile(r"^(.+): (Completado|Parcial|Postergado)\.$")

_ATRIBUTOS = {"placeholder", "aria-label", "title", "alt"}
_ATRIBUTOS_CONFIRM = {"onsubmit", "onclick"}
_SALTAR = {"script", "style", "textarea"}


def normalizar(idioma: str | None) -> str:
    valor = (idioma or "es").strip().lower()[:2]
    return valor if valor in IDIOMAS else "es"


def _nucleo(texto: str) -> str:
    if texto in _NO_TRADUCIR:
        return texto
    nuevo = CATALOGO.get(texto)
    if nuevo:
        return nuevo
    for patron, reemplazo in _PATRONES:
        if patron.fullmatch(texto):
            return patron.sub(reemplazo, texto)
    mostrar = re.fullmatch(r"Mostrar (.+)", texto)
    if mostrar:
        return f"Show {_nucleo(mostrar.group(1))}"
    titulo = re.fullmatch(r"(.+) · Mission", texto)
    if titulo:
        interno = _nucleo(titulo.group(1))
        if interno != titulo.group(1):
            return f"{interno} · Mission"
    compuesto = _componer(texto)
    if compuesto:
        return compuesto
    return texto


def _componer(texto: str) -> str | None:
    """Une cromo que el HTML deja en un solo nodo: «emoji Nombre — descripción»."""
    if texto.startswith("— "):
        resto = texto[2:]
        nuevo = _nucleo(resto)
        if nuevo != resto:
            return f"— {nuevo}"
        return None
    if " — " in texto:
        izquierda, derecha = texto.split(" — ", 1)
        izq = _nucleo(izquierda)
        der = _nucleo(derecha)
        if izq != izquierda or der != derecha:
            return f"{izq} — {der}"
        return None
    marca = re.fullmatch(r"(\S+) (.+)", texto)
    if not marca or any(c.isalnum() for c in marca.group(1)):
        return None
    nombre = _nucleo(marca.group(2))
    if nombre == marca.group(2):
        return None
    return f"{marca.group(1)} {nombre}"


def traducir_fragmento(texto: str) -> str:
    if not texto or not texto.strip():
        return texto
    lead = texto[: len(texto) - len(texto.lstrip())]
    trail = texto[len(texto.rstrip()) :]
    nucleo = " ".join(texto.split())
    nuevo = _nucleo(nucleo)
    if nuevo == nucleo:
        return texto
    return f"{lead}{nuevo}{trail}"


def _caso_telegram(nucleo: str) -> str | None:
    """Líneas del bot cuyo dato (nombre, monto, título) no se traduce, salvo etiquetas conocidas."""
    gasto = _RE_GASTO.fullmatch(nucleo)
    if gasto:
        return (
            f"Logged ${gasto.group(1)} under «{gasto.group(2)}» → "
            f"{_nucleo(gasto.group(3))} ({_nucleo(gasto.group(4))})."
        )
    listo = _RE_LISTO.fullmatch(nucleo)
    if listo:
        return f"Done: it is now in {_nucleo(listo.group(1))} ({_nucleo(listo.group(2))})."
    sobre = _RE_SOBRE.fullmatch(nucleo)
    if sobre:
        return f"Tightest envelope: {sobre.group(1)} {_nucleo(sobre.group(2))} ${sobre.group(3)}"
    luz = _RE_LUZ.fullmatch(nucleo)
    if luz:
        return f"{luz.group(1)} {_nucleo(luz.group(2))}: ${luz.group(3)} of ${luz.group(4)}"
    rojos = _RE_ROJOS.fullmatch(nucleo)
    if rojos:
        nombres = ", ".join(_nucleo(p.strip()) for p in rojos.group(1).split(","))
        return f"Envelopes in the red: {nombres}"
    cuerpo = _RE_CUERPO.fullmatch(nucleo)
    if cuerpo:
        resto = re.sub(r"sueño ([\d.]+) h", r"sleep \1 h", cuerpo.group(1))
        resto = re.sub(r"rutina (.+) días", r"routine \1 days", resto)
        return f"Body: {resto}"
    ayuda = _RE_AREA_AYUDA.fullmatch(nucleo)
    if ayuda:
        return (
            f"The «{_nucleo(ayuda.group(1))}» area is off. "
            "Turn it on in the app, under Account → Settings. I won't list commands."
        )
    apagado = _RE_AREA_OFF.fullmatch(nucleo)
    if apagado:
        return (
            f"The «{_nucleo(apagado.group(1))}» area is off, so I saved nothing. "
            "Turn it on in the app, under Account → Settings."
        )
    areas = re.fullmatch(r"Áreas: (.+)", nucleo)
    if areas and areas.group(1) != "ninguna":
        nombres = ", ".join(_nucleo(p.strip()) for p in areas.group(1).split(","))
        return f"Areas: {nombres}"
    energia = _RE_ENERGIA.fullmatch(nucleo)
    if energia:
        momento = _MOMENTO_EN.get(energia.group(1), energia.group(1))
        return f"Logged {momento} energy at {energia.group(2)}/5."
    bloque = _RE_BLOQUE.fullmatch(nucleo)
    if bloque:
        return f"{bloque.group(1)} {bloque.group(2)} · {_ESTADO_EN.get(bloque.group(3), bloque.group(3))}"
    estado = _RE_ESTADO.fullmatch(nucleo)
    if estado:
        return f"{estado.group(1)}: {_ESTADO_EN.get(estado.group(2), estado.group(2))}."
    return None


def _nucleo_telegram(nucleo: str) -> str:
    nuevo = _nucleo(nucleo)
    if nuevo != nucleo:
        return nuevo
    especial = _caso_telegram(nucleo)
    if especial is not None:
        return especial
    for patron, reemplazo in _PATRONES_TG:
        if patron.fullmatch(nucleo):
            return patron.sub(reemplazo, nucleo)
    if " — " in nucleo:
        izquierda, derecha = nucleo.split(" — ", 1)
        izq = _nucleo_telegram(izquierda)
        der = _nucleo_telegram(derecha)
        if izq != izquierda or der != derecha:
            return f"{izq} — {der}"
    return nucleo


def traducir_plano(texto: str, idioma: str | None = "es") -> str:
    """Texto de Telegram, línea a línea. En español el mensaje no cambia."""
    if normalizar(idioma or "es") != "en" or not texto:
        return texto
    lineas = []
    for linea in texto.split("\n"):
        if not linea.strip():
            lineas.append(linea)
            continue
        lead = linea[: len(linea) - len(linea.lstrip())]
        trail = linea[len(linea.rstrip()) :]
        nucleo = " ".join(linea.split())
        nuevo = _nucleo_telegram(nucleo)
        lineas.append(linea if nuevo == nucleo else f"{lead}{nuevo}{trail}")
    return "\n".join(lineas)


class _Reescritor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.chunks: list[str] = []
        self.skip = 0

    def _flush(self) -> None:
        if not self.chunks:
            return
        raw = "".join(self.chunks)
        self.chunks = []
        if self.skip:
            self.out.append(raw)
            return
        decoded = html.unescape(raw)
        nuevo = traducir_fragmento(decoded)
        if nuevo == decoded:
            self.out.append(raw)
            return
        self.out.append(html.escape(nuevo, quote=False))

    def _emit_start(self, tag: str, attrs) -> None:
        self._flush()
        raw = self.get_starttag_text()
        # El placeholder de un textarea se traduce; el cuerpo (lo que escribió la persona) no.
        traducir_attrs = self.skip == 0 and _atributos_cambiaron(attrs)
        if tag in _SALTAR:
            self.skip += 1
        if traducir_attrs:
            self.out.append(_reconstruir(tag, attrs))
        else:
            self.out.append(raw)

    def handle_starttag(self, tag, attrs) -> None:
        self._emit_start(tag, attrs)

    def handle_startendtag(self, tag, attrs) -> None:
        self._emit_start(tag, attrs)

    def handle_endtag(self, tag) -> None:
        self._flush()
        if tag in _SALTAR and self.skip:
            self.skip -= 1
        self.out.append(f"</{tag}>")

    def handle_data(self, data) -> None:
        self.chunks.append(data)

    def handle_entityref(self, name) -> None:
        self.chunks.append(f"&{name};")

    def handle_charref(self, name) -> None:
        self.chunks.append(f"&#{name};")

    def handle_comment(self, data) -> None:
        self._flush()
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl) -> None:
        self._flush()
        self.out.append(f"<!{decl}>")

    def close(self) -> None:
        super().close()
        self._flush()


def _atributos_cambiaron(attrs) -> bool:
    for clave, valor in attrs:
        if valor is None or (clave not in _ATRIBUTOS and clave not in _ATRIBUTOS_CONFIRM):
            continue
        if _valor_atributo(clave, valor) != valor:
            return True
    return False


def _traducir_confirm(decoded: str) -> str:
    marca = re.fullmatch(r"return confirm\('(.*)'\)", decoded)
    if not marca:
        return decoded
    nuevo = traducir_fragmento(marca.group(1))
    if nuevo == marca.group(1) or "'" in nuevo or "\\" in nuevo:
        return decoded
    return f"return confirm('{nuevo}')"


def _valor_atributo(clave: str, valor: str) -> str:
    decoded = html.unescape(valor)
    if clave in _ATRIBUTOS_CONFIRM:
        nuevo = _traducir_confirm(decoded)
    elif clave in _ATRIBUTOS:
        nuevo = traducir_fragmento(decoded)
    else:
        return valor
    if nuevo == decoded:
        return valor
    return html.escape(nuevo, quote=True)


def _reconstruir(tag: str, attrs) -> str:
    partes = [f"<{tag}"]
    for clave, valor in attrs:
        if valor is None:
            partes.append(f" {clave}")
            continue
        shown = (
            _valor_atributo(clave, valor)
            if clave in _ATRIBUTOS or clave in _ATRIBUTOS_CONFIRM
            else valor
        )
        partes.append(f' {clave}="{shown}"')
    partes.append(">")
    return "".join(partes)


def traducir_html(documento: str) -> str:
    try:
        parser = _Reescritor()
        parser.feed(documento)
        parser.close()
        salida = "".join(parser.out)
    except Exception:
        return documento
    if "<html" in documento.lower() and "<html" not in salida.lower():
        return documento
    return salida or documento


def aplicar_cookie_idioma(response, idioma: str) -> None:
    response.set_cookie(
        COOKIE,
        normalizar(idioma),
        max_age=_MAX_AGE,
        httponly=False,
        samesite="lax",
        path="/",
    )


def idioma_efectivo(request, user: dict | None) -> str:
    """La preferencia guardada gana a la cookie. Sin ninguna, español."""
    if user and user.get("id") is not None:
        try:
            from app.cuenta import idioma_guardado

            guardado = idioma_guardado(int(user["id"]))
            if guardado:
                return guardado
        except Exception:
            pass
    try:
        cookie = request.cookies.get(COOKIE)
    except Exception:
        cookie = None
    if cookie:
        return normalizar(cookie)
    return "es"
