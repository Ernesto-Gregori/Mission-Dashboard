# Diagnóstico Mission Dashboard

## Veredicto

**No hace falta migrar a Electron ahora.** Los tres problemas que reportas (recarga, finanzas que no guardan, sin usuarios) se explican por limitaciones y bugs de la app Streamlit actual. Electron cambiaría el empaquetado, no arreglaría solo la persistencia ni el login.

---

## 1. “Cada cambio recarga”

Eso es comportamiento normal de **Streamlit**: cada clic, slider o input vuelve a ejecutar el script de arriba a abajo. No es un bug de tu lógica.

| Opción | Cuándo tiene sentido |
|--------|----------------------|
| Quedarte en Streamlit + usar más `st.form` / `session_state` | App personal, iterar rápido |
| NiceGUI / Flet (sigue siendo Python) | Quieres UI más “app” sin recargas totales |
| Electron + React/Vue | Solo si quieres app de escritorio nativa y aceptas reescribir casi todo |

**Recomendación:** no reescribir a Electron por este síntoma. Mitigar con formularios y menos widgets fuera de `st.form`.

---

## 2. Finanzas “no guarda bien” (bug real)

Hay **dos caminos de base de datos**:

- El resto de módulos usan `ejecutar()` → SQLite local **o Turso** según secrets.
- Finanzas (`guardar_ingreso`, `agregar_gasto_sobre`, etc.) abría `sqlite3.connect(data/mission.db)` **siempre**.

Consecuencias:

1. Si configuraste Turso, Agenda/Salud/etc. van a la nube y **Finanzas escribe en un `.db` local** que en Streamlit Cloud / contenedores **se borra** al reiniciar.
2. Tras migrar a Turso, los gastos parecen “guardados” en local pero desaparecen o no coinciden con el resto.
3. Tras guardar un gasto nuevo no siempre se forzaba un refresco claro del resumen.

**Fix en este PR:** todas las operaciones de finanzas pasan por `ejecutar()` (misma BD que el resto).

---

## 3. Usuarios y contraseña (bug + diseño incompleto)

Estado anterior:

- Solo una contraseña plana en `st.secrets["APP_PASSWORD"]`.
- **No hay creación de usuarios** en la UI.
- El login solo estaba en `Mission_Dashboard.py`.
- Las páginas (`/Finanzas`, `/Agenda`, …) **no llamaban a auth** → se podían abrir sin pasar por el login.
- Si `APP_PASSWORD` no existía, la contraseña correcta era `""` (entrar con campo vacío).

**Fix en este PR:**

- Tabla `usuarios` con hash PBKDF2 (no texto plano).
- Primer arranque: pantalla para crear el usuario admin.
- Login con usuario + contraseña en **todas** las páginas.
- Panel para crear más usuarios (solo admin autenticado).
- Compatibilidad opcional con `APP_PASSWORD` solo si aún no hay usuarios en BD.

---

## 4. ¿Dónde crear usuarios? (Streamlit actual)

1. Entra con un usuario **admin** (si migraste desde secrets: usuario `admin` + tu `APP_PASSWORD`).
2. En el menú lateral abre **Usuarios** (`pages/09_Usuarios.py`).
3. O en la home: enlace «Crear / gestionar usuarios» (sidebar) / sección al final del dashboard.

Si no ves esa página, redeploy/pull de `main` — el código viejo no la tenía.

## 5. NiceGUI / Flet vs Streamlit Cloud

**Streamlit Community Cloud NO ejecuta NiceGUI ni Flet.** Solo apps Streamlit.

| Opción | ¿Sigue en Streamlit Cloud? | Qué implica |
|--------|----------------------------|-------------|
| Quedarte en Streamlit | Sí | Sin recargas “tipo app”, pero hosting igual |
| Migrar a NiceGUI o Flet | **No** | Hay que hospedar en Railway, Fly.io, Render, VPS, etc. |
| Electron | No (es escritorio) | Reescritura grande; no es hosting web |

Si el sitio está en Streamlit Cloud hoy:

- **Puedes** mejorar auth/finanzas ahí (lo que ya hicimos).
- **No puedes** “cambiar solo el framework” y seguir en el mismo hosting Streamlit.
- Para NiceGUI/Flet hay que **cambiar de hosting** y reescribir la UI (la capa `app/database.py`, IA y Google sí se reutilizan).

Recomendación: mientras el deploy sea Streamlit Cloud, **seguir en Streamlit** y usar la página Usuarios. Valorar NiceGUI solo si aceptas mover el hosting.

## 6. ¿Cuándo sí valdría Electron?

Solo si necesitas:

- App instalable en Windows/Mac sin navegador.
- Offline fuerte + archivo local garantizado.
- UI tipo desktop (ventanas, menús nativos).

Coste: reescribir frontend, auth, y capa de datos. La lógica de Python (IA, Google, sobres) se puede reutilizar vía API, pero no es un “cambio de empaquetado”.

---

## 7. Estabilidad Streamlit (recargas)

Mitigaciones ya aplicadas (seguir en Streamlit):

- `ensure_database()` — schema una vez por sesión
- `invalidate_data_caches()` — tras guardar, la UI no queda 30s desfasada
- Finanzas: período/ingreso en `st.form`; historial en `st.fragment`
- Agenda bitácora: formulario completo (escribir sin recargar)
- Deep Work: marcar sesión en `st.form` dentro del popover
- Dashboard: hábitos nuevos y chat IA en forms; seed de hábitos 1×/día
- `calcular_sobres` cacheado

Streamlit **siempre** re-ejecuta el script en interacciones fuera de form/fragment; no se puede eliminar al 100% sin cambiar de framework.

## 8. Google Fit se desconecta al “dormir”

Causa: Streamlit Cloud borra el disco → `token_fit.json` desaparece.  
Si solo había access token en secrets (sin `refresh_token`), hay que volver a vincular.

**Fix:** tokens en tabla `oauth_tokens` (Turso). Tras conectar una vez, debe decir «token en BD».

También: apps OAuth en modo Testing de Google caducan el refresh ~7 días.

## 9. Groq por módulo

Bug corregido: `chat_simple(..., contexto=SYSTEM_X)` **ignoraba** el system prompt del módulo y siempre usaba el genérico. Ahora cada módulo (Finanzas, Salud, Agenda, Deep Work, etc.) envía su propio contexto a Groq.

## 11. Multi-usuario (cada quien su sistema)

Antes todos compartían las mismas tablas. Ahora:

- Columna `user_id` en tablas de negocio
- CRUD filtrado por `app.tenant.uid()`
- Tokens Google Fit por usuario
- Migración automática en `ensure_database()`

## 12. Coach IA + plantillas

Usuarios nuevos (sin módulos activos) ven el **Coach** al primer login:

1. Perfil (situación, objetivos, áreas)
2. Groq sugiere 3–6 módulos + hábitos (fallback por reglas si no hay API key)
3. El usuario confirma → `user_modulos` + `habitos_config`

Admin/legacy con módulos ya activos se marca `onboarding_completo=1` y no ve el coach.
Dashboard y nav muestran solo módulos activos; se puede reconfigurar desde el expander Coach.

---

## Roadmap

1. ~~Unificar finanzas con `ejecutar()` / Turso~~
2. ~~Auth real + proteger todas las páginas~~
3. ~~Página visible Usuarios~~
4. ~~Forms / fragments / cache para recargas~~
5. ~~Multi-usuario~~
6. ~~Coach IA + plantillas~~
7. Confirmar Turso / secrets y redeploy en Streamlit Cloud
8. NiceGUI/Flet **solo** si cambias de hosting (no compatible con Streamlit Cloud)

---

## Checklist post-deploy

- [ ] Crear el primer usuario en la pantalla de setup
- [ ] Completar el Coach IA (o confirmar que admin legacy ya tiene módulos)
- [ ] Crear un segundo usuario y verificar que ve el coach y datos aislados
- [ ] Verificar que un gasto en Finanzas aparece tras recargar / en otro dispositivo (si usas Turso)
- [ ] Confirmar que abrir `/Finanzas` sin login pide autenticación
- [ ] Hacer backup de `data/mission.db` antes de migrar a Turso
