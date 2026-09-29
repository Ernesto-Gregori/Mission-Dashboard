/**
 * Timeline drag & drop for /app/planificador.
 * Pointer events + form POST (no extra frameworks).
 */
(function () {
  const grid = document.querySelector("[data-planner-grid]");
  const month = document.querySelector(".tl-month");
  const form = document.getElementById("planner-move");
  if (!form) return;

  function submitMove(id, fecha, start, end) {
    form.evento_id.value = id;
    form.fecha.value = fecha || "";
    form.hora_inicio.value = start || "";
    form.hora_fin.value = end || "";
    form.submit();
  }

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function minsToHm(total) {
    const h = Math.floor(total / 60);
    const m = total % 60;
    return pad(h) + ":" + pad(m);
  }

  function parseHm(value) {
    if (!value) return null;
    const parts = String(value).split(":");
    const h = Number(parts[0]);
    const m = Number((parts[1] || "0").slice(0, 2));
    if (Number.isNaN(h)) return null;
    return h * 60 + (Number.isNaN(m) ? 0 : m);
  }

  function shiftIso(iso, days) {
    const parts = String(iso || "").split("-");
    if (parts.length < 3) return "";
    const y = Number(parts[0]);
    const m = Number(parts[1]);
    const d = Number(parts[2]);
    if (!y || !m || !d) return "";
    const next = new Date(y, m - 1, d + days);
    return next.getFullYear() + "-" + pad(next.getMonth() + 1) + "-" + pad(next.getDate());
  }

  document.addEventListener("keydown", function (ev) {
    const block = ev.target && ev.target.closest ? ev.target.closest("button[data-event-id]") : null;
    if (!block) return;
    const key = ev.key;
    const up = key === "ArrowUp";
    const down = key === "ArrowDown";
    const left = key === "ArrowLeft";
    const right = key === "ArrowRight";
    if (!up && !down && !left && !right) return;
    const id = block.getAttribute("data-event-id");
    if (!id) return;
    const allday = block.getAttribute("data-allday") === "1" || !parseHm(block.getAttribute("data-start"));
    if ((up || down) && allday) return;
    ev.preventDefault();
    const fecha0 = block.getAttribute("data-fecha") || "";
    if (left || right) {
      const fecha = shiftIso(fecha0, left ? -1 : 1);
      if (!fecha || fecha === fecha0) return;
      if (allday) submitMove(id, fecha, "", "");
      else submitMove(id, fecha, block.getAttribute("data-start") || "", block.getAttribute("data-end") || "");
      return;
    }
    const gridEl = block.closest("[data-planner-grid]");
    const hourStart = Number((gridEl && gridEl.dataset.hourStart) || 6);
    const hourEnd = Number((gridEl && gridEl.dataset.hourEnd) || 22);
    const start0 = parseHm(block.getAttribute("data-start"));
    const end0 = parseHm(block.getAttribute("data-end"));
    const dur = start0 != null && end0 != null && end0 > start0 ? end0 - start0 : 60;
    const mins = Math.max(hourStart * 60, Math.min(hourEnd * 60 - 15, start0 + (up ? -15 : 15)));
    if (mins === start0) return;
    submitMove(id, fecha0, minsToHm(mins), minsToHm(mins + dur));
  });

  if (grid) {
    const hourStart = Number(grid.dataset.hourStart || 6);
    const hourEnd = Number(grid.dataset.hourEnd || 22);
    const pxPerHour = Number(grid.dataset.pxPerHour || 56);

    grid.addEventListener("pointerdown", function (ev) {
      const block = ev.target.closest("[data-event-id]");
      if (!block || ev.button !== 0) return;
      const id = block.getAttribute("data-event-id");
      if (!id) return;
      const allday = block.getAttribute("data-allday") === "1";
      const start0 = parseHm(block.getAttribute("data-start"));
      const end0 = parseHm(block.getAttribute("data-end"));
      const dur = start0 != null && end0 != null && end0 > start0 ? end0 - start0 : 60;
      const originX = ev.clientX;
      const originY = ev.clientY;
      const fecha0 = block.getAttribute("data-fecha") || "";
      block.classList.add("is-dragging");
      try {
        block.setPointerCapture(ev.pointerId);
      } catch (e) { /* ignore */ }

      function colFromPoint(x, y) {
        const cols = grid.querySelectorAll(".tl-col");
        for (const col of cols) {
          const r = col.getBoundingClientRect();
          if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return col;
        }
        return block.closest(".tl-col");
      }

      function minutesFromY(col, clientY) {
        const hours = col.querySelector(".tl-hours");
        const rect = hours.getBoundingClientRect();
        const y = clientY - rect.top;
        let mins = hourStart * 60 + (y / pxPerHour) * 60;
        mins = Math.round(mins / 15) * 15;
        const maxStart = hourEnd * 60 - 15;
        return Math.max(hourStart * 60, Math.min(maxStart, mins));
      }

      function onMove(e) {
        const col = colFromPoint(e.clientX, e.clientY);
        if (!col) return;
        if (!allday) {
          const mins = minutesFromY(col, e.clientY);
          const top = ((mins - hourStart * 60) / 60) * pxPerHour;
          block.style.top = top + "px";
        }
      }

      function onUp(e) {
        block.classList.remove("is-dragging");
        block.removeEventListener("pointermove", onMove);
        block.removeEventListener("pointerup", onUp);
        block.removeEventListener("pointercancel", onUp);
        const moved = Math.hypot(e.clientX - originX, e.clientY - originY) > 8;
        if (!moved) return;
        const col = colFromPoint(e.clientX, e.clientY) || block.closest(".tl-col");
        const fecha = col ? col.getAttribute("data-fecha") : block.getAttribute("data-fecha");
        if (allday) {
          if (fecha && fecha !== fecha0) submitMove(id, fecha, "", "");
          return;
        }
        const mins = minutesFromY(col, e.clientY);
        submitMove(id, fecha, minsToHm(mins), minsToHm(mins + dur));
      }

      block.addEventListener("pointermove", onMove);
      block.addEventListener("pointerup", onUp);
      block.addEventListener("pointercancel", onUp);
    });
  }

  if (month) {
    let dragging = null;
    month.addEventListener("pointerdown", function (ev) {
      const block = ev.target.closest("[data-event-id]");
      if (!block || ev.button !== 0) return;
      dragging = block;
      block.classList.add("is-dragging");
    });
    month.addEventListener("pointerup", function (ev) {
      if (!dragging) return;
      dragging.classList.remove("is-dragging");
      const cell = ev.target.closest(".tl-month-cell[data-fecha]");
      const id = dragging.getAttribute("data-event-id");
      const fecha = cell && cell.getAttribute("data-fecha");
      const start = dragging.getAttribute("data-start") || "";
      const end = dragging.getAttribute("data-end") || "";
      const prevFecha = dragging.getAttribute("data-fecha") || "";
      dragging = null;
      if (id && fecha && fecha !== prevFecha) submitMove(id, fecha, start, end);
    });
  }
})();
