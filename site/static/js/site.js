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

  // Подсказки поиска: разделы и товары по мере ввода. Шаблон ARIA combobox + listbox,
  // стрелки выбирают вариант, Enter открывает его, Escape закрывает.
  var sForm = document.querySelector("[data-suggest-form]");
  if (sForm && window.fetch) {
    var sInput = sForm.querySelector("[data-suggest-input]");
    var sBox = sForm.querySelector("[data-suggest]");
    var sTimer, sSeq = 0, sActive = -1, sCache = {};

    var el = function (tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    };
    // Совпадение со словами запроса — жирным (только через textContent, разметку из ответа не вставляем)
    var highlight = function (node, text, q) {
      var words = q.toLowerCase().split(/\s+/).filter(function (w) { return w.length > 1; });
      var low = text.toLowerCase(), i = 0;
      while (i < text.length) {
        var hit = -1, len = 0;
        words.forEach(function (w) { var k = low.indexOf(w, i); if (k !== -1 && (hit === -1 || k < hit)) { hit = k; len = w.length; } });
        if (hit === -1) { node.appendChild(document.createTextNode(text.slice(i))); break; }
        if (hit > i) node.appendChild(document.createTextNode(text.slice(i, hit)));
        node.appendChild(el("mark", "", text.slice(hit, hit + len)));
        i = hit + len;
      }
    };
    var options = function () { return sBox.querySelectorAll("[role=option]"); };
    var setActive = function (i) {
      var opts = options();
      sActive = opts.length ? (i + opts.length) % opts.length : -1;
      opts.forEach(function (o, k) { o.setAttribute("aria-selected", String(k === sActive)); });
      if (sActive >= 0) {
        sInput.setAttribute("aria-activedescendant", opts[sActive].id);
        opts[sActive].scrollIntoView({ block: "nearest" });
      } else sInput.removeAttribute("aria-activedescendant");
    };
    var close = function () {
      sBox.hidden = true;
      sInput.setAttribute("aria-expanded", "false");
      sInput.removeAttribute("aria-activedescendant");
      sActive = -1;
    };
    var option = function (href, cls, id) {
      var a = el("a", "suggest__opt " + cls);
      a.href = href; a.id = "sg-" + id; a.setAttribute("role", "option"); a.tabIndex = -1;
      a.setAttribute("aria-selected", "false");
      return a;
    };
    var draw = function (data) {
      var q = sInput.value.trim(), n = 0;
      sBox.replaceChildren();
      if (data.popular) {
        var g0 = el("div", "suggest__group"); g0.setAttribute("role", "group"); g0.setAttribute("aria-label", "Часто ищут");
        g0.appendChild(el("div", "suggest__label", "Часто ищут"));
        var chips = el("div", "suggest__chips");
        data.popular.forEach(function (word) {
          var a = option(sForm.action + "?q=" + encodeURIComponent(word), "suggest__opt--q", n++);
          a.textContent = word;
          chips.appendChild(a);
        });
        g0.appendChild(chips);
        sBox.appendChild(g0);
      }
      if (data.categories && data.categories.length) {
        var g1 = el("div", "suggest__group"); g1.setAttribute("role", "group"); g1.setAttribute("aria-label", "Разделы");
        g1.appendChild(el("div", "suggest__label", "Разделы"));
        data.categories.forEach(function (c) {
          var a = option(c.url, "suggest__opt--cat", n++);
          a.appendChild(el("span", "suggest__meta", "▦"));
          var name = el("span", "suggest__name"); highlight(name, c.name, q); a.appendChild(name);
          a.appendChild(el("span", "suggest__meta", c.count + " шт."));
          g1.appendChild(a);
        });
        sBox.appendChild(g1);
      }
      if (data.products && data.products.length) {
        var g2 = el("div", "suggest__group"); g2.setAttribute("role", "group"); g2.setAttribute("aria-label", "Товары");
        g2.appendChild(el("div", "suggest__label", "Товары"));
        data.products.forEach(function (p) {
          var a = option(p.url, "", n++);
          var img = el("img", "suggest__img"); img.alt = ""; img.width = 44; img.height = 44;
          if (p.image) img.src = p.image; else img.removeAttribute("src");
          a.appendChild(img);
          var name = el("span", "suggest__name"); highlight(name, p.title, q); a.appendChild(name);
          a.appendChild(el("span", "suggest__price", p.price ? p.price + "/" + p.unit : ""));
          g2.appendChild(a);
        });
        sBox.appendChild(g2);
      }
      if (q && data.total > 0) {
        var all = option(data.all_url, "suggest__all", n++);
        all.className = "suggest__all";
        all.textContent = "Все результаты: " + data.total;
        sBox.appendChild(all);
      } else if (q && !data.total) {
        sBox.appendChild(el("p", "suggest__empty", "Ничего не нашлось. Попробуйте другое слово или позвоните — подберём под заказ."));
      }
      sBox.hidden = !sBox.childNodes.length;
      sInput.setAttribute("aria-expanded", String(!sBox.hidden));
      sActive = -1;
    };
    var load = function () {
      var q = sInput.value.trim();
      var key = q.toLowerCase();
      if (sCache[key]) { draw(sCache[key]); return; }
      var seq = ++sSeq;
      fetch(sForm.dataset.suggestUrl + "?q=" + encodeURIComponent(q), { headers: { "X-Requested-With": "fetch" } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          sCache[key] = data;
          if (seq === sSeq && document.activeElement === sInput) draw(data);  // ответы старых запросов не рисуем
        }).catch(function () { /* без подсказок поиск работает как раньше */ });
    };
    sInput.addEventListener("input", function () { clearTimeout(sTimer); sTimer = setTimeout(load, 140); });
    sInput.addEventListener("focus", load);
    sInput.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (sBox.hidden) { load(); return; }
        e.preventDefault();
        setActive(sActive + (e.key === "ArrowDown" ? 1 : -1));
      } else if (e.key === "Enter" && sActive >= 0 && !sBox.hidden) {
        e.preventDefault();
        options()[sActive].click();
      } else if (e.key === "Escape" && !sBox.hidden) {
        e.stopPropagation();
        close();
      }
    });
    document.addEventListener("click", function (e) { if (!sForm.contains(e.target)) close(); });
    sForm.addEventListener("focusout", function (e) { if (!sForm.contains(e.relatedTarget)) setTimeout(close, 120); });
  }

  // Фильтры применяются сразу при выборе (кнопка «Показать» остаётся для ввода цены и без JS)
  var fForm = document.querySelector("[data-filters-form]");
  if (fForm) {
    fForm.addEventListener("change", function (e) {
      if (e.target.type !== "checkbox") return;
      fForm.closest("[data-filters]").classList.add("is-loading");
      fForm.requestSubmit ? fForm.requestSubmit() : fForm.submit();
    });
  }

  // Фото товара «перелетает» из карточки на страницу товара: имя перехода — только у нажатой карточки
  if ("onpageswap" in window || document.startViewTransition) {
    document.addEventListener("click", function (e) {
      var link = e.target.closest && e.target.closest("[data-photo-link]");
      if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      var img = link.closest(".card") && link.closest(".card").querySelector(".card__img img");
      document.querySelectorAll("[data-vt-photo]").forEach(function (n) { n.style.viewTransitionName = ""; n.removeAttribute("data-vt-photo"); });
      if (img) { img.style.viewTransitionName = "product-photo"; img.setAttribute("data-vt-photo", ""); }
    });
    // Возврат назад из кэша страницы — имя снимаем, чтобы не мешало следующему переходу
    window.addEventListener("pageshow", function () {
      document.querySelectorAll("[data-vt-photo]").forEach(function (n) { n.style.viewTransitionName = ""; n.removeAttribute("data-vt-photo"); });
    });
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
