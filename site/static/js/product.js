// Хозтрейд — страница товара: калькулятор «сколько нужно» и стоимость доставки в выбранную зону.
(function () {
  "use strict";

  var buy = document.querySelector(".buybox [data-buy]");
  var num = function (v) { return parseFloat(String(v || "").replace(",", ".").replace(/\s/g, "")) || 0; };
  var fmt = function (n, digits) {
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits === undefined ? 1 : digits }).format(n);
  };
  var plural = function (n, forms) {
    var f = (forms || "шт,шт,шт").split(","), m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return f[0];
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return f[1];
    return f[2];
  };

  // Сколько единиц товара сейчас «в работе»: в корзине — оттуда, иначе — выбранное к добавлению
  function currentQty() {
    if (!buy) return 1;
    if (buy.classList.contains("is-in-cart")) return num(buy.querySelector("[data-buy-qty]").value) || 1;
    var amount = buy.querySelector("[data-buy-amount]");
    return Math.max(1, num(amount && amount.value) || 1);
  }

  // ---------- Калькулятор ----------
  var calc = document.querySelector("[data-calc]");
  if (calc) {
    var d = calc.dataset;
    var perUnit = num(d.perUnit), reserve = num(d.reserve) / 100, rate = num(d.rate);
    var inputs = {};
    calc.querySelectorAll("[data-calc-in]").forEach(function (i) { inputs[i.dataset.calcIn] = i; });
    var out = calc.querySelector("[data-calc-qty]");
    var detail = calc.querySelector("[data-calc-detail]");
    var apply = calc.querySelector("[data-calc-apply]");
    var units = 0;
    var v = function (key) { return inputs[key] ? num(inputs[key].value) : 0; };

    var compute = function () {
      var need = 0, text = "";
      if (d.kind === "area") {
        var area = inputs.b ? v("a") * v("b") : v("a");
        need = area * (1 + reserve) / perUnit;
        text = fmt(area) + " м² с запасом " + Math.round(reserve * 100) + " %";
      } else if (d.kind === "layer") {
        var kg = v("a") * v("b") * rate * (1 + reserve);
        need = kg / perUnit;
        text = "≈ " + fmt(kg, 0) + " кг смеси";
      } else if (d.kind === "rate") {
        var total = v("a") * Math.max(1, v("b")) * rate * (1 + reserve);
        need = total / perUnit;
        text = "≈ " + fmt(total) + " на всю площадь";
      } else if (d.kind === "masonry") {
        var wall = Math.max(0, v("a") * v("b") - v("c"));
        need = wall * (1 + reserve) / perUnit;
        text = fmt(wall) + " м² кладки";
      } else if (d.kind === "length") {
        need = v("a") * (1 + reserve) / perUnit;
        text = fmt(v("a")) + " м с запасом";
      } else if (d.kind === "volume") {
        need = v("a") / perUnit;
        text = fmt(v("a"), 2) + " м³";
      }
      var next = need > 0 ? Math.ceil(need - 1e-9) : 0;
      if (next !== units && next > 0) { out.classList.remove("is-ticked"); void out.offsetWidth; out.classList.add("is-ticked"); }
      units = next;
      out.textContent = units ? fmt(units, 0) + " " + plural(units, d.forms) : "—";
      detail.textContent = units ? text : "Введите размеры";
      apply.disabled = !units || !buy;
      apply.textContent = !units ? "Положить в корзину"
        : (buy && buy.classList.contains("is-in-cart") ? "Изменить в корзине на " : "Положить в корзину ")
          + fmt(units, 0) + " " + plural(units, d.forms);
    };
    calc.addEventListener("input", compute);
    apply.addEventListener("click", function () {
      if (!units || !buy) return;
      buy.dispatchEvent(new CustomEvent("buy:set", { detail: { quantity: units } }));
    });
    if (buy) buy.addEventListener("buy:change", compute);
    compute();
  }

  // ---------- Доставка по зоне: та же логика, что delivery/services.py ----------
  var ship = document.querySelector("[data-ship]");
  var source = document.getElementById("ship-data");
  if (ship && source) {
    var data = JSON.parse(source.textContent);
    var zone = ship.querySelector("[data-ship-zone]");
    var result = ship.querySelector("[data-ship-result]");
    var KEY = "ship-zone";
    try {
      var saved = localStorage.getItem(KEY);
      if (saved !== null && zone.querySelector('option[value="' + saved + '"]')) zone.value = saved;
    } catch (e) { /* приватный режим */ }

    var trips = function (t, kg, m3) {
      var n = kg > 0 ? Math.ceil(kg / t.kg) : 1;
      if (t.m3 > 0 && m3 > 0) n = Math.max(n, Math.ceil(m3 / t.m3));
      return Math.max(n, 1);
    };
    var quote = function () {
      var z = data.zones[Number(zone.value)];
      var qty = currentQty();
      var kg = data.product.kg * qty, m3 = data.product.m3 * qty;
      var trucks = data.trucks.map(function (t, i) { return { name: t.name, kg: t.kg, m3: t.m3, price: z.prices[i] }; })
        .filter(function (t) { return t.price !== null; });
      if (!trucks.length) { result.textContent = "В эту зону цену назовёт менеджер"; return; }
      var pick = null, n = 1;
      for (var i = 0; i < trucks.length; i++) { if (trips(trucks[i], kg, m3) === 1) { pick = trucks[i]; break; } }
      if (!pick) { pick = trucks[trucks.length - 1]; n = trips(pick, kg, m3); }
      var cost = document.createElement("b");
      cost.textContent = fmt(pick.price * n, 0) + " ₽";
      var what = " за " + fmt(qty, 0) + " " + plural(qty, buy ? buy.dataset.forms : "") + ", " + fmt(kg, 0) + " кг: "
        + pick.name + (n > 1 ? " × " + n + " " + plural(n, "рейс,рейса,рейсов") : "");
      result.replaceChildren(cost, document.createTextNode(what));
    };
    zone.addEventListener("change", function () {
      try { localStorage.setItem(KEY, zone.value); } catch (e) { /* приватный режим */ }
      quote();
    });
    if (buy) {
      buy.addEventListener("buy:change", quote);
      buy.addEventListener("input", quote);
      buy.addEventListener("click", function () { setTimeout(quote, 0); });  // кнопки «− +» у количества
    }
    quote();
  }
})();
