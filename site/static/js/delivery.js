// Хозтрейд — калькулятор доставки на странице «Доставка». Та же логика подбора машины, что на сервере
// (delivery/services.py): наименьшая машина за один рейс, иначе самая большая в несколько рейсов.
(function () {
  "use strict";

  var form = document.querySelector("[data-delivery-calc]");
  var source = document.getElementById("delivery-calc-data");
  if (!form || !source) return;

  var data = JSON.parse(source.textContent);
  var weight = form.querySelector("#calc-weight");
  var zone = form.querySelector("#calc-zone");
  var result = form.querySelector("[data-calc-result]");
  var rub = function (n) { return new Intl.NumberFormat("ru-RU").format(n) + " ₽"; };
  var plural = function (n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  };

  function calc() {
    var kg = Math.max(parseFloat(weight.value) || 0, 0);
    var prices = data.zones[zone.value].prices;
    var trucks = data.trucks
      .map(function (t, i) { return { name: t.name, kg: t.kg, price: prices[i] }; })
      .filter(function (t) { return t.price !== null; });
    if (!trucks.length) { result.textContent = "В эту зону цену назовёт менеджер"; return; }

    var pick = trucks.find(function (t) { return kg <= t.kg; });
    var trips = 1;
    if (!pick) {
      pick = trucks[trucks.length - 1];
      trips = Math.ceil(kg / pick.kg);
    }
    // Название машины приходит из 1С — только как текст, без разметки
    var cost = document.createElement("b");
    cost.textContent = rub(pick.price * trips);
    var truck = document.createElement("span");
    truck.textContent = pick.name + (trips > 1 ? " × " + trips + " " + plural(trips, "рейс", "рейса", "рейсов") : "");
    result.replaceChildren(cost, truck);
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); calc(); });
  form.addEventListener("input", calc);
  form.addEventListener("change", calc);
  calc();
})();
