"""Frases del bot. El español es el texto de origen; esto solo se aplica si el idioma es inglés.

Los comandos (/gasto, /ayuda finanzas) y los ejemplos que el parser reconoce se quedan
igual: si se traducen, el usuario los manda y el bot no los entiende.
"""

FRASES = {
    # Menú y vínculo
    "Menú:": "Menu:",
    "• /briefing — foco del día": "• /briefing — focus for the day",
    "• /gasto 35 super — anotar un gasto": "• /gasto 35 super — log an expense",
    "• /deshacer — lo último que guardé": "• /deshacer — the last thing I saved",
    "• /ayuda finanzas — también agenda, salud, enfoque, lectura, fe, pareja, habitos, alma": (
        "• /ayuda finanzas — also agenda, salud, enfoque, lectura, fe, pareja, habitos, alma"
    ),
    "Texto suelto («35 en super») o una nota de voz también sirven.": (
        "Free text («35 en super») or a voice note also works."
    ),
    "Desvincular: en la app → Usuarios → Telegram.": "Unlink: in the app → Users → Telegram.",
    "Este chat no está vinculado a Mission Dashboard.": "This chat is not linked to Mission Dashboard.",
    "Entrá a la app → Usuarios → Telegram, generá un código y pulsá Start (o mandá el código de 6 dígitos).": (
        "Open the app → Users → Telegram, generate a code and tap Start (or send the 6-digit code)."
    ),
    "Este Telegram no está vinculado a Mission Dashboard. Entrá a la app → Usuarios → Telegram, generá un código y pulsá Start en el bot (o mandá el código de 6 dígitos). /ayuda cuenta qué puede hacer el bot.": (
        "This Telegram is not linked to Mission Dashboard. Open the app → Users → Telegram, generate a code and tap Start on the bot (or send the 6-digit code). /ayuda lists what the bot can do."
    ),
    "Tu cuenta está inactiva.": "Your account is inactive.",
    "Telegram requiere plan Premium o Familia. Activalo en /app/billing — no ejecuté ninguna acción.": (
        "Telegram requires a Premium or Family plan. Turn it on at /app/billing — I did not run anything."
    ),
    "No pude transcribir el audio. Probá en texto o /ayuda.": "I couldn't transcribe the audio. Try text or /ayuda.",
    "Hubo un error procesando el mensaje. No se guardó nada.": "There was an error processing the message. Nothing was saved.",
    "No entendí, así que no guardé nada.": "I didn't understand, so I saved nothing.",
    "Probá: «35 en super», «/tarea mañana 5pm llamar al banco» o /briefing.": (
        "Try: «35 en super», «/tarea mañana 5pm llamar al banco» or /briefing."
    ),
    "/ayuda muestra todos los comandos.": "/ayuda lists every command.",
    "Ya estás vinculado.": "You are already linked.",
    "Ese tema no tiene comandos.": "That topic has no commands.",
    "No conozco ese tema. Probá /ayuda finanzas, agenda, salud, enfoque, lectura, fe, pareja, habitos o alma.": (
        "I don't know that topic. Try /ayuda finanzas, agenda, salud, enfoque, lectura, fe, pareja, habitos or alma."
    ),
    "Ese módulo no tiene comandos.": "That module has no commands.",
    "Chat inválido.": "Invalid chat.",
    "Ese Telegram ya está vinculado a otra cuenta.": "That Telegram is already linked to another account.",
    "Listo, Telegram vinculado.": "Done, Telegram is linked.",
    "No se pudo guardar el vínculo.": "The link could not be saved.",
    "Código generado. Vence en 10 minutos.": "Code generated. It expires in 10 minutes.",
    "Ese botón ya no sirve. No guardé nada.": "That button no longer works. I saved nothing.",
    "Ese botón ya no sirve. No cambié nada.": "That button no longer works. I changed nothing.",
    "Esa confirmación ya no está disponible. No guardé nada.": "That confirmation is no longer available. I saved nothing.",
    "Cancelado. No guardé nada.": "Cancelled. I saved nothing.",
    "¿Error? /deshacer": "Wrong? /deshacer",
    # Comandos del menú /
    "Vincular o ver el menú": "Link or see the menu",
    "Foco del día": "Focus for the day",
    "Lo mismo que /briefing": "Same as /briefing",
    "Anotar un gasto. Ej: /gasto 35 super": "Log an expense. E.g. /gasto 35 super",
    "Ingreso, gastado y disponible": "Income, spent and available",
    "Agenda de hoy, mañana o la semana": "Calendar for today, tomorrow or the week",
    "Crear una tarea": "Create a task",
    "Deshacer lo último que guardé": "Undo the last thing I saved",
    "Menú, o /ayuda y un módulo": "Menu, or /ayuda plus a module",
    # Botones
    "💸 Saldo": "💸 Balance",
    "✅ Hábitos": "✅ Habits",
    "❓ Ayuda": "❓ Help",
    "✅ Sí": "✅ Yes",
    "✖️ No": "✖️ No",
    # Ayuda por módulo (el uso, suelto o detrás de « — »)
    "Usá /silencio, /silencio 3 o /silencio 0 para reanudar.": "Use /silencio, /silencio 3, or /silencio 0 to resume.",
    "Decime cuál. Ejemplo: /hecho leer  (o «ya leí»).": "Tell me which one. Example: /hecho leer  (or «ya leí»).",
    "Escribí el mensaje. Ejemplo: /alma cómo viene mi semana": "Write the message. Example: /alma cómo viene mi semana",
    "Escribí la nota. Ejemplo: /nota le gusta el café de la esquina": (
        "Write the note. Example: /nota le gusta el café de la esquina"
    ),
    "Decime los minutos. Ejemplo: /conexion 30": "Tell me the minutes. Example: /conexion 30",
    "Usá un título y hora. Ejemplo: /tarea mañana 5pm llamar al banco.": (
        "Use a title and a time. Example: /tarea mañana 5pm llamar al banco."
    ),
    "Primero /agenda, después /mover 2 18:00.": "First /agenda, then /mover 2 18:00.",
    "Primero /agenda, después /cancelar 2.": "First /agenda, then /cancelar 2.",
    "Usá un monto. Ejemplo: /gasto 35 super  (o «35 en supermercado»).": (
        "Use an amount. Example: /gasto 35 super  (or «35 en supermercado»)."
    ),
    "Usá un monto. Ejemplo: /ingreso 800": "Use an amount. Example: /ingreso 800",
    "Primero /gastos, después /borrar 2.": "First /gastos, then /borrar 2.",
    "Decime el producto. Ejemplo: /precio leche": "Tell me the product. Example: /precio leche",
    "Escribí el pedido. Ejemplo: /orar salud de mamá": "Write the request. Example: /orar salud de mamá",
    "Primero /oraciones, después /respondida 1.": "First /oraciones, then /respondida 1.",
    "Decime el libro y la página. Ejemplo: /leer El Hobbit 40": (
        "Tell me the book and the page. Example: /leer El Hobbit 40"
    ),
    "Usá las horas. Ejemplo: /sueno 7.5 calidad 4": "Use the hours. Example: /sueno 7.5 calidad 4",
    "Usá un número del 1 al 5. Ejemplo: /energia 4  o  /energia tarde 3": (
        "Use a number from 1 to 5. Example: /energia 4  or  /energia tarde 3"
    ),
    "Decime qué hiciste. Ejemplo: /ejercicio pierna 45 min": "Tell me what you did. Example: /ejercicio pierna 45 min",
    # Briefing y hábitos
    "Agenda: sin eventos.": "Calendar: no events.",
    "Hábitos: al día.": "Habits: all done.",
    "Enfoque: sin bloques hoy.": "Focus: no blocks today.",
    "Vencimientos: ninguno en 3 días.": "Due dates: none in the next 3 days.",
    "Oración: nada para hoy.": "Prayer: nothing for today.",
    "Pareja: sin cita hoy.": "Pareja: no date today.",
    "Salud: sin registro hoy.": "Health: no log today.",
    "Listo: el briefing de la mañana vuelve cuando le toque.": "Done: the morning briefing returns on its next slot.",
    "No tenés hábitos activos. Se crean en la app, en Coach.": "You have no active habits. They are created in the app, under Coach.",
    "Hábitos de hoy": "Today's habits",
    "Para marcar: /hecho leer  (o «ya leí»).": "To check one off: /hecho leer  (or «ya leí»).",
    "Ese hábito ya no está. No marqué nada.": "That habit is gone. I checked nothing off.",
    # Finanzas, agenda, salud y el resto de las respuestas fijas
    "No estaba claro el rubro; usé el de por defecto. Tocá para cambiarlo.": (
        "The category was unclear; I used the default. Tap to change it."
    ),
    "Ese rubro no existe. No cambié nada.": "That category does not exist. I changed nothing.",
    "No encontré ese gasto. No cambié nada.": "I couldn't find that expense. I changed nothing.",
    "No pude guardar el ingreso.": "I couldn't save the income.",
    "No hay gastos anotados.": "No expenses logged.",
    "Últimos gastos. /borrar <n>": "Latest expenses. /borrar <n>",
    "No encuentro ese número. Mandá /gastos y usá el de la lista.": (
        "I can't find that number. Send /gastos and use one from the list."
    ),
    "No pude borrar ese gasto.": "I couldn't delete that expense.",
    "No encuentro ese número. Mandá /agenda primero.": "I can't find that number. Send /agenda first.",
    "No pude mover ese evento.": "I couldn't move that event.",
    "No pude cancelar ese evento.": "I couldn't cancel that event.",
    "El catálogo de precios está vacío. No hay nada que comparar.": "The price catalog is empty. There is nothing to compare.",
    "No hay pedidos activos. Ejemplo: /orar salud de mamá": "No active requests. Example: /orar salud de mamá",
    "Oraciones": "Prayers",
    "Para cerrar uno: /respondida 1": "To close one: /respondida 1",
    "Ese número no está en la lista. Mirá /oraciones. No cambié nada.": (
        "That number is not on the list. See /oraciones. I changed nothing."
    ),
    "No pude actualizar el pedido. No cambié nada.": "I couldn't update the request. I changed nothing.",
    "No pude guardar el pedido. No escribí nada.": "I couldn't save the request. I wrote nothing.",
    "Hoy no tenés bloques de enfoque. Se arman en la app → Enfoque.": (
        "You have no focus blocks today. They are set up in the app → Focus."
    ),
    "Enfoque de hoy": "Focus today",
    "✓ Completado · ~ Parcial · → Postergado": "✓ Done · ~ Partial · → Postponed",
    "No pude guardar el estado.": "I couldn't save the status.",
    "Ese bloque no es de hoy. No cambié nada.": "That block is not from today. I changed nothing.",
    "No pude anotar el sueño.": "I couldn't log sleep.",
    "No pude anotar la energía.": "I couldn't log energy.",
    "No pude anotar el ejercicio.": "I couldn't log the workout.",
    "Todavía no hay registros de salud en los últimos 7 días.": "There are no health logs in the last 7 days yet.",
    "No tenés una rutina guardada. Se arma en la app, en Salud.": (
        "You have no saved routine. It is set up in the app, under Health."
    ),
    "No estás leyendo ningún libro. Se marcan en la app, en Biblioteca.": (
        "You are not reading any book. They are marked in the app, under Library."
    ),
    "Leyendo": "Reading",
    "Para avanzar: /leer el título y la página.": "To update progress: /leer plus the title and the page.",
    "Esa lista ya no está. Mandá /leer de nuevo. No cambié nada.": (
        "That list is gone. Send /leer again. I changed nothing."
    ),
    "Ese libro ya no está. No cambié nada.": "That book is gone. I changed nothing.",
    "No pude guardar la página. No cambié nada.": "I couldn't save the page. I changed nothing.",
    "La foto supera 5 MB. No leí nada.": "The photo is over 5 MB. I read nothing.",
    "No pude bajar la foto. No leí nada.": "I couldn't download the photo. I read nothing.",
    "Se agotó el cupo de IA de este mes. No leí el recibo.": "This month's AI allowance is used up. I didn't read the receipt.",
    "No pude guardar la foto. No leí nada.": "I couldn't save the photo. I read nothing.",
    "No hay categorías autorizadas. Se activan en la app, en Alma. El bot no puede prenderlas.": (
        "No categories are authorized. They are turned on in the app, under Assistant. The bot cannot turn them on."
    ),
    "Google: vinculado": "Google: linked",
    "Google: sin vincular": "Google: not linked",
    "Módulos: ninguno": "Modules: none",
}

# Patrones de una línea. Lo que está entre paréntesis es dato del usuario y se conserva.
PATRONES = [
    (r"^Foco (\d{4}-\d{2}-\d{2})$", r"Focus \1"),
    (r"^Agenda de hoy: nada anotado\.$", "Calendar for today: nothing scheduled."),
    (r"^Agenda de mañana: nada anotado\.$", "Calendar for tomorrow: nothing scheduled."),
    (r"^Agenda de la semana: nada anotado\.$", "Calendar for the week: nothing scheduled."),
    (r"^Agenda de hoy\. /mover <n> o /cancelar <n>$", "Calendar for today. /mover <n> or /cancelar <n>"),
    (r"^Agenda de mañana\. /mover <n> o /cancelar <n>$", "Calendar for tomorrow. /mover <n> or /cancelar <n>"),
    (r"^Agenda de la semana\. /mover <n> o /cancelar <n>$", "Calendar for the week. /mover <n> or /cancelar <n>"),
    (r"^(\d+)\. (\d{4}-\d{2}-\d{2}) sin hora (.+)$", r"\1. \2 no time \3"),
    (r"^Hábitos pendientes: (.+)$", r"Habits still open: \1"),
    (r"^Enfoque: (\d+)/(\d+) bloques$", r"Focus: \1/\2 blocks"),
    (r"^Enfoque: (.+)$", r"Focus: \1"),
    (r"^Vencimientos: (.+)$", r"Due dates: \1"),
    (r"^Agenda: (.+)$", r"Calendar: \1"),
    (r"^Oración: (.+)$", r"Prayer: \1"),
    (r"^Pareja: (.+)$", r"Pareja: \1"),
    (r"^Saldo (\d{2}/\d{4})$", r"Balance \1"),
    (r"^Ingreso de (\d{2}/\d{4}): \$(\d+)\.$", r"Income for \1: $\2."),
    (r"^Ingreso \$(\d+)$", r"Income $\1"),
    (r"^Gastado \$(\d+)$", r"Spent $\1"),
    (r"^Disponible \$(\d+)$", r"Available $\1"),
    (r"^Semana del (\d{4}-\d{2}-\d{2})$", r"Week of \1"),
    (r"^Ejercicio: (\d+) días$", r"Exercise: \1 days"),
    (r"^Energía: (.+)$", r"Energy: \1"),
    (r"^Leyendo: (.+)$", r"Reading: \1"),
    (r"^Coach: sin tope\.$", "Coach: no cap."),
    (r"^Coach: (\d+)/(\d+) esta semana\.$", r"Coach: \1/\2 this week."),
    (r"^Coach \(sin tope\)$", "Coach (no cap)"),
    (r"^Coach \((\d+)/(\d+) esta semana\)$", r"Coach (\1/\2 this week)"),
    (r"^Plan: (.+)$", r"Plan: \1"),
    (r"^Llamadas de IA este mes: (\d+)$", r"AI calls this month: \1"),
    (r"^Más baratos para «(.+)»$", r"Cheapest for «\1»"),
    (r"^No encontré «(.+)» en el catálogo\.$", r"I couldn't find «\1» in the catalog."),
    (r"^No encontré un hábito para «(.+)»\. Mirá /habitos\. No marqué nada\.$", (
        r"I couldn't find a habit for «\1». See /habitos. I checked nothing off."
    )),
    (r"^«(.+)» coincide con varios\. ¿Cuál, en la página (\d+)\?$", r"«\1» matches several. Which one, on page \2?"),
    (r"^«(.+)» coincide con varios\. ¿Cuál\?$", r"«\1» matches several. Which one?"),
    (r"^✓ (.+)\. Los otros hábitos de hoy siguen como estaban\.$", r"✓ \1. The other habits for today stay as they were."),
    (r"^Anoté \$([0-9.]+) en «(.+)»\.$", r"Logged $\1 under «\2»."),
    (r"^Leí \$([0-9.]+) en «(.+)»\.$", r"I read $\1 at «\2»."),
    (r"^Vas a anotar \$([0-9.]+) en «(.+)»\. Es un monto alto\.$", r"You are about to log $\1 under «\2». That is a large amount."),
    (r"^Vas a anotar \$([0-9.]+) en «(.+)»\. Deja el sobre en negativo\.$", (
        r"You are about to log $\1 under «\2». It would put the envelope below zero."
    )),
    (r"^Este mes ya tiene un ingreso de \$(\d+)\. ¿Lo reemplazo por \$(\d+)\?$", (
        r"This month already has income of $\1. Replace it with $\2?"
    )),
    (r"^¿Borro el gasto (\d+)\? No se puede deshacer\.$", r"Delete expense \1? This cannot be undone."),
    (r"^Borré el gasto (\d+)\.$", r"Deleted expense \1."),
    (r"^¿Muevo el (\d+) a las (\d{2}:\d{2})\?$", r"Move \1 to \2?"),
    (r"^Moví el (\d+) a las (\d{2}:\d{2})\.$", r"Moved \1 to \2."),
    (r"^¿Cancelo el (\d+)\? También se borra en Google Calendar si estaba vinculado\.$", (
        r"Cancel \1? It is also deleted in Google Calendar if it was linked."
    )),
    (r"^Cancelé el (\d+)\.$", r"Cancelled \1."),
    (r"^Silencio hasta el (\d{4}-\d{2}-\d{2}) inclusive\. /silencio 0 lo reanuda\.$", (
        r"Quiet until \1 inclusive. /silencio 0 resumes it."
    )),
    (r"^¿Lo guardo\? Tocá un botón o respondé «sí» / «no» \(vence en (\d+) min\)\.$", (
        r"Save it? Tap a button or reply yes / no (expires in \1 min)."
    )),
    (r"^Esa confirmación venció \((\d+) min\)\. No guardé nada; mandalo de nuevo\.$", (
        r"That confirmation expired (\1 min). I saved nothing; send it again."
    )),
    (r"^No hay nada para deshacer \(solo la última acción, hasta (\d+) min\)\.$", (
        r"There is nothing to undo (only the last action, within \1 min)."
    )),
    (r"^No pude deshacer: (.+)\. Revisalo en la app\.$", r"I couldn't undo: \1. Check it in the app."),
    (r"^Deshice: (.+)\.$", r"Undid: \1."),
    (r"^⏰ Recordatorio: (\d{2}:\d{2}) · (.+)\.$", r"⏰ Reminder: \1 · \2."),
    (r"^⏰ Recordatorio: (.+)\.$", r"⏰ Reminder: \1."),
    (r"^Anoté la nota: «(.+)»\.$", r"Logged the note: «\1»."),
    (r"^Anoté (\d+) min de conexión\.$", r"Logged \1 min of connection."),
    (r"^Anoté el pedido «(.+)»\.$", r"Logged the request «\1»."),
    (r"^Anoté ([0-9.]+) h de sueño, calidad (\d)/5\. El resto del día quedó igual\.$", (
        r"Logged \1 h of sleep, quality \2/5. The rest of the day stays as it was."
    )),
    (r"^Anoté ([0-9.]+) h de sueño\. El resto del día quedó igual\.$", (
        r"Logged \1 h of sleep. The rest of the day stays as it was."
    )),
    (r"^Anoté ejercicio: (.+), (\d+) min\.$", r"Logged workout: \1, \2 min."),
    (r"^Anoté ejercicio: (.+)\.$", r"Logged workout: \1."),
    (r"^📖 (.+), página (\d+)\.$", r"📖 \1, page \2."),
    (r"^No encontré «(.+)»\. Mirá /leyendo\. No cambié nada\.$", r"I couldn't find «\1». See /leyendo. I changed nothing."),
    (r"^¿Marco el pedido (\d+) como respondido\?$", r"Mark request \1 as answered?"),
    (r"^Marqué «(.+)» como respondido\.$", r"Marked «\1» as answered."),
    (r"^No conozco el dominio «(.+)»\. No guardé nada\. Usá: (.+)\.$", r"I don't know the area «\1». I saved nothing. Use: \2."),
    (r"^Salud, últimos (\d+) días con registro$", r"Health, last \1 days with a log"),
    (r"^Sueño ([0-9.]+) h · calidad ([0-9.]+)$", r"Sleep \1 h · quality \2"),
    (r"^Energía mañana ([0-9.]+)/5$", r"Morning energy \1/5"),
    (r"^Ejercicio (\d+) días$", r"Exercise \1 days"),
    (r"^Racha del objetivo: (\d+) días$", r"Goal streak: \1 days"),
    (r"^Rutina: (.+) días · (.+) min$", r"Routine: \1 days · \2 min"),
]
