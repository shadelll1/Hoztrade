// Хозтрейд — CRM: доска с перетаскиванием, фильтры, задачи без перезагрузки. Без JS всё работает формами.
(function () {
  "use strict";

  var live = document.querySelector("[data-crm-live]");
  var say = function (text) { if (live) live.textContent = text; };
  var csrf = function (root) {
    var input = (root || document).querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  };
  var post = function (url, data, root) {
    var body = new FormData();
    Object.keys(data).forEach(function (k) { body.append(k, data[k]); });
    body.append("csrfmiddlewaretoken", csrf(root));
    return fetch(url, { method: "POST", body: body, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  };

  // Фильтры (кто, источник, период) применяются сразу
  document.querySelectorAll("[data-crm-autosubmit]").forEach(function (form) {
    form.addEventListener("change", function () { form.requestSubmit ? form.requestSubmit() : form.submit(); });
  });

  // Отказ — с причиной (её видно в отчёте «Причины отказов»)
  var askReason = function () {
    var reason = window.prompt("Причина отказа (необязательно): дорого, купил в другом месте, передумал…", "");
    return reason === null ? null : reason.trim();
  };
  document.querySelectorAll("[data-ask-reason]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      var reason = askReason();
      if (reason === null) { e.preventDefault(); return; }
      btn.form.querySelector("[data-reason]").value = reason;
    });
  });

  // ---------- Доска: перетаскивание карточек между этапами ----------
  var board = document.querySelector("[data-board]");
  if (board) {
    var moveUrl = function (id) { return board.dataset.moveUrl.replace("/0/", "/" + id + "/"); };
    var columns = Array.prototype.slice.call(board.querySelectorAll("[data-stage]"));
    var dragged = null;

    var recount = function () {
      columns.forEach(function (col) {
        var list = col.querySelector("[data-drop]");
        var cards = list.querySelectorAll("[data-deal]");
        col.querySelector("[data-col-count]").textContent = cards.length;
        var empty = list.querySelector(".col__empty");
        if (cards.length && empty) empty.remove();
        if (!cards.length && !empty) {
          var li = document.createElement("li");
          li.className = "col__empty"; li.textContent = "Пусто";
          list.appendChild(li);
        }
      });
    };

    var move = function (card, col) {
      var from = card.closest("[data-stage]");
      if (!col || col === from) return;
      var stage = col.dataset.stage, data = { stage: stage };
      if (stage === "lost") {
        var reason = askReason();
        if (reason === null) return;
        data.reason = reason;
      }
      var list = col.querySelector("[data-drop]");
      list.insertBefore(card, list.firstChild);
      card.classList.remove("is-moved"); void card.offsetWidth; card.classList.add("is-moved");
      recount();
      post(moveUrl(card.dataset.deal), data, board).then(function (res) {
        say("Обращение перенесено: " + res.label);
      }).catch(function () {
        from.querySelector("[data-drop]").insertBefore(card, from.querySelector("[data-drop]").firstChild);
        recount();
        say("Не удалось сменить этап — обновите страницу");
      });
    };

    board.addEventListener("dragstart", function (e) {
      dragged = e.target.closest && e.target.closest("[data-deal]");
      if (!dragged) return;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", dragged.dataset.deal);
      requestAnimationFrame(function () { dragged.classList.add("is-dragging"); });
    });
    board.addEventListener("dragend", function () {
      if (dragged) dragged.classList.remove("is-dragging");
      columns.forEach(function (c) { c.classList.remove("is-over"); });
      dragged = null;
    });
    columns.forEach(function (col) {
      col.addEventListener("dragover", function (e) {
        if (!dragged) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        col.classList.add("is-over");
      });
      col.addEventListener("dragleave", function (e) { if (!col.contains(e.relatedTarget)) col.classList.remove("is-over"); });
      col.addEventListener("drop", function (e) {
        e.preventDefault();
        col.classList.remove("is-over");
        if (dragged) move(dragged, col);
      });
    });
    // С клавиатуры: фокус на карточке, Alt+→ / Alt+← — следующий или предыдущий этап
    board.addEventListener("keydown", function (e) {
      if (!e.altKey || (e.key !== "ArrowRight" && e.key !== "ArrowLeft")) return;
      var card = e.target.closest("[data-deal]");
      if (!card) return;
      e.preventDefault();
      var i = columns.indexOf(card.closest("[data-stage]")) + (e.key === "ArrowRight" ? 1 : -1);
      if (columns[i]) { move(card, columns[i]); card.querySelector("a").focus(); }
    });
  }

  // ---------- Задачи: «выполнено» без перезагрузки ----------
  document.querySelectorAll("[data-task-done]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var task = form.closest("[data-task]");
      post(form.action, {}, form).then(function () {
        task.classList.add("is-done");
        form.querySelector("button").disabled = true;
        say("Задача выполнена");
        if (!task.closest(".task-group--done")) {
          setTimeout(function () { task.classList.add("is-closing"); }, 700);
          setTimeout(function () { task.remove(); }, 1000);
        }
      }).catch(function () { form.submit(); });
    });
  });
})();
