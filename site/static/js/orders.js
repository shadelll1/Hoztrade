// Хозтрейд — корзина, оформление, окно обратного звонка. Всё работает и без JS (обычные формы).
(function () {
  "use strict";

  function post(form) {
    return fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin",
    });
  }

  var badges = document.querySelectorAll("[data-cart-count]");
  var live = document.querySelector("[data-cart-live]");  // озвучка для экранного диктора
  var MAX = 100000;

  function plural(n, forms) {
    var f = (forms || "шт,шт,шт").split(","), m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return f[0];
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return f[1];
    return f[2];
  }

  function updateBadges(count) {
    badges.forEach(function (badge) {
      badge.textContent = count;
      badge.hidden = !count;
      badge.classList.remove("bump"); void badge.offsetWidth; badge.classList.add("bump");
    });
  }

  // Все блоки покупки одного товара на странице (карточка, страница товара, панель на телефоне) — в одно состояние
  function sameProduct(box) {
    return document.querySelectorAll('[data-buy][data-product="' + box.dataset.product + '"]');
  }

  function render(box, qty, bump) {
    sameProduct(box).forEach(function (b) {
      var field = b.querySelector("[data-buy-qty]");
      b.classList.toggle("is-in-cart", qty > 0);
      if (qty > 0 && field && Number(field.value) !== qty) field.value = qty;
      if (bump) {
        var q = b.querySelector(".qty");
        if (q) { q.classList.remove("is-bumped"); void q.offsetWidth; q.classList.add("is-bumped"); }
      }
      b.dispatchEvent(new CustomEvent("buy:change", { bubbles: true, detail: { quantity: qty } }));
    });
  }

  // Уведомление «Добавлено в корзину» — только при первом добавлении товара
  var toast = document.querySelector("[data-added]");
  var toastTimer;
  function showToast(box) {
    if (!toast) return;
    var img = toast.querySelector("[data-added-img]");
    img.hidden = !box.dataset.image;
    if (box.dataset.image) img.src = box.dataset.image;
    toast.querySelector("[data-added-name]").textContent = box.dataset.name || "";
    clearTimeout(toastTimer);
    toast.classList.remove("is-leaving");
    toast.hidden = false;
    toastTimer = setTimeout(function () {
      toast.classList.add("is-leaving");
      setTimeout(function () { toast.hidden = true; toast.classList.remove("is-leaving"); }, 250);
    }, 3800);
  }

  function send(form, quantity) {
    var body = new FormData(form);
    if (quantity !== undefined) body.set("quantity", quantity);
    return fetch(form.action, {
      method: "POST", body: body, credentials: "same-origin", headers: { "X-Requested-With": "fetch" },
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }

  function applied(box, data, verb) {
    updateBadges(data.count);
    render(box, data.quantity, true);
    if (live) {
      live.textContent = data.quantity
        ? verb + " В корзине " + data.quantity + " " + plural(data.quantity, box.dataset.forms) + "."
        : "Товар убран из корзины.";
    }
  }

  document.querySelectorAll("[data-buy]").forEach(function (box) {
    var add = box.querySelector("[data-buy-add]");
    var set = box.querySelector("[data-buy-set]");
    var field = box.querySelector("[data-buy-qty]");
    var timer, pending;

    // «В корзину»: добавить выбранное количество (в карточке — 1 штуку)
    add.addEventListener("submit", function (e) {
      e.preventDefault();
      var amount = add.querySelector("[data-buy-amount]");
      var n = Math.max(1, Math.min(MAX, parseInt(amount && amount.value, 10) || 1));
      box.classList.add("is-busy");
      send(add, n).then(function (data) {
        applied(box, data, "Товар добавлен в корзину.");
        showToast(box);
        if (amount && amount.type === "number") amount.value = 1;
        var next = box.querySelector("[data-buy-step='1']");
        if (next && box.contains(document.activeElement)) next.focus();  // фокус не теряется при смене кнопки на счётчик
      }).catch(function () { add.submit(); }).then(function () { box.classList.remove("is-busy"); });
    });

    // Счётчик: изменения копятся 350 мс и уходят одним запросом; 0 — товар убирается из корзины
    function commit(n) {
      n = Math.max(0, Math.min(MAX, n));
      field.value = Math.max(n, 1);
      render(box, n, true);
      clearTimeout(timer);
      pending = n;
      timer = setTimeout(function () {
        send(set, pending).then(function (data) { applied(box, data, "Количество изменено."); })
          .catch(function () { set.submit(); });
      }, 350);
    }
    box.querySelectorAll("[data-buy-step]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        commit((parseInt(field.value, 10) || 0) + Number(btn.dataset.buyStep));
      });
    });
    field.addEventListener("change", function () { commit(parseInt(field.value, 10) || 0); });
    set.addEventListener("submit", function (e) { e.preventDefault(); commit(parseInt(field.value, 10) || 0); });

    // Калькулятор и другие блоки могут задать количество: «положить N в корзину»
    box.addEventListener("buy:set", function (e) {
      var n = e.detail.quantity;
      if (box.classList.contains("is-in-cart")) { commit(n); return; }
      var amount = add.querySelector("[data-buy-amount]");
      if (amount) amount.value = n;
      add.requestSubmit ? add.requestSubmit() : add.dispatchEvent(new Event("submit", { cancelable: true }));
    });
  });

  // Корзина: изменение количества сразу пересчитывает
  document.querySelectorAll("[data-autosubmit]").forEach(function (form) {
    var timer;
    form.addEventListener("change", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { form.submit(); }, 400);
    });
  });

  // Оформление: показываем поля по выбранному типу покупателя и способу получения
  var checkout = document.querySelector("[data-checkout]");
  if (checkout) {
    var sync = function () {
      var type = (checkout.querySelector("[name=customer_type]:checked") || {}).value;
      var delivery = (checkout.querySelector("[name=delivery]:checked") || {}).value;
      checkout.querySelectorAll("[data-show-for]").forEach(function (box) {
        var key = box.dataset.showFor;
        box.hidden = !(key === type || key === delivery);
      });
    };
    // Стоимость доставки выбранной зоны — в сводку заказа (сервер пересчитает её при оформлении)
    var deliveryRow = checkout.querySelector("[data-delivery-row]");
    var deliveryCost = checkout.querySelector("[data-delivery-cost]");
    var grandTotal = checkout.querySelector("[data-grand-total]");
    var truckName = checkout.querySelector("[data-truck-name]");
    var rub = function (n) {
      return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(n) + " ₽";
    };
    var recalc = function () {
      var delivery = (checkout.querySelector("[name=delivery]:checked") || {}).value;
      var zone = checkout.querySelector("[name=zone]:checked");
      var quote = zone && zone.closest(".zone").querySelector("[data-cost]");
      var cost = delivery === "truck" && quote ? parseFloat(quote.dataset.cost) : 0;
      if (deliveryRow) {
        deliveryRow.hidden = !cost;
        deliveryCost.textContent = rub(cost);
        grandTotal.textContent = rub(parseFloat(grandTotal.dataset.goods) + cost);
      }
      if (truckName && quote) truckName.textContent = quote.dataset.truck;
    };
    checkout.addEventListener("change", function () { sync(); recalc(); });
    sync();
    recalc();
  }

  // Окно «Перезвоним вам»
  var dialog = document.getElementById("callback");
  document.querySelectorAll("[data-dialog-open]").forEach(function (btn) {
    btn.addEventListener("click", function () { if (dialog && dialog.showModal) dialog.showModal(); });
  });
  if (dialog) {
    dialog.querySelector("[data-dialog-close]").addEventListener("click", function () { dialog.close(); });
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
    var form = dialog.querySelector("[data-callback]");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var err = form.querySelector("[data-callback-error]");
      var ok = form.querySelector("[data-callback-ok]");
      err.hidden = true;
      post(form).then(function (r) {
        if (r.ok) {
          ok.hidden = false;
          form.querySelectorAll("input, button[type=submit]").forEach(function (el) { el.disabled = true; });
          setTimeout(function () { dialog.close(); }, 2500);
        } else {
          err.hidden = false;
        }
      });
    });
  }
})();
