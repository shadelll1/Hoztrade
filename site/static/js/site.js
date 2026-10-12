// Хозтрейд — поведение витрины. Без зависимостей.
(function () {
  "use strict";

  // Мегаменю каталога: кнопка в шапке и «Каталог» в нижней панели на телефоне
  var toggles = document.querySelectorAll("[data-megamenu-toggle]");
  var menu = document.getElementById("megamenu");
  if (toggles.length && menu) {
    var setOpen = function (open) {
      toggles.forEach(function (t) { t.setAttribute("aria-expanded", String(open)); });
      menu.hidden = !open;
      document.documentElement.classList.toggle("is-menu-open", open);
    };
    toggles.forEach(function (t) {
      t.addEventListener("click", function () { setOpen(menu.hidden); });
    });
    // Escape закрывает меню; если фокус был внутри — возвращаем его на кнопку, которой меню открыли
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" || menu.hidden) return;
      var inside = menu.contains(document.activeElement);
      setOpen(false);
      if (inside) {
        var visible = Array.prototype.filter.call(toggles, function (t) { return t.offsetParent !== null; });
        if (visible[0]) visible[0].focus();
      }
    });
    document.addEventListener("click", function (e) {
      if (menu.hidden || menu.contains(e.target)) return;
      for (var i = 0; i < toggles.length; i++) if (toggles[i].contains(e.target)) return;
      setOpen(false);
    });

    // Раздел слева -> его подразделы справа (наведение мышью или фокус с клавиатуры)
    var roots = menu.querySelectorAll("[data-mega-root]");
    var activate = function (root) {
      roots.forEach(function (r) { r.classList.toggle("is-active", r === root); });
      menu.querySelectorAll("[data-mega-panel]").forEach(function (panel) {
        panel.hidden = panel.dataset.megaPanel !== root.dataset.megaRoot;
      });
    };
    roots.forEach(function (root) {
      root.addEventListener("mouseenter", function () { activate(root); });
      root.addEventListener("focus", function () { activate(root); });
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

  // Лента товаров: стрелки листают на ширину видимой части
  document.querySelectorAll("[data-rail]").forEach(function (rail) {
    var section = rail.closest("section") || document;
    var prev = section.querySelector("[data-rail-prev]");
    var next = section.querySelector("[data-rail-next]");
    var sync = function () {
      if (prev) prev.disabled = rail.scrollLeft <= 4;
      if (next) next.disabled = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 4;
    };
    if (prev) prev.addEventListener("click", function () { rail.scrollBy({ left: -rail.clientWidth * 0.9 }); });
    if (next) next.addEventListener("click", function () { rail.scrollBy({ left: rail.clientWidth * 0.9 }); });
    rail.addEventListener("scroll", sync, { passive: true });
    window.addEventListener("resize", sync);
    sync();
  });

  // Фото товара: увеличение под курсором (только мышь)
  var zoom = document.querySelector("[data-zoom]");
  if (zoom && zoom.querySelector("img") && window.matchMedia("(hover: hover)").matches) {
    zoom.addEventListener("mousemove", function (e) {
      var r = zoom.getBoundingClientRect();
      zoom.style.setProperty("--zx", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
      zoom.style.setProperty("--zy", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
    });
    zoom.addEventListener("mouseenter", function () { zoom.classList.add("is-zoom"); });
    zoom.addEventListener("mouseleave", function () { zoom.classList.remove("is-zoom"); });
  }

  // Телефон: панель «В корзину» появляется, когда основной блок покупки ушёл с экрана
  var buybox = document.querySelector("[data-buybox]");
  var buybar = document.querySelector("[data-buybar]");
  if (buybox && buybar && "IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      var box = entries[0];
      buybar.hidden = box.isIntersecting || box.boundingClientRect.top > 0;
    }).observe(buybox);
  }

  // Плашка о cookie: отметка «Понятно» хранится только в браузере
  var cookie = document.querySelector("[data-cookie]");
  if (cookie) {
    var seen = false;
    try { seen = localStorage.getItem("cookie-ok") === "1"; } catch (e) { /* приватный режим */ }
    cookie.hidden = seen;
    cookie.querySelector("[data-cookie-ok]").addEventListener("click", function () {
      try { localStorage.setItem("cookie-ok", "1"); } catch (e) { /* приватный режим */ }
      cookie.hidden = true;
    });
  }
})();
