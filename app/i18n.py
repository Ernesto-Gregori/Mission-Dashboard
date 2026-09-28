"""Idioma de la interfaz. Español es el origen; inglés se aplica al HTML ya renderizado."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

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
    "Sandbox",
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
    "Vida": "Life",
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
    "Proyectos y snippets.": "Projects and snippets.",
    "Proyectos y notas sueltas.": "Projects and loose notes.",
    "Ingreso, gastos y vencimientos.": "Income, expenses, and bills.",
    "Bloques de trabajo concentrado.": "Blocks of focused work.",
    "Una práctica para cuidar lo que te sostiene.": "A practice for what sustains you.",
    "Personas que quieres cuidar: pareja, familia o amigos.": "People you want to care for: partner, family, or friends.",
    # Configuración
    "Nombres, áreas y el día a día. Apagar un área lo esconde y deja tus registros donde están.": "Names, areas, and the day to day. Turning an area off hides it and leaves your records in place.",
    "Áreas": "Areas",
    "Nombre en tu cuenta": "Name on your account",
    "Vacío usa el nombre neutro": "Empty uses the neutral name",
    "Todavía no hay áreas. Hoy, Semana y Cuenta siguen disponibles.": "No areas yet. Today, Week, and Account stay available.",
    "Mostrar snippets dentro de Ideas": "Show snippets inside Ideas",
    "Día y asistente": "Day and assistant",
    "Ritual": "Ritual",
    "Gratitud e intención en Hoy": "Gratitude and intention on Today",
    "Rueda de la vida": "Life wheel",
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
    "Módulos": "Modules",
    "Ningún módulo activo.": "No active module.",
    "Abrir configuración": "Open settings",
    "para renombrar, apagar o cambiar el ritual sin pasar por el coach.": "to rename, turn off, or change the ritual without the coach.",
    "✏️ Cambiar módulos con el coach": "✏️ Change modules with the coach",
    "Plan Free: el Coach IA de setup es una sola vez.": "Free plan: the AI setup coach runs once.",
    "Desbloquear reconfiguración (Premium)": "Unlock reconfiguration (Premium)",
    "Disponibles en Premium": "Available on Premium",
    "Upgrade": "Upgrade",
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
    "Conectar en Salud": "Connect in Health",
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
    "Módulos ilimitados": "Unlimited modules",
    "Coach reconfigurable": "Coach can be reconfigured",
    "Briefings diarios": "Daily briefings",
    "Google Fit / Calendar": "Google Fit / Calendar",
    "Error": "Error",
    "usuario": "user",
    "admin": "admin",
}

_PATRONES = (
    (re.compile(r"^(\d+) módulos activos$"), r"\1 active modules"),
    (re.compile(r"^Archivados \((\d+)\)$"), r"Archived (\1)"),
    (re.compile(r"^Demasiados intentos\. Espera (\d+)s\.$"), r"Too many attempts. Wait \1s."),
)

_ATRIBUTOS = {"placeholder", "aria-label", "title", "alt"}
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
    titulo = re.fullmatch(r"(.+) · Mission", texto)
    if titulo:
        interno = _nucleo(titulo.group(1))
        if interno != titulo.group(1):
            return f"{interno} · Mission"
    return texto


def traducir_fragmento(texto: str) -> str:
    if not texto or not texto.strip():
        return texto
    lead = texto[: len(texto) - len(texto.lstrip())]
    trail = texto[len(texto.rstrip()) :]
    nucleo = texto.strip()
    nuevo = _nucleo(nucleo)
    if nuevo == nucleo:
        return texto
    return f"{lead}{nuevo}{trail}"


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
        if tag in _SALTAR:
            self.skip += 1
        if self.skip == 0 and _atributos_cambiaron(attrs):
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
        if valor is None or clave not in _ATRIBUTOS:
            continue
        decoded = html.unescape(valor)
        if traducir_fragmento(decoded) != decoded:
            return True
    return False


def _reconstruir(tag: str, attrs) -> str:
    partes = [f"<{tag}"]
    for clave, valor in attrs:
        if valor is None:
            partes.append(f" {clave}")
            continue
        shown = valor
        if clave in _ATRIBUTOS:
            decoded = html.unescape(valor)
            nuevo = traducir_fragmento(decoded)
            if nuevo != decoded:
                shown = html.escape(nuevo, quote=True)
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
