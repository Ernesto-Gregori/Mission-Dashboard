// Drawer de navegación en móvil. En escritorio el sidebar es fijo y esto no hace nada.
(function () {
  var sidebar = document.getElementById("app-sidebar");
  var toggle = document.querySelector(".nav-toggle");
  var scrim = document.querySelector(".nav-scrim");
  var close = document.querySelector(".nav-close");
  if (!sidebar || !toggle) return;

  var abierto = false;

  function focusables() {
    return Array.prototype.filter.call(
      sidebar.querySelectorAll("a[href], button, input, select, textarea"),
      function (el) { return !el.disabled && el.offsetParent !== null; }
    );
  }

  function abrir() {
    abierto = true;
    sidebar.dataset.open = "true";
    toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("nav-open");
    if (scrim) scrim.hidden = false;
    var primero = focusables()[0];
    if (primero) primero.focus();
  }

  function cerrar(devolverFoco) {
    abierto = false;
    delete sidebar.dataset.open;
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("nav-open");
    if (scrim) scrim.hidden = true;
    if (devolverFoco) toggle.focus();
  }

  toggle.addEventListener("click", function () {
    if (abierto) cerrar(true); else abrir();
  });
  if (close) close.addEventListener("click", function () { cerrar(true); });
  if (scrim) scrim.addEventListener("click", function () { cerrar(true); });

  document.addEventListener("keydown", function (e) {
    if (!abierto) return;
    if (e.key === "Escape") {
      cerrar(true);
      return;
    }
    if (e.key !== "Tab") return;
    // Mientras el drawer tapa la página, el foco no debe salir de él.
    var items = focusables();
    if (!items.length) return;
    var primero = items[0];
    var ultimo = items[items.length - 1];
    if (e.shiftKey && document.activeElement === primero) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && document.activeElement === ultimo) {
      e.preventDefault();
      primero.focus();
    }
  });

  // Al pasar a escritorio el sidebar vuelve a ser fijo: el estado abierto sobra.
  window.addEventListener("resize", function () {
    if (abierto && window.innerWidth > 800) cerrar(false);
  });
})();
