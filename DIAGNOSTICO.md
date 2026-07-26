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

## 4. ¿Cuándo sí valdría Electron?

Solo si necesitas:

- App instalable en Windows/Mac sin navegador.
- Offline fuerte + archivo local garantizado.
- UI tipo desktop (ventanas, menús nativos).

Coste: reescribir frontend, auth, y capa de datos. La lógica de Python (IA, Google, sobres) se puede reutilizar vía API, pero no es un “cambio de empaquetado”.

---

## 5. Plan sugerido (prioridad)

1. ~~Unificar finanzas con `ejecutar()` / Turso~~ (este PR)
2. ~~Auth real + proteger todas las páginas~~ (este PR)
3. Confirmar en `.streamlit/secrets.toml` (o `.env`): `TURSO_URL`, `TURSO_TOKEN`, y opcionalmente migrar con `migrar_local_a_turso()`
4. Reducir recargas molestas con más `st.form` en páginas grandes
5. Evaluar NiceGUI/Flet solo si la UX de Streamlit sigue siendo insuficiente

---

## Checklist post-deploy

- [ ] Crear el primer usuario en la pantalla de setup
- [ ] Verificar que un gasto en Finanzas aparece tras recargar / en otro dispositivo (si usas Turso)
- [ ] Confirmar que abrir `/Finanzas` sin login pide autenticación
- [ ] Hacer backup de `data/mission.db` antes de migrar a Turso
