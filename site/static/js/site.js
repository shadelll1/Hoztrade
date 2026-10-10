// Хозтрейд — поведение витрины. Без зависимостей.
(function () {
  "use strict";

  // Мегаменю каталога
  var toggle = document.querySelector("[data-megamenu-toggle]");
  var menu = document.getElementById("megamenu");
  if (toggle && menu) {
    var setOpen = function (open) {
      toggle.setAttribute("aria-expanded", String(open));
      menu.hidden = !open;
    };
    toggle.addEventListener("click", function () { setOpen(menu.hidden); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setOpen(false); });
    document.addEventListener("click", function (e) {
      if (!menu.hidden && !menu.contains(e.target) && !toggle.contains(e.target)) setOpen(false);
    });
  }

  // Фильтры: на широком экране всегда раскрыты (на узком сворачиваются в <details>)
  var filters = document.querySelector("[data-filters]");
  if (filters && window.matchMedia("(min-width: 861px)").matches) filters.open = true;

  // Счётчик количества «− 1 +»
  document.querySelectorAll("[data-stepper]").forEach(function (box) {
    var input = box.querySelector("input");
    box.querySelectorAll("[data-step]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var min = Number(input.min || 1);
        var value = Math.max(min, (Number(input.value) || min) + Number(btn.dataset.step));
        input.value = value;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  });
})();
