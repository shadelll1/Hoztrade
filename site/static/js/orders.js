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

  // «В корзину» без перезагрузки: обновляем значок и кнопку
  var badge = document.querySelector("[data-cart-count]");
  document.querySelectorAll("[data-add-to-cart]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      post(form).then(function (r) { return r.json(); }).then(function (data) {
        if (badge) {
          badge.textContent = data.count;
          badge.hidden = !data.count;
          badge.classList.remove("bump"); void badge.offsetWidth; badge.classList.add("bump");
        }
        var label = btn.textContent;
        btn.textContent = "В корзине ✓";
        setTimeout(function () { btn.textContent = label; btn.disabled = false; }, 1400);
      }).catch(function () { form.submit(); });
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
    checkout.addEventListener("change", sync);
    sync();
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
