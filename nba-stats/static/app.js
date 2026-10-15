(function () {
  "use strict";

  // ---- 表のソート（ヘッダークリック） -----------------------------------
  function cellValue(cell, numeric) {
    if (!cell) return numeric ? null : "";
    var v = cell.getAttribute("data-v");
    if (v === null) v = cell.textContent.trim();
    if (!numeric) return v.toLowerCase();
    var n = parseFloat(v);
    return isNaN(n) ? null : n;
  }

  function sortTable(table, idx, th) {
    var numeric = th.getAttribute("data-sort") === "num";
    // 数値は降順スタート（大きい順が見たいことが多い）、文字列は昇順スタート
    var current = th.classList.contains("asc") ? "asc" : th.classList.contains("desc") ? "desc" : "";
    var dir = current ? (current === "asc" ? "desc" : "asc") : (numeric ? "desc" : "asc");
    table.querySelectorAll("thead th").forEach(function (h) { h.classList.remove("asc", "desc"); });
    th.classList.add(dir);

    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      var x = cellValue(a.cells[idx], numeric);
      var y = cellValue(b.cells[idx], numeric);
      // 空欄は常に末尾
      if (x === null || x === "") return (y === null || y === "") ? 0 : 1;
      if (y === null || y === "") return -1;
      var r = x < y ? -1 : x > y ? 1 : 0;
      return dir === "asc" ? r : -r;
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
    renumber(table);
  }

  // 「Rk」列があれば表示順に振り直す
  function renumber(table) {
    var first = table.querySelector("thead th");
    if (!first || first.textContent.trim() !== "Rk") return;
    var n = 0;
    Array.prototype.forEach.call(table.tBodies[0].rows, function (r) {
      if (!r.classList.contains("hidden")) r.cells[0].textContent = ++n;
    });
  }

  document.querySelectorAll("table.sortable").forEach(function (table) {
    table.querySelectorAll("thead th").forEach(function (th, idx) {
      th.addEventListener("click", function () { sortTable(table, idx, th); });
    });
  });

  // ---- タブ ---------------------------------------------------------------
  var KEY = "nba-stats-tab";
  function activate(id) {
    var found = false;
    document.querySelectorAll(".tab").forEach(function (b) {
      var on = b.getAttribute("data-tab") === id;
      b.classList.toggle("active", on);
      if (on) found = true;
    });
    if (!found) return false;
    document.querySelectorAll(".panel").forEach(function (p) {
      p.hidden = p.getAttribute("data-panel") !== id;
    });
    return true;
  }
  document.querySelectorAll(".tab").forEach(function (b) {
    b.addEventListener("click", function () {
      var id = b.getAttribute("data-tab");
      activate(id);
      try { localStorage.setItem(KEY, id); } catch (e) { /* ignore */ }
    });
  });
  // 前回見ていた表（Per Game / Totals / Advanced）を復元
  var hashTab = location.hash.replace("#", "");
  if (!(hashTab && activate(hashTab))) {
    try { var saved = localStorage.getItem(KEY); if (saved) activate(saved); } catch (e) { /* ignore */ }
  }

  // ---- シーズンページのフィルタ -----------------------------------------
  var minGames = document.querySelector(".min-games");
  var hidePartial = document.querySelector(".hide-partial");
  function applyFilters() {
    var min = minGames ? parseFloat(minGames.value) || 0 : 0;
    var hp = hidePartial ? hidePartial.checked : false;
    document.querySelectorAll("table.stats").forEach(function (table) {
      Array.prototype.forEach.call(table.tBodies[0].rows, function (r) {
        var g = parseFloat(r.getAttribute("data-g"));
        var hide = (min > 0 && !isNaN(g) && g < min) || (hp && r.classList.contains("partial"));
        r.classList.toggle("hidden", hide);
      });
      renumber(table);
    });
  }
  if (minGames) minGames.addEventListener("input", applyFilters);
  if (hidePartial) hidePartial.addEventListener("change", applyFilters);

  // ---- 選手検索 -----------------------------------------------------------
  var input = document.getElementById("search");
  var list = document.getElementById("search-results");
  var players = window.PLAYERS || [];
  var root = window.SITE_ROOT || "";
  var sel = -1;

  function norm(s) {
    // アクセント記号を除去（Dončić → doncic）
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  players.forEach(function (p) { p.k = norm(p.n); });

  function esc(s) {
    return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  function render() {
    var q = norm(input.value.trim());
    sel = -1;
    if (!q) { list.hidden = true; list.innerHTML = ""; return; }
    var hits = players.filter(function (p) { return p.k.indexOf(q) !== -1; });
    // 前方一致（姓・名どちらでも）を優先
    hits.sort(function (a, b) {
      var sa = (" " + a.k).indexOf(" " + q) !== -1 ? 0 : 1;
      var sb = (" " + b.k).indexOf(" " + q) !== -1 ? 0 : 1;
      return sa - sb;
    });
    hits = hits.slice(0, 20);
    list.innerHTML = hits.length
      ? hits.map(function (p) {
          return '<li><a href="' + root + p.u + '"><span>' + esc(p.n) + '</span><span class="y">' + esc(p.y) + "</span></a></li>";
        }).join("")
      : '<li><a><span class="y">該当なし</span></a></li>';
    list.hidden = false;
  }

  if (input && list) {
    input.addEventListener("input", render);
    input.addEventListener("keydown", function (e) {
      var items = list.querySelectorAll("li");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach(function (li, i) { li.classList.toggle("sel", i === sel); });
      } else if (e.key === "Enter") {
        var target = items[sel >= 0 ? sel : 0];
        var a = target && target.querySelector("a[href]");
        if (a) location.href = a.getAttribute("href");
      } else if (e.key === "Escape") {
        list.hidden = true;
      }
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".search")) list.hidden = true;
    });
    // "/" キーで検索欄へ
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement !== input && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) {
        e.preventDefault();
        input.focus();
      }
    });
  }
})();
