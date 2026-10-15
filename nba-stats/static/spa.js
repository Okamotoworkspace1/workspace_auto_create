/* 1 ファイル版の描画。build.py --single が埋め込む window.NBA_DATA を読み、
 * #p~選手ID / #s~シーズン / #t~チーム / #t~チーム~シーズン でページを切り替える。 */
(function () {
  "use strict";

  var D = window.NBA_DATA;
  var TOTAL = {};
  D.totalCodes.forEach(function (c) { TOTAL[c] = true; });
  var app = document.getElementById("app");

  // ---- 共通 ---------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function num(v) {
    if (v === null || v === undefined) return null;
    if (typeof v === "number") return v;
    var t = String(v).trim().replace(/,/g, "");
    if (t === "") return null;
    var n = Number(t);
    return isNaN(n) ? null : n;
  }
  function fmt(v, kind) {
    if (v === null || v === undefined || v === "") return "";
    if (kind === "text") return String(v);
    var n = num(v);
    if (n === null) return String(v);
    if (kind === "int") return String(Math.round(n));
    if (kind === "f1") return n.toFixed(1);
    if (kind === "f3") return n.toFixed(3);
    if (kind === "pct") {
      var t = n.toFixed(3);
      return t.indexOf("0.") === 0 ? t.slice(1) : t.replace("-0.", "-.");
    }
    return String(v);
  }
  function isTotal(team) { return !!TOTAL[String(team).toUpperCase()]; }
  function playerName(pid) { return (D.players[pid] && D.players[pid].n) || pid; }
  function teamName(code) { return (D.teams[code] && D.teams[code].n) || code; }
  function nameKey(pid) { return playerName(pid).toLowerCase(); }

  function playerLink(pid) { return '<a href="#p~' + esc(pid) + '">' + esc(playerName(pid)) + "</a>"; }
  function seasonLink(s) { return '<a href="#s~' + esc(s) + '">' + esc(s) + "</a>"; }
  function teamLink(team, season) {
    if (isTotal(team)) return esc(team);
    var h = "#t~" + team + (season ? "~" + season : "");
    return '<a href="' + esc(h) + '" title="' + esc(teamName(team)) + '">' + esc(team) + "</a>";
  }

  // 行: [player_id, season, team, ...列の値]
  function R(row) { return { pid: row[0], season: row[1], team: row[2], v: row.slice(3) }; }
  var TABLES = D.tables.map(function (t) {
    var gi = -1;
    t.cols.forEach(function (c, i) { if (c[0] === "g") gi = i; });
    return { id: t.id, title: t.title, cols: t.cols, rows: t.rows.map(R), career: t.career, gi: gi };
  });

  var seasonSet = {};
  TABLES.forEach(function (t) { t.rows.forEach(function (r) { seasonSet[r.season] = true; }); });
  var SEASONS = Object.keys(seasonSet).sort().reverse();

  function bySeasonTeam(a, b) {
    if (a.season !== b.season) return a.season < b.season ? -1 : 1;
    var ta = isTotal(a.team) ? 0 : 1, tb = isTotal(b.team) ? 0 : 1;
    if (ta !== tb) return ta - tb;
    return a.team < b.team ? -1 : a.team > b.team ? 1 : 0;
  }

  // ---- 表 ---------------------------------------------------------------
  // lead: 先頭の固定列 "season" / "player" / "team"
  function statTable(t, rows, lead, opts) {
    opts = opts || {};
    var footer = opts.footer;
    var labels = { season: "Season", player: "Player", team: "Team" };
    var colIdx = [];
    t.cols.forEach(function (c, i) {
      var used = rows.some(function (r) { return r.v[i] !== "" && r.v[i] != null; }) ||
        (footer && footer[i] !== "" && footer[i] != null);
      if (used) colIdx.push(i);
    });
    var cls = function (i) { return t.cols[i][2] === "text" ? "text" : "num"; };

    var head = (opts.rank ? '<th class="num" data-sort="num" tabindex="0">Rk</th>' : "") +
      lead.map(function (k, i) {
        return '<th class="lead' + (i === 0 ? " sticky" : "") + '" data-sort="text" tabindex="0">' + labels[k] + "</th>";
      }).join("") +
      colIdx.map(function (i) {
        return '<th class="' + cls(i) + '" data-sort="' + (cls(i) === "text" ? "text" : "num") + '" tabindex="0">' + esc(t.cols[i][1]) + "</th>";
      }).join("");

    var hasTotal = {};
    rows.forEach(function (r) { if (isTotal(r.team)) hasTotal[r.pid + "|" + r.season] = true; });

    var body = rows.map(function (r, n) {
      var cells = opts.rank ? ['<td class="num">' + (n + 1) + "</td>"] : [];
      lead.forEach(function (k, i) {
        var st = i === 0 ? " sticky" : "";
        if (k === "season") cells.push('<th scope="row" class="lead' + st + '">' + seasonLink(r.season) + "</th>");
        if (k === "player") cells.push('<td class="lead' + st + '" data-v="' + esc(playerName(r.pid)) + '">' + playerLink(r.pid) + "</td>");
        if (k === "team") cells.push('<td class="lead' + st + '">' + teamLink(r.team, r.season) + "</td>");
      });
      colIdx.forEach(function (i) {
        var raw = r.v[i], n2 = num(raw);
        var dv = n2 !== null && cls(i) !== "text" ? ' data-v="' + n2 + '"' : "";
        cells.push('<td class="' + cls(i) + '"' + dv + ">" + esc(fmt(raw, t.cols[i][2])) + "</td>");
      });
      var partial = !isTotal(r.team) && hasTotal[r.pid + "|" + r.season];
      var g = t.gi >= 0 ? num(r.v[t.gi]) : null;
      return "<tr" + (partial ? ' class="partial"' : "") + (g !== null ? ' data-g="' + g + '"' : "") + ">" + cells.join("") + "</tr>";
    }).join("");

    var foot = "";
    if (footer) {
      var seasons = {};
      rows.forEach(function (r) { seasons[r.season] = true; });
      var span = lead.length + (opts.rank ? 1 : 0);
      foot = '<tfoot><tr><th class="lead sticky" colspan="' + span + '">Career <span class="muted">(' +
        Object.keys(seasons).length + " seasons)</span></th>" +
        colIdx.map(function (i) { return '<td class="' + cls(i) + '">' + esc(fmt(footer[i], t.cols[i][2])) + "</td>"; }).join("") +
        "</tr></tfoot>";
    }
    return '<div class="table-scroll"><table class="stats sortable"><thead><tr>' + head +
      "</tr></thead><tbody>" + body + "</tbody>" + foot + "</table></div>";
  }

  // sections: [{id, title, html}]
  var TAB_KEY = "nba-stats-tab";
  function savedTab() { try { return localStorage.getItem(TAB_KEY); } catch (e) { return null; } }
  function tabs(sections) {
    if (!sections.length) return '<p class="muted">データがありません。</p>';
    var want = savedTab();
    var active = sections.some(function (s) { return s.id === want; }) ? want : sections[0].id;
    return '<div class="tabs" role="tablist">' + sections.map(function (s) {
      return '<button type="button" class="tab' + (s.id === active ? " active" : "") + '" data-tab="' + esc(s.id) + '">' + esc(s.title) + "</button>";
    }).join("") + "</div>" + sections.map(function (s) {
      return '<section class="panel" data-panel="' + esc(s.id) + '"' + (s.id === active ? "" : " hidden") + "><h2>" + esc(s.title) + "</h2>" + s.html + "</section>";
    }).join("");
  }

  // ---- ページ -------------------------------------------------------------
  function home() {
    var L = D.leaders, html = "";
    var teamSet = {};
    TABLES.forEach(function (t) { t.rows.forEach(function (r) { if (!isTotal(r.team)) teamSet[r.team] = true; }); });
    html += '<section class="hero"><h1>' + esc(D.title) + "</h1>" +
      (D.subtitle ? '<p class="muted">' + esc(D.subtitle) + "</p>" : "") +
      '<p class="stats-count">' + Object.keys(D.players).length + " players · " + SEASONS.length + " seasons · " +
      Object.keys(teamSet).length + " teams</p></section>";
    if (L.boards.length) {
      html += "<section><h2>" + esc(L.season) + ' Leaders <span class="muted small">' + esc(L.table) +
        (L.minG ? "（" + L.minG + "試合以上）" : "") + '</span></h2><div class="cards">' +
        L.boards.map(function (b) {
          return '<div class="card"><h3>' + esc(b.label) + "</h3><ol>" + b.rows.map(function (r) {
            return '<li><span class="who">' + playerLink(r[0]) + ' <span class="muted">' + esc(r[1]) +
              '</span></span><span class="val">' + esc(fmt(r[2], b.fmt)) + "</span></li>";
          }).join("") + "</ol></div>";
        }).join("") + "</div><p>" + '<a href="#s~' + esc(L.season) + '">' + esc(L.season) + " の全選手スタッツ →</a></p></section>";
    }
    html += '<section><h2>Seasons</h2><ul class="cols">' +
      SEASONS.slice(0, 12).map(function (s) { return "<li>" + seasonLink(s) + "</li>"; }).join("") +
      '</ul><p><a href="#seasons">すべてのシーズン →</a></p></section>';
    return { title: "Home", nav: "", html: html };
  }

  function playerPage(pid) {
    var info = D.players[pid];
    if (!info) return notFound();
    var sections = [], all = [];
    TABLES.forEach(function (t) {
      var rows = t.rows.filter(function (r) { return r.pid === pid; }).sort(bySeasonTeam);
      if (!rows.length) return;
      all = all.concat(rows);
      sections.push({ id: t.id, title: t.title, html: statTable(t, rows, ["season", "team"], { footer: t.career[pid] }) });
    });
    var seasons = {}, teams = [];
    all.slice().sort(bySeasonTeam).forEach(function (r) {
      seasons[r.season] = true;
      if (!isTotal(r.team) && teams.indexOf(r.team) < 0) teams.push(r.team);
    });
    var ss = Object.keys(seasons).sort();
    var bio = info.b.map(function (b) { return "<div><dt>" + esc(b[0]) + "</dt><dd>" + esc(b[1]) + "</dd></div>"; }).join("");
    var html = '<div class="breadcrumbs"><a href="#players">Players</a> › ' + esc(info.n) + "</div>" +
      '<section class="profile"><h1>' + esc(info.n) + "</h1>" +
      (ss.length ? '<p class="muted">' + esc(ss[0]) + " – " + esc(ss[ss.length - 1]) + " · " + ss.length + " seasons</p>" : "") +
      (bio ? '<dl class="bio">' + bio + "</dl>" : "") +
      (teams.length ? '<p class="teams">Teams: ' + teams.map(function (t) { return teamLink(t); }).join(" · ") + "</p>" : "") +
      "</section>" + tabs(sections);
    return { title: info.n, nav: "players", html: html };
  }

  function playersIndex() {
    var groups = {};
    Object.keys(D.players).forEach(function (pid) {
      var p = D.players[pid], k = p.l || p.n || pid;
      var letter = /[A-Za-z]/.test(k.charAt(0)) ? k.charAt(0).toUpperCase() : "#";
      (groups[letter] = groups[letter] || []).push({ pid: pid, key: (k + " " + p.n).toLowerCase() });
    });
    var span = {};
    TABLES.forEach(function (t) {
      t.rows.forEach(function (r) {
        var s = span[r.pid] = span[r.pid] || [r.season, r.season];
        if (r.season < s[0]) s[0] = r.season;
        if (r.season > s[1]) s[1] = r.season;
      });
    });
    var letters = Object.keys(groups).sort();
    var html = '<h1>Players <span class="muted">(' + Object.keys(D.players).length + ")</span></h1>" +
      '<p class="jump">' + letters.map(function (l) { return '<a href="#players" data-jump="letter-' + l + '">' + l + "</a>"; }).join(" ") + "</p>" +
      letters.map(function (l) {
        return '<section id="letter-' + l + '"><h2>' + l + '</h2><ul class="cols">' +
          groups[l].sort(function (a, b) { return a.key < b.key ? -1 : a.key > b.key ? 1 : 0; }).map(function (x) {
            var s = span[x.pid];
            return "<li>" + playerLink(x.pid) + (s ? ' <span class="muted">' + esc(s[0]) + " – " + esc(s[1]) + "</span>" : "") + "</li>";
          }).join("") + "</ul></section>";
      }).join("");
    return { title: "Players", nav: "players", html: html };
  }

  function seasonPage(season) {
    var i = SEASONS.indexOf(season);
    if (i < 0) return notFound();
    var sections = [];
    TABLES.forEach(function (t) {
      var rows = t.rows.filter(function (r) { return r.season === season; });
      if (!rows.length) return;
      rows.sort(function (a, b) {
        var na = nameKey(a.pid), nb = nameKey(b.pid);
        if (na !== nb) return na < nb ? -1 : 1;
        return bySeasonTeam(a, b);
      });
      sections.push({ id: t.id, title: t.title, html: statTable(t, rows, ["player", "team"], { rank: true }) });
    });
    var prev = SEASONS[i + 1], next = SEASONS[i - 1];
    var html = '<div class="breadcrumbs"><a href="#seasons">Seasons</a> › ' + esc(season) + "</div>" +
      "<h1>" + esc(season) + " Player Stats</h1>" +
      '<p class="pager">' + (prev ? "‹ " + seasonLink(prev) : "") + " " + (next ? seasonLink(next) + " ›" : "") + "</p>" +
      '<div class="filters"><label>最低試合数 <input id="min-games" type="number" class="min-games" min="0" value="0" inputmode="numeric"></label>' +
      '<label><input id="hide-partial" type="checkbox" class="hide-partial"> 移籍選手はチーム別の行を隠す（合計行のみ）</label></div>' +
      tabs(sections);
    return { title: season + " Player Stats", nav: "seasons", html: html };
  }

  function seasonsIndex() {
    return {
      title: "Seasons", nav: "seasons",
      html: '<h1>Seasons</h1><ul class="cols">' + SEASONS.map(function (s) { return "<li>" + seasonLink(s) + "</li>"; }).join("") + "</ul>",
    };
  }

  function teamRows(code) {
    var out = {};
    TABLES.forEach(function (t) {
      t.rows.forEach(function (r) {
        if (r.team !== code) return;
        var s = out[r.season] = out[r.season] || {};
        (s[t.id] = s[t.id] || []).push(r);
      });
    });
    return out;
  }

  function teamPage(code) {
    var seasons = teamRows(code);
    var keys = Object.keys(seasons).sort().reverse();
    if (!keys.length && !D.teams[code]) return notFound();
    var info = D.teams[code] || {};
    var meta = [info.c, info.d].filter(Boolean).map(esc).join(" · ");
    var rows = keys.map(function (s) {
      var ps = {};
      Object.keys(seasons[s]).forEach(function (tid) { seasons[s][tid].forEach(function (r) { ps[r.pid] = true; }); });
      var n = Object.keys(ps).length;
      return '<tr><th scope="row" class="lead sticky">' + '<a href="' + esc("#t~" + code + "~" + s) + '">' + esc(s) + "</a>" +
        '</th><td class="num" data-v="' + n + '">' + n + "</td></tr>";
    }).join("");
    var html = '<div class="breadcrumbs"><a href="#teams">Teams</a> › ' + esc(teamName(code)) + "</div>" +
      "<h1>" + esc(teamName(code)) + ' <span class="muted">(' + esc(code) + ")</span></h1>" +
      (meta ? '<p class="muted">' + meta + "</p>" : "") +
      (rows ? '<div class="table-scroll"><table class="stats sortable narrow"><thead><tr>' +
        '<th class="lead sticky" data-sort="text" tabindex="0">Season</th><th class="num" data-sort="num" tabindex="0">Players</th>' +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>" : '<p class="muted">データがありません。</p>');
    return { title: teamName(code), nav: "teams", html: html };
  }

  function teamSeasonPage(code, season) {
    var per = teamRows(code)[season];
    if (!per) return notFound();
    var sections = [];
    TABLES.forEach(function (t) {
      var rows = (per[t.id] || []).slice();
      if (!rows.length) return;
      var mi = -1;
      t.cols.forEach(function (c, i) { if (c[0] === "mp") mi = i; });
      rows.sort(function (a, b) { return (mi >= 0 ? (num(b.v[mi]) || 0) - (num(a.v[mi]) || 0) : 0); });
      sections.push({ id: t.id, title: t.title, html: statTable(t, rows, ["player"]) });
    });
    var html = '<div class="breadcrumbs"><a href="#teams">Teams</a> › <a href="#t~' + esc(code) + '">' + esc(teamName(code)) +
      "</a> › " + esc(season) + "</div><h1>" + esc(season) + " " + esc(teamName(code)) + "</h1>" +
      '<p class="muted">シーズン全体: ' + seasonLink(season) + "</p>" + tabs(sections);
    return { title: season + " " + teamName(code), nav: "teams", html: html };
  }

  function teamsIndex() {
    var codes = {};
    Object.keys(D.teams).forEach(function (c) { codes[c] = true; });
    var played = {};
    TABLES.forEach(function (t) { t.rows.forEach(function (r) { if (!isTotal(r.team)) { codes[r.team] = true; played[r.team] = true; } }); });
    var groups = {};
    Object.keys(codes).forEach(function (c) {
      var conf = (D.teams[c] && D.teams[c].c) || "";
      (groups[conf] = groups[conf] || []).push(c);
    });
    var html = "<h1>Teams</h1>" + Object.keys(groups).sort().map(function (conf) {
      return "<section>" + (conf ? "<h2>" + esc(conf) + "</h2>" : "") + '<ul class="cols">' +
        groups[conf].sort(function (a, b) { return teamName(a) < teamName(b) ? -1 : 1; }).map(function (c) {
          var label = esc(teamName(c)) + ' <span class="muted">' + esc(c) + "</span>";
          return "<li>" + (played[c] ? '<a href="#t~' + esc(c) + '">' + label + "</a>" : label) + "</li>";
        }).join("") + "</ul></section>";
    }).join("");
    return { title: "Teams", nav: "teams", html: html };
  }

  function notFound() {
    return { title: "Not found", nav: "", html: '<h1>ページが見つかりません</h1><p><a href="#">トップへ戻る</a></p>' };
  }

  // ---- ルーティング -------------------------------------------------------
  function route() {
    var h = decodeURIComponent(location.hash.replace(/^#/, ""));
    var parts = h.split("~");
    if (!h) return home();
    if (h === "players") return playersIndex();
    if (h === "seasons") return seasonsIndex();
    if (h === "teams") return teamsIndex();
    if (parts[0] === "p") return playerPage(parts.slice(1).join("~"));
    if (parts[0] === "s") return seasonPage(parts[1]);
    if (parts[0] === "t") return parts[2] ? teamSeasonPage(parts[1], parts[2]) : teamPage(parts[1]);
    return notFound();
  }

  function shell() {
    app.innerHTML =
      '<header class="site-header"><div class="wrap header-inner">' +
      '<a class="brand" href="#">' + esc(D.title) + "</a>" +
      '<nav class="nav"><a href="#players" data-nav="players">Players</a><a href="#seasons" data-nav="seasons">Seasons</a><a href="#teams" data-nav="teams">Teams</a></nav>' +
      '<div class="search"><input id="search" type="search" placeholder="選手名で検索…" autocomplete="off" aria-label="選手検索">' +
      '<ul id="search-results" class="search-results" hidden></ul></div></div></header>' +
      '<main class="wrap" id="view"></main>' +
      '<footer class="site-footer"><div class="wrap">最終更新 ' + esc(D.built) + "</div></footer>";
  }

  function render() {
    var page = route();
    document.getElementById("view").innerHTML = page.html;
    document.title = page.title + " | " + D.title;
    document.querySelectorAll("[data-nav]").forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("data-nav") === page.nav);
    });
    window.scrollTo(0, 0);
  }

  // ---- 操作（イベント委譲） ----------------------------------------------
  function sortTable(th) {
    var table = th.closest("table");
    var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
    var numeric = th.getAttribute("data-sort") === "num";
    var cur = th.classList.contains("asc") ? "asc" : th.classList.contains("desc") ? "desc" : "";
    var dir = cur ? (cur === "asc" ? "desc" : "asc") : (numeric ? "desc" : "asc");
    table.querySelectorAll("thead th").forEach(function (h) { h.classList.remove("asc", "desc"); });
    th.classList.add(dir);
    var val = function (cell) {
      if (!cell) return null;
      var v = cell.getAttribute("data-v");
      if (v === null) v = cell.textContent.trim();
      if (!numeric) return v === "" ? null : v.toLowerCase();
      var n = parseFloat(v);
      return isNaN(n) ? null : n;
    };
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      var x = val(a.cells[idx]), y = val(b.cells[idx]);
      if (x === null) return y === null ? 0 : 1;  // 空欄は常に末尾
      if (y === null) return -1;
      var r = x < y ? -1 : x > y ? 1 : 0;
      return dir === "asc" ? r : -r;
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
    renumber(table);
  }

  function renumber(table) {
    var first = table.querySelector("thead th");
    if (!first || first.textContent.trim() !== "Rk") return;
    var n = 0;
    Array.prototype.forEach.call(table.tBodies[0].rows, function (r) {
      if (!r.classList.contains("hidden")) r.cells[0].textContent = ++n;
    });
  }

  function applyFilters() {
    var mg = document.getElementById("min-games"), hp = document.getElementById("hide-partial");
    var min = mg ? parseFloat(mg.value) || 0 : 0;
    var hide = hp ? hp.checked : false;
    document.querySelectorAll("#view table.stats").forEach(function (table) {
      Array.prototype.forEach.call(table.tBodies[0].rows, function (r) {
        var g = parseFloat(r.getAttribute("data-g"));
        r.classList.toggle("hidden", (min > 0 && !isNaN(g) && g < min) || (hide && r.classList.contains("partial")));
      });
      renumber(table);
    });
  }

  document.addEventListener("click", function (e) {
    var th = e.target.closest("table.sortable thead th");
    if (th) { sortTable(th); return; }
    var tab = e.target.closest(".tab");
    if (tab) {
      var id = tab.getAttribute("data-tab");
      document.querySelectorAll(".tab").forEach(function (b) { b.classList.toggle("active", b === tab); });
      document.querySelectorAll(".panel").forEach(function (p) { p.hidden = p.getAttribute("data-panel") !== id; });
      try { localStorage.setItem(TAB_KEY, id); } catch (err) { /* 保存できなくても動作は続ける */ }
      return;
    }
    var jump = e.target.closest("[data-jump]");
    if (jump) {
      e.preventDefault();
      var target = document.getElementById(jump.getAttribute("data-jump"));
      if (target) target.scrollIntoView();
      return;
    }
    if (!e.target.closest(".search")) {
      var list = document.getElementById("search-results");
      if (list) list.hidden = true;
    }
  });
  document.addEventListener("keydown", function (e) {
    var th = e.target.closest && e.target.closest("table.sortable thead th");
    if (th && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); sortTable(th); }
  });
  document.addEventListener("input", function (e) {
    if (e.target.id === "min-games") applyFilters();
  });
  document.addEventListener("change", function (e) {
    if (e.target.id === "hide-partial") applyFilters();
  });

  // ---- 検索 ---------------------------------------------------------------
  function norm(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  var INDEX = Object.keys(D.players).map(function (pid) { return { pid: pid, n: D.players[pid].n, k: norm(D.players[pid].n) }; });
  INDEX.sort(function (a, b) { return a.k < b.k ? -1 : 1; });

  function bindSearch() {
    var input = document.getElementById("search"), list = document.getElementById("search-results"), sel = -1;
    function close() { list.hidden = true; input.value = ""; }
    function show() {
      var q = norm(input.value.trim());
      sel = -1;
      if (!q) { list.hidden = true; list.innerHTML = ""; return; }
      var hits = INDEX.filter(function (p) { return p.k.indexOf(q) !== -1; });
      hits.sort(function (a, b) {
        var sa = (" " + a.k).indexOf(" " + q) !== -1 ? 0 : 1, sb = (" " + b.k).indexOf(" " + q) !== -1 ? 0 : 1;
        return sa - sb;
      });
      list.innerHTML = hits.length ? hits.slice(0, 20).map(function (p) {
        return '<li><a href="#p~' + esc(p.pid) + '"><span>' + esc(p.n) + "</span></a></li>";
      }).join("") : '<li><a><span class="y">該当なし</span></a></li>';
      list.hidden = false;
    }
    input.addEventListener("input", show);
    input.addEventListener("keydown", function (e) {
      var items = list.querySelectorAll("li");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach(function (li, i) { li.classList.toggle("sel", i === sel); });
      } else if (e.key === "Enter") {
        var a = items[sel >= 0 ? sel : 0] && items[sel >= 0 ? sel : 0].querySelector("a[href]");
        if (a) { location.hash = a.getAttribute("href"); close(); }
      } else if (e.key === "Escape") {
        list.hidden = true;
      }
    });
    list.addEventListener("click", function (e) { if (e.target.closest("a[href]")) close(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); input.focus(); }
    });
  }

  shell();
  bindSearch();
  window.addEventListener("hashchange", render);
  render();
})();
