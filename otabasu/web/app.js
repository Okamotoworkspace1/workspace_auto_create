/* オタバス NBA データ室
 * build.py が埋め込む window.OTABASU を読み、# 付き URL でページを切り替える。
 *   #draft~2016 / #steals / #curve / #teams / #defense / #p~選手ID
 */
(function () {
  "use strict";

  var RAW = window.OTABASU;
  var view = document.getElementById("view");
  var GRADES = ["SSS", "SS", "S", "A", "B", "C", "D"];
  var GRADE_PT = { SSS: 6, SS: 5, S: 4, A: 3, B: 2, C: 1, D: 0 };
  var RECENT_FROM = RAW.recentFrom;  // これ以降の指名はキャリアが短く評価途中

  // ---------- 共通 ----------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function f1(v) { return v == null ? "–" : (Math.round(v * 10) / 10).toFixed(1); }
  function f2(v) { return v == null ? "–" : v.toFixed(2); }
  function sgn(v, d) { if (v == null) return "–"; var t = v.toFixed(d); return v > 0 ? "+" + t : t; }
  function comma(v) { return v == null ? "–" : Math.round(v).toLocaleString("en-US"); }
  function gradeBadge(g) { return g ? '<span class="gb g' + GRADE_PT[g] + '" title="評価 ' + esc(g) + "（" + GRADE_PT[g] + '点）">' + esc(g) + "</span>" : ""; }
  function plink(id, name) { return id ? '<a href="#p~' + esc(id) + '">' + esc(name) + "</a>" : esc(name); }
  function mean(a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : null; }

  // 期待値との差（0 を中心にした棒 + 数値）
  var DMAX = 0;
  function dv(v) {
    if (v == null) return '<span class="dim">–</span>';
    var w = Math.min(50, Math.abs(v) / DMAX * 50);
    var cls = v >= 0 ? "p" : "n";
    return '<span class="dv"><span class="bar"><span class="fill ' + cls + '" style="width:' + w.toFixed(1) + '%"></span></span>' +
      '<span class="v ' + cls + '">' + sgn(v, 2) + "</span></span>";
  }

  // ---------- データ ----------
  // draft: [year, round, pick, name, grade, team, as, nba3, nba2, nba1, def2, def1, dpoy, mvp, fmvp, min, mpg, score, avg, fit, dfit, id, defIdx]
  var DRAFT = RAW.draft.map(function (r, i) {
    return {
      i: i, y: r[0], rd: r[1], p: r[2], n: r[3], g: r[4], t: r[5], as: r[6], n3: r[7], n2: r[8], n1: r[9],
      d2: r[10], d1: r[11], dpoy: r[12], mvp: r[13], fmvp: r[14], min: r[15], mpg: r[16], s: r[17],
      avg: r[18], fit: r[19], df: r[20], id: r[21], di: r[22]
    };
  });
  DRAFT.forEach(function (d) { DMAX = Math.max(DMAX, Math.abs(d.df)); });
  var YEARS = Array.from(new Set(DRAFT.map(function (d) { return d.y; }))).sort();
  var DEF = RAW.defense;

  var PLAYERS = {};  // id → {name, draft, def}
  DRAFT.forEach(function (d) { var p = PLAYERS[d.id] = PLAYERS[d.id] || { id: d.id, name: d.n }; p.draft = d; });
  DEF.forEach(function (d, i) { d.i = i; var p = PLAYERS[d.id] = PLAYERS[d.id] || { id: d.id, name: d.player }; p.def = d; p.name = d.player; });

  function honors(d, big) {
    var out = [];
    function add(n, label, strong) { if (n) out.push('<span class="award' + (strong ? " big" : "") + '">' + label + (n > 1 ? "×" + n : "") + "</span>"); }
    add(d.mvp, "MVP", true); add(d.fmvp, "FMVP", true); add(d.dpoy, "DPOY", true);
    if (big) {
      add(d.n1, "All-NBA 1st"); add(d.n2, "All-NBA 2nd"); add(d.n3, "All-NBA 3rd");
      add(d.d1, "All-DF 1st"); add(d.d2, "All-DF 2nd"); add(d.as, "オールスター");
    }
    return out.join("");
  }
  function triple(a, b, c) { return (a + b + c) ? a + "-" + b + "-" + c : '<span class="dim">–</span>'; }

  // ---------- ソートできる表 ----------
  // cols: {k, label, cls, num, val(d), html(d), title, sort:false}
  var SORT = {}, INIT_SORT = {};
  function table(id, cols, rows, opts) {
    opts = opts || {};
    if (opts.sort) INIT_SORT[id] = opts.sort;
    var st = SORT[id] || opts.sort || null;
    var list = rows.slice();
    if (st) {
      var col = cols.filter(function (c) { return c.k === st.k; })[0];
      if (col) {
        list.sort(function (a, b) {
          var x = col.val(a), y = col.val(b);
          var xn = x == null || x === "", yn = y == null || y === "";
          if (xn || yn) return xn && yn ? 0 : xn ? 1 : -1;  // 空欄は常に末尾
          var r = typeof x === "string" ? x.localeCompare(y) : x - y;
          return st.dir * r;
        });
      }
    }
    var head = cols.map(function (c) {
      var arr = st && st.k === c.k ? '<span class="arr">' + (st.dir < 0 ? "▼" : "▲") + "</span>" : "";
      var sortable = c.sort !== false && c.val;
      return '<th class="' + (c.cls || "") + (sortable ? "" : " nosort") + '"' + (sortable ? ' data-t="' + id + '" data-k="' + c.k + '" tabindex="0"' : "") +
        (c.title ? ' title="' + esc(c.title) + '"' : "") + ">" + c.label + arr + "</th>";
    }).join("");
    var body = list.map(function (d, n) {
      if (opts.sep && !st) {
        var s = opts.sep(d, list[n - 1]);
        if (s) return '<tr class="sep"><td colspan="' + cols.length + '">' + s + "</td></tr>" + rowHtml(d, n);
      }
      return rowHtml(d, n);
    }).join("");
    function rowHtml(d, n) {
      return "<tr" + (opts.mark && opts.mark(d) ? ' class="me"' : "") + ">" + cols.map(function (c) { return '<td class="' + (c.cls || "") + '">' + c.html(d, n) + "</td>"; }).join("") + "</tr>";
    }
    return '<div class="tscroll"><table class="t" data-table="' + id + '"><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>";
  }
  var DEFAULT_DIR = {};  // 列ごとの最初の並び順（数値は大きい順）
  function onSort(th) {
    var id = th.getAttribute("data-t"), k = th.getAttribute("data-k");
    var cur = SORT[id] || INIT_SORT[id];
    var first = DEFAULT_DIR[id + ":" + k] || -1;
    SORT[id] = cur && cur.k === k ? { k: k, dir: -cur.dir } : { k: k, dir: first };
    render(true);
  }

  // ---------- DF 採点（元ページと同じ計算） ----------
  var QUAL_G = 50, QUAL_MP = 750;
  var METR = { dbpm: 1, diff: -1, dfg: -1, drtg: -1, stlpct: 1, blkpct: 1, drbpct: 1 };
  var PILLARS = [
    { key: "impact", label: "総合インパクト", hint: "DBPM", members: [["dbpm", 1]] },
    { key: "suppress", label: "被シュート抑制", hint: "DIFF%・DFG%", members: [["diff", 0.7], ["dfg", 0.3]] },
    { key: "team", label: "チーム失点", hint: "DRtg", members: [["drtg", 1]] },
    { key: "steal", label: "ボール奪取", hint: "STL%", members: [["stlpct", 1]] },
    { key: "rim", label: "リム保護", hint: "BLK%", members: [["blkpct", 1]] },
    { key: "reb", label: "守備リバウンド", hint: "DRB%", members: [["drbpct", 1]] }
  ];
  var PRESETS = {
    balanced: { label: "バランス", w: { impact: 30, suppress: 30, team: 12, steal: 12, rim: 10, reb: 6 } },
    stopper: { label: "ストッパー", w: { impact: 20, suppress: 45, team: 15, steal: 5, rim: 10, reb: 5 } },
    disruptor: { label: "ディスラプター", w: { impact: 25, suppress: 15, team: 10, steal: 30, rim: 15, reb: 5 } },
    impact: { label: "インパクト", w: { impact: 45, suppress: 20, team: 25, steal: 4, rim: 4, reb: 2 } },
    rim: { label: "リム保護", w: { impact: 20, suppress: 22, team: 10, steal: 6, rim: 37, reb: 5 } }
  };
  function posGroup(pos) { var p = (pos || "").split("-")[0]; return p === "C" ? "C" : (p === "PG" || p === "SG") ? "G" : "F"; }
  DEF.forEach(function (d) { d.grp = posGroup(d.pos); d.qual = (d.g || 0) >= QUAL_G && (d.mp || 0) >= QUAL_MP; });

  // 重みとポジション補正から、全員のスコア（偏差値）を返す
  function dfScores(W, posadj) {
    var pool = DEF.filter(function (d) { return d.qual; });
    function stats(rows) {
      var s = {};
      Object.keys(METR).forEach(function (m) {
        var v = rows.map(function (r) { return r[m]; }).filter(function (x) { return x != null; });
        var mu = mean(v) || 0;
        var sd = Math.sqrt(v.reduce(function (a, b) { return a + (b - mu) * (b - mu); }, 0) / (v.length || 1)) || 1;
        s[m] = [mu, sd];
      });
      return s;
    }
    var S = posadj
      ? { C: stats(pool.filter(function (r) { return r.grp === "C"; })), F: stats(pool.filter(function (r) { return r.grp === "F"; })), G: stats(pool.filter(function (r) { return r.grp === "G"; })) }
      : stats(pool);
    var sw = Object.keys(W).reduce(function (a, k) { return a + W[k]; }, 0) || 1;
    function z(d, m) { var st = posadj ? S[d.grp] : S; var v = d[m]; return v == null ? 0 : ((v - st[m][0]) / st[m][1]) * METR[m]; }
    var raw = DEF.map(function (d) {
      return PILLARS.reduce(function (s, p) {
        return s + (W[p.key] / sw) * p.members.reduce(function (a, m) { return a + m[1] * z(d, m[0]); }, 0);
      }, 0);
    });
    var pr = pool.map(function (d) { return raw[d.i]; });
    var mu = mean(pr), sd = Math.sqrt(pr.reduce(function (a, b) { return a + (b - mu) * (b - mu); }, 0) / (pr.length || 1)) || 1;
    return raw.map(function (r) { return 50 + 10 * (r - mu) / sd; });
  }
  var BAL = dfScores(PRESETS.balanced.w, false);
  var BAL_RANK = {};
  DEF.filter(function (d) { return d.qual; }).sort(function (a, b) { return BAL[b.i] - BAL[a.i]; })
    .forEach(function (d, n) { BAL_RANK[d.i] = n + 1; });
  var QUAL_N = Object.keys(BAL_RANK).length;

  // ---------- トップ ----------
  function pageHome() {
    var steals = DRAFT.filter(function (d) { return d.y < RECENT_FROM; }).sort(function (a, b) { return b.df - a.df; }).slice(0, 5);
    var dtop = DEF.filter(function (d) { return d.qual; }).sort(function (a, b) { return BAL[b.i] - BAL[a.i]; }).slice(0, 5);
    var latest = YEARS[YEARS.length - 1];
    var top5 = DRAFT.filter(function (d) { return d.y === latest && d.rd === 1; }).slice(0, 5);
    function li(name, id, meta, v) { return '<li><span class="who">' + plink(id, name) + (meta ? ' <span class="team">' + esc(meta) + "</span>" : "") + '</span><span class="v">' + v + "</span></li>"; }
    return {
      title: "オタバス NBA データ室", nav: "",
      html:
        '<section class="hero"><span class="plate"><img src="' + window.OTABASU_LOGO + '" alt="オタバス"></span><div>' +
        '<div class="eyebrow">OTABASU · NBA DATA ROOM</div><h1>数字で語る、オタクのNBA。</h1>' +
        '<p class="lead">オタバスが独自に採点した<b>2005〜' + latest + '年のドラフト全' + DRAFT.length.toLocaleString() + '人の評価</b>と、' +
        '<b>2025-26シーズンのディフェンス総合ランキング</b>をまとめたデータ室です。動画で紹介した数字の元データはここで確認できます。</p></div></section>' +

        '<div class="grid three section">' +
        '<div class="card entry"><span class="eyebrow">Draft Review</span><h3><a href="#draft">ドラフト評価</a></h3>' +
        '<p class="muted small">年ごとの全指名選手を SSS〜D で評価。指名順位から見た「期待値」との差で、当たり指名と期待外れが一目でわかります。</p>' +
        '<div class="chips">' + YEARS.slice(-6).reverse().map(function (y) { return '<a class="chip" href="#draft~' + y + '">' + y + "</a>"; }).join("") + "</div>" +
        '<a class="go" href="#draft">全21年分を見る →</a></div>' +
        '<div class="card entry"><span class="eyebrow">Steals</span><h3><a href="#steals">歴代の上振れ指名 TOP5</a></h3>' +
        '<ol class="rank">' + steals.map(function (d) { return li(d.n, d.id, d.y + " #" + d.p, sgn(d.df, 2)); }).join("") + "</ol>" +
        '<a class="go" href="#steals">上振れ・下振れランキング →</a></div>' +
        '<div class="card entry"><span class="eyebrow">Defense 2025-26</span><h3><a href="#defense">DF総合ランキング TOP5</a></h3>' +
        '<ol class="rank">' + dtop.map(function (d) { return li(d.player, d.id, d.team, BAL[d.i].toFixed(1)); }).join("") + "</ol>" +
        '<a class="go" href="#defense">重みを変えて見る →</a></div></div>' +

        '<div class="grid two section">' +
        '<div class="card"><span class="eyebrow">Draft ' + latest + '</span><h3>' + latest + '年 1巡目上位</h3><ol class="rank">' +
        top5.map(function (d) { return li(d.n, d.id, d.t, gradeBadge(d.g)); }).join("") + '</ol><p class="muted small">直近の指名はキャリアが短いため、評価は今後変わります。</p></div>' +
        '<div class="card"><span class="eyebrow">How to read</span><h3>評価の読み方</h3>' +
        '<p class="small">評価 SSS〜D を 6〜0 点に換算し、指名順位ごとの期待値（近似曲線）と比べています。差がプラスなら「指名順位以上の当たり」、マイナスなら「期待を下回った」指名です。</p>' +
        '<div class="dist" style="margin-top:8px">' + GRADES.map(function (g) { return "<span>" + gradeBadge(g) + GRADE_PT[g] + "点</span>"; }).join("") + "</div>" +
        '<p class="small" style="margin-top:10px"><a href="#curve">指名順位と期待値のグラフを見る →</a></p></div></div>'
    };
  }

  // ---------- ドラフト年 ----------
  function draftCols(withYear) {
    var c = [];
    if (withYear) c.push({ k: "y", label: "年", val: function (d) { return d.y; }, html: function (d) { return '<a href="#draft~' + d.y + '">' + d.y + "</a>"; } });
    c.push(
      { k: "p", label: "指名", val: function (d) { return d.p; }, html: function (d) { return d.p; } },
      { k: "n", label: "選手", cls: "l name stick", val: function (d) { return d.n; }, html: function (d) { return plink(d.id, d.n); } },
      { k: "g", label: "評価", cls: "c", val: function (d) { return d.s; }, html: function (d) { return gradeBadge(d.g); } },
      { k: "t", label: "初年度", cls: "l", title: "初年度に所属したチーム", val: function (d) { return d.t; }, html: function (d) { return d.t ? esc(d.t) : '<span class="dim">–</span>'; } },
      { k: "as", label: "AS", title: "オールスター選出回数", val: function (d) { return d.as; }, html: function (d) { return d.as || '<span class="dim">0</span>'; } },
      { k: "nba", label: "All-NBA", title: "1st-2nd-3rd の選出回数", val: function (d) { return d.n1 * 3 + d.n2 * 2 + d.n3; }, html: function (d) { return triple(d.n1, d.n2, d.n3); } },
      { k: "adf", label: "All-DF", title: "1st-2nd の選出回数", val: function (d) { return d.d1 * 2 + d.d2; }, html: function (d) { return (d.d1 + d.d2) ? d.d1 + "-" + d.d2 : '<span class="dim">–</span>'; } },
      { k: "aw", label: "主要タイトル", cls: "l", sort: false, html: function (d) { return honors(d, false); } },
      { k: "min", label: "総出場分", val: function (d) { return d.min; }, html: function (d) { return comma(d.min); } },
      { k: "mpg", label: "平均分", val: function (d) { return d.mpg; }, html: function (d) { return f1(d.mpg); } },
      { k: "s", label: "得点", title: "評価を 0〜6 点に換算", val: function (d) { return d.s; }, html: function (d) { return d.s; } },
      { k: "fit", label: "期待値", title: "指名順位から見た期待得点（近似曲線）", val: function (d) { return d.fit; }, html: function (d) { return f2(d.fit); } },
      { k: "df", label: "期待値との差", title: "得点 − 期待値", val: function (d) { return d.df; }, html: function (d) { return dv(d.df); } }
    );
    return c;
  }
  ["p", "y", "n", "t"].forEach(function (k) { DEFAULT_DIR["draft:" + k] = 1; DEFAULT_DIR["dyear:" + k] = 1; });

  function pageDraft(year) {
    year = +year || YEARS[YEARS.length - 1];
    if (YEARS.indexOf(year) < 0) return notFound();
    var rows = DRAFT.filter(function (d) { return d.y === year; });
    var cnt = {}; GRADES.forEach(function (g) { cnt[g] = 0; }); rows.forEach(function (d) { cnt[d.g]++; });
    var best = rows.slice().sort(function (a, b) { return b.df - a.df; })[0];
    var worst = rows.slice().sort(function (a, b) { return a.df - b.df; })[0];
    var top = rows.filter(function (d) { return d.s >= 5; }).length;
    var rf = window.__round || "all";
    var shown = rows.filter(function (d) { return rf === "all" || d.rd === +rf; });
    var avgDf = mean(rows.map(function (d) { return d.df; }));
    return {
      title: year + "年 NBAドラフト評価", nav: "draft",
      html:
        '<div class="eyebrow">Draft Review</div><h1>' + year + '年 NBAドラフト</h1>' +
        '<div class="yearbar" role="navigation" aria-label="年を選ぶ">' + YEARS.map(function (y) {
          return '<a class="chip' + (y === year ? " on" : "") + '" href="#draft~' + y + '"' + (y === year ? ' aria-current="page"' : "") + ">" + y + "</a>";
        }).join("") + "</div>" +
        (year >= RECENT_FROM ? '<div class="note">' + year + '年組はキャリアがまだ短いため、評価は今後変わる可能性があります。</div>' : "") +
        '<div class="summary">' +
        '<div class="card"><h3>評価の内訳</h3><div class="dist">' + GRADES.map(function (g) { return "<span>" + gradeBadge(g) + cnt[g] + "</span>"; }).join("") + "</div>" +
        '<div class="kv" style="margin-top:8px"><span class="k">S以上（4点以上）</span><b class="num">' + rows.filter(function (d) { return d.s >= 4; }).length + "人</b></div>" +
        '<div class="kv"><span class="k">SS以上（5点以上）</span><b class="num">' + top + "人</b></div></div>" +
        '<div class="card"><h3>この年のハイライト</h3>' +
        '<div class="kv"><span class="k">最大の上振れ</span><span>' + plink(best.id, best.n) + ' <span class="team">#' + best.p + "</span></span></div>" +
        '<div class="kv"><span class="k"></span>' + dv(best.df) + "</div>" +
        '<div class="kv"><span class="k">最大の下振れ</span><span>' + plink(worst.id, worst.n) + ' <span class="team">#' + worst.p + "</span></span></div>" +
        '<div class="kv"><span class="k"></span>' + dv(worst.df) + "</div></div>" +
        '<div class="card"><h3>年全体の当たり度</h3><p class="small muted">全指名の「期待値との差」の平均。プラスほど豊作の年です。</p>' +
        '<div class="kv"><span class="k">平均</span>' + dv(avgDf) + "</div>" +
        '<div class="kv"><span class="k">21年中の順位</span><b class="num">' + yearRank(year) + "位</b></div></div>" +
        "</div>" +
        '<div class="controls"><span class="seg" role="group" aria-label="巡目">' +
        [["all", "全員"], ["1", "1巡目"], ["2", "2巡目"]].map(function (o) {
          return '<button type="button" data-round="' + o[0] + '" aria-pressed="' + (rf === o[0]) + '">' + o[1] + "</button>";
        }).join("") + '</span><span class="muted small">列名をクリックで並べ替え（もう一度で逆順）</span></div>' +
        table("dyear", draftCols(false), shown, {
          sep: function (d, prev) { return (!prev || prev.rd !== d.rd) && rf === "all" ? d.rd + "巡目" : ""; }
        })
    };
  }
  var YEAR_RANK = null;
  function yearRank(y) {
    if (!YEAR_RANK) {
      YEAR_RANK = {};
      YEARS.map(function (yy) { return [yy, mean(DRAFT.filter(function (d) { return d.y === yy; }).map(function (d) { return d.df; }))]; })
        .sort(function (a, b) { return b[1] - a[1]; }).forEach(function (a, n) { YEAR_RANK[a[0]] = n + 1; });
    }
    return YEAR_RANK[y];
  }

  // ---------- 上振れ・下振れ ----------
  function pageSteals() {
    var o = window.__steals = window.__steals || { from: YEARS[0], to: YEARS[YEARS.length - 1], round: "all", recent: true, n: 30 };
    var pool = DRAFT.filter(function (d) {
      return d.y >= o.from && d.y <= o.to && (o.round === "all" || d.rd === +o.round) && (!o.recent || d.y < RECENT_FROM);
    });
    var up = pool.slice().sort(function (a, b) { return b.df - a.df; }).slice(0, o.n);
    var down = pool.slice().sort(function (a, b) { return a.df - b.df; }).slice(0, o.n);
    var cols = [
      { k: "r", label: "#", sort: false, html: function (d, n) { return n + 1; } },
      { k: "n", label: "選手", cls: "l name stick", sort: false, html: function (d) { return plink(d.id, d.n); } },
      { k: "yp", label: "年・指名", sort: false, html: function (d) { return '<a href="#draft~' + d.y + '">' + d.y + "</a> #" + d.p; } },
      { k: "g", label: "評価", cls: "c", sort: false, html: function (d) { return gradeBadge(d.g); } },
      { k: "fit", label: "期待値", sort: false, html: function (d) { return f2(d.fit); } },
      { k: "df", label: "期待値との差", sort: false, html: function (d) { return dv(d.df); } }
    ];
    function opt(v, cur) { return '<option value="' + v + '"' + (v === cur ? " selected" : "") + ">" + v + "</option>"; }
    return {
      title: "上振れ・下振れ指名ランキング", nav: "steals",
      html:
        '<div class="eyebrow">Steals &amp; Busts</div><h1>上振れ・下振れ指名ランキング</h1>' +
        '<p class="lead">指名順位から見た期待値と、実際の評価との差で並べました。上位指名ほど期待値が高いので、下振れには上位指名が、上振れには下位指名が並びやすくなります。</p>' +
        '<div class="controls">' +
        '<label>期間 <select id="s-from">' + YEARS.map(function (y) { return opt(y, o.from); }).join("") + '</select> 〜 <select id="s-to">' + YEARS.map(function (y) { return opt(y, o.to); }).join("") + "</select></label>" +
        '<span class="seg" role="group" aria-label="巡目">' + [["all", "全員"], ["1", "1巡目"], ["2", "2巡目"]].map(function (x) {
          return '<button type="button" data-sround="' + x[0] + '" aria-pressed="' + (o.round === x[0]) + '">' + x[1] + "</button>";
        }).join("") + "</span>" +
        '<label><input id="s-recent" type="checkbox"' + (o.recent ? " checked" : "") + "> " + RECENT_FROM + "年以降の指名を除く（評価途中のため）</label>" +
        '<span class="muted small">対象 ' + pool.length + "人</span></div>" +
        '<div class="grid two">' +
        '<div><h2>上振れ TOP' + o.n + "</h2>" + table("up", cols, up) + "</div>" +
        '<div><h2>下振れ TOP' + o.n + "</h2>" + table("down", cols, down) + "</div></div>"
    };
  }

  // ---------- 指名順位と期待値 ----------
  function pageCurve() {
    var picks = [];
    for (var p = 1; p <= 60; p++) {
      var rs = DRAFT.filter(function (d) { return d.p === p; });
      if (!rs.length) continue;
      picks.push({ p: p, avg: rs[0].avg, fit: rs[0].fit, real: mean(rs.map(function (d) { return d.s; })), n: rs.length });
    }
    var bands = [[1, 5], [6, 10], [11, 20], [21, 30], [31, 45], [46, 60]];
    var brow = bands.map(function (b) {
      var rs = DRAFT.filter(function (d) { return d.p >= b[0] && d.p <= b[1] && d.y < RECENT_FROM; });
      var c = {}; GRADES.forEach(function (g) { c[g] = 0; }); rs.forEach(function (d) { c[d.g]++; });
      return { b: b, n: rs.length, c: c, avg: mean(rs.map(function (d) { return d.s; })) };
    });
    var heat = '<div class="tscroll"><table class="t heat"><thead><tr><th class="l nosort">指名順位</th><th class="nosort">人数</th>' +
      GRADES.map(function (g) { return '<th class="c nosort">' + gradeBadge(g) + "</th>"; }).join("") +
      '<th class="nosort">平均得点</th><th class="nosort">S以上の割合</th></tr></thead><tbody>' +
      brow.map(function (r) {
        return '<tr><td class="l name">' + r.b[0] + "〜" + r.b[1] + "位</td><td>" + r.n + "</td>" +
          GRADES.map(function (g) {
            var pct = r.c[g] / r.n * 100;
            return '<td class="c h" style="background:color-mix(in srgb, var(--orange) ' + Math.round(pct * 0.9) + '%, transparent)" title="' + g + ": " + r.c[g] + '人">' + (pct ? Math.round(pct) + "%" : '<span class="dim">0</span>') + "</td>";
          }).join("") +
          "<td>" + f2(r.avg) + "</td><td>" + Math.round((r.c.SSS + r.c.SS + r.c.S) / r.n * 100) + "%</td></tr>";
      }).join("") + "</tbody></table></div>";
    return {
      title: "指名順位と期待値", nav: "curve",
      html:
        '<div class="eyebrow">Expected Value by Pick</div><h1>指名順位と期待値</h1>' +
        '<p class="lead">指名順位ごとの平均得点と、それをなめらかにした近似曲線です。この近似曲線を各指名の「期待値」として、上振れ・下振れを計算しています。</p>' +
        '<div class="card section"><h2>指名順位別の平均得点（0〜6点）</h2>' +
        '<div class="legend"><span><i class="ln"></i>近似曲線（期待値）</span><span><i class="dt"></i>指名順位ごとの平均値</span></div>' +
        '<div class="chart" id="curve-chart"></div>' +
        '<p class="small muted">平均値と近似曲線は元シートの値です。ツールチップの「現データの平均」は、ここに載っている ' + YEARS[0] + "〜" + YEARS[YEARS.length - 1] + " 年の評価から計算し直した値です。</p></div>" +
        '<div class="section"><h2>指名順位帯ごとの評価の分布</h2><p class="small muted">' + YEARS[0] + "〜" + (RECENT_FROM - 1) + "年の指名（評価途中の" + RECENT_FROM + "年以降は除外）。色が濃いほど割合が高い。</p>" + heat + "</div>",
      after: function () { drawCurve(picks); }
    };
  }

  function drawCurve(picks) {
    var box = document.getElementById("curve-chart");
    if (!box) return;
    var W = 760, H = 320, m = { l: 40, r: 16, t: 14, b: 36 };
    var ymax = 4;
    var x = function (p) { return m.l + (p - 1) / 59 * (W - m.l - m.r); };
    var y = function (v) { return H - m.b - v / ymax * (H - m.t - m.b); };
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="指名順位別の平均得点と近似曲線">';
    s += '<g class="grid">';
    for (var v = 0; v <= ymax; v++) s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(v) + '" y2="' + y(v) + '"/>';
    s += "</g><g class=\"axis\">";
    for (v = 0; v <= ymax; v++) s += '<text x="' + (m.l - 8) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + "</text>";
    [1, 10, 20, 30, 40, 50, 60].forEach(function (p) { s += '<text x="' + x(p) + '" y="' + (H - m.b + 18) + '" text-anchor="middle">' + p + "位</text>"; });
    s += '</g><line class="base" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(0) + '" y2="' + y(0) + '"/>';
    // 1巡目と2巡目の境目
    s += '<line x1="' + ((x(30) + x(31)) / 2) + '" x2="' + ((x(30) + x(31)) / 2) + '" y1="' + m.t + '" y2="' + y(0) + '" stroke="var(--line-strong)" stroke-dasharray="3 4"/>';
    s += '<text class="lbl" x="' + ((x(30) + x(31)) / 2 + 6) + '" y="' + (m.t + 12) + '">2巡目 →</text>';
    s += '<path d="' + picks.map(function (d, i) { return (i ? "L" : "M") + x(d.p).toFixed(1) + " " + y(d.fit).toFixed(1); }).join("") +
      '" fill="none" stroke="var(--series-a)" stroke-width="2.5" stroke-linejoin="round"/>';
    s += picks.map(function (d) { return '<circle cx="' + x(d.p).toFixed(1) + '" cy="' + y(d.avg).toFixed(1) + '" r="4" fill="var(--series-b)" stroke="var(--surface)" stroke-width="2"/>'; }).join("");
    // 直接ラベル（線の右寄り、点の左上）
    var lp = picks[picks.length - 12] || picks[0];
    s += '<text class="lbl" x="' + (x(lp.p) + 6) + '" y="' + (y(lp.fit) - 10) + '" style="fill:var(--series-a)">近似曲線</text>';
    s += '<text class="lbl" x="' + (x(1) + 10) + '" y="' + (y(picks[0].avg) + 4) + '" style="fill:var(--series-b)">平均値</text>';
    s += '<line id="xh" y1="' + m.t + '" y2="' + y(0) + '" stroke="var(--faint)" stroke-width="1" visibility="hidden"/>';
    s += '<rect x="' + m.l + '" y="' + m.t + '" width="' + (W - m.l - m.r) + '" height="' + (H - m.t - m.b) + '" fill="transparent" id="hit"/>';
    s += "</svg>";
    box.innerHTML = s + '<div class="tip" hidden></div>';
    var svg = box.querySelector("svg"), tip = box.querySelector(".tip"), xh = box.querySelector("#xh");
    function move(ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * W;
      var p = Math.max(1, Math.min(60, Math.round((px - m.l) / (W - m.l - m.r) * 59 + 1)));
      var d = picks.filter(function (q) { return q.p === p; })[0];
      if (!d) return;
      xh.setAttribute("x1", x(p)); xh.setAttribute("x2", x(p)); xh.setAttribute("visibility", "visible");
      tip.innerHTML = "<b>" + p + "位指名</b>（" + d.n + "人）<br>近似曲線（期待値） <b>" + f2(d.fit) + "</b><br>平均値 <b>" + f2(d.avg) + "</b><br><span class=\"muted\">現データの平均 " + f2(d.real) + "</span>";
      tip.hidden = false;
      var left = x(p) / W * r.width + 12;
      if (left + 170 > r.width) left = x(p) / W * r.width - 182;
      tip.style.left = left + "px"; tip.style.top = (y(Math.max(d.avg, d.fit)) / H * r.height - 10) + "px";
    }
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerdown", move);
    svg.addEventListener("pointerleave", function () { tip.hidden = true; xh.setAttribute("visibility", "hidden"); });
  }

  // ---------- チーム別 ----------
  var MERGE = { NJN: "BKN", NOH: "NOP", NOK: "NOP", SEA: "OKC" };
  function pageTeams() {
    var o = window.__teams = window.__teams || { merge: true, recent: true };
    var g = {};
    DRAFT.forEach(function (d) {
      if (!d.t || d.t === "-") return;
      if (o.recent && d.y >= RECENT_FROM) return;
      var t = o.merge && MERGE[d.t] ? MERGE[d.t] : d.t;
      (g[t] = g[t] || []).push(d);
    });
    var rows = Object.keys(g).map(function (t) {
      var rs = g[t];
      var best = rs.slice().sort(function (a, b) { return b.df - a.df; })[0];
      return { t: t, n: rs.length, s: mean(rs.map(function (d) { return d.s; })), df: mean(rs.map(function (d) { return d.df; })),
        sum: rs.reduce(function (a, d) { return a + d.df; }, 0), top: rs.filter(function (d) { return d.s >= 5; }).length, best: best };
    });
    var cols = [
      { k: "t", label: "チーム", cls: "l name stick", val: function (r) { return r.t; }, html: function (r) { return esc(r.t); } },
      { k: "n", label: "人数", val: function (r) { return r.n; }, html: function (r) { return r.n; } },
      { k: "s", label: "平均得点", val: function (r) { return r.s; }, html: function (r) { return f2(r.s); } },
      { k: "df", label: "平均の差", title: "期待値との差の平均", val: function (r) { return r.df; }, html: function (r) { return dv(r.df); } },
      { k: "sum", label: "差の合計", val: function (r) { return r.sum; }, html: function (r) { return sgn(r.sum, 1); } },
      { k: "top", label: "SS以上", val: function (r) { return r.top; }, html: function (r) { return r.top || '<span class="dim">0</span>'; } },
      { k: "best", label: "いちばんの当たり", cls: "l", val: function (r) { return r.best.df; }, html: function (r) { return plink(r.best.id, r.best.n) + ' <span class="team">' + r.best.y + " #" + r.best.p + "</span> " + gradeBadge(r.best.g); } }
    ];
    DEFAULT_DIR["teams:t"] = 1;
    return {
      title: "チーム別", nav: "teams",
      html:
        '<div class="eyebrow">By Team</div><h1>初年度所属チーム別</h1>' +
        '<p class="lead">選手が<b>ルーキーシーズンに所属したチーム</b>で集計しています（指名したチームとは限りません。ドラフト当日のトレードなどで変わる場合があります）。</p>' +
        '<div class="controls"><label><input id="t-merge" type="checkbox"' + (o.merge ? " checked" : "") + "> 移転・改名前のチームをまとめる（NJN→BKN、NOH・NOK→NOP、SEA→OKC）</label>" +
        '<label><input id="t-recent" type="checkbox"' + (o.recent ? " checked" : "") + "> " + RECENT_FROM + "年以降の指名を除く</label></div>" +
        table("teams", cols, rows, { sort: { k: "df", dir: -1 } })
    };
  }

  // ---------- DF ランキング ----------
  var DFS = { preset: "balanced", w: Object.assign({}, PRESETS.balanced.w), posadj: false, pos: "ALL", qual: true, q: "" };
  function dfCols(scores) {
    var c = [
      { k: "rk", label: "#", sort: false, html: function (d, n) { return n + 1; } },
      { k: "player", label: "選手", cls: "l name stick", val: function (d) { return d.player; }, html: function (d) { return plink(d.id, d.player) + '<span class="team">' + esc(d.team) + "</span>"; } },
      { k: "score", label: "総合", cls: "l", val: function (d) { return scores[d.i]; }, html: function (d) {
        var v = scores[d.i], pct = Math.max(3, Math.min(100, (v - 35) / 43 * 100));
        return '<span class="scorebar"><b>' + v.toFixed(1) + '</b><span class="track"><span class="fill" style="width:' + pct + '%"></span></span></span>';
      } },
      { k: "grp", label: "POS", cls: "c", val: function (d) { return d.grp; }, html: function (d) { return '<span class="posb" title="' + esc(d.pos) + '">' + d.grp + "</span>"; } },
      { k: "g", label: "G", val: function (d) { return d.g; }, html: function (d) { return d.g; } },
      { k: "mpg", label: "MPG", val: function (d) { return d.mpg; }, html: function (d) { return f1(d.mpg); } },
      { k: "dbpm", label: "DBPM", val: function (d) { return d.dbpm; }, html: function (d) { return f1(d.dbpm); } },
      { k: "dws", label: "DWS", val: function (d) { return d.dws; }, html: function (d) { return f1(d.dws); } },
      { k: "drtg", label: "DRtg", val: function (d) { return d.drtg; }, html: function (d) { return d.drtg == null ? '<span class="dim">–</span>' : d.drtg; } },
      { k: "dfg", label: "DFG%", val: function (d) { return d.dfg; }, html: function (d) { return f1(d.dfg); } },
      { k: "diff", label: "DIFF%", val: function (d) { return d.diff; }, html: function (d) { return d.diff == null ? '<span class="dim">–</span>' : sgn(d.diff, 1); } },
      { k: "blkpct", label: "BLK%", val: function (d) { return d.blkpct; }, html: function (d) { return f1(d.blkpct); } },
      { k: "stlpct", label: "STL%", val: function (d) { return d.stlpct; }, html: function (d) { return f1(d.stlpct); } },
      { k: "drbpct", label: "DRB%", val: function (d) { return d.drbpct; }, html: function (d) { return f1(d.drbpct); } },
      { k: "hon", label: "受賞", cls: "l", val: function (d) { return d.honors ? 1 : 0; }, html: function (d) { return d.honors ? '<span class="award big">' + esc(d.honors) + "</span>" : '<span class="dim">–</span>'; } },
      { k: "dr", label: "ドラフト", cls: "l", val: function (d) { return d.di != null ? DRAFT[d.di].s : null; }, html: function (d) {
        if (d.di == null) return '<span class="dim">–</span>';
        var r = DRAFT[d.di];
        return '<a href="#draft~' + r.y + '">' + r.y + "</a> #" + r.p + " " + gradeBadge(r.g);
      } }
    ];
    ["player", "grp", "drtg", "dfg", "diff"].forEach(function (k) { DEFAULT_DIR["df:" + k] = 1; });
    return c;
  }
  function pageDefense() {
    var scores = dfScores(DFS.w, DFS.posadj);
    var rows = DEF.filter(function (d) {
      if (DFS.pos !== "ALL" && d.grp !== DFS.pos) return false;
      if (DFS.qual && !d.qual) return false;
      if (DFS.q && d.player.toLowerCase().indexOf(DFS.q.toLowerCase()) < 0) return false;
      return true;
    });
    var sw = Object.keys(DFS.w).reduce(function (a, k) { return a + DFS.w[k]; }, 0) || 1;
    var cols = dfCols(scores);
    var html =
      '<div class="eyebrow">Defense 2025-26</div><h1>ディフェンス総合ランキング 2025-26</h1>' +
      '<p class="lead">評価対象（' + QUAL_G + "試合以上かつ" + QUAL_MP + "分以上・" + QUAL_N + "人）の守備指標を偏差値化し、重み付きで合計した総合スコア（平均50）で順位付けしています。重みはスライダーとプリセットで変えられます。</p>" +
      '<div class="card section"><div class="controls" style="margin:0"><b>プリセット</b><span class="seg" role="group" aria-label="プリセット">' +
      Object.keys(PRESETS).map(function (k) { return '<button type="button" data-preset="' + k + '" aria-pressed="' + (DFS.preset === k) + '">' + PRESETS[k].label + "</button>"; }).join("") +
      '</span><span class="seg" role="group" aria-label="ポジション補正">' +
      '<button type="button" data-adj="0" aria-pressed="' + !DFS.posadj + '">全体で比較</button><button type="button" data-adj="1" aria-pressed="' + DFS.posadj + '">C/F/G内で比較</button></span></div>' +
      '<div class="sliders">' + PILLARS.map(function (p) {
        return '<div class="slider"><div class="top"><span>' + p.label + " <small>" + p.hint + '</small></span><span class="pc" id="pc-' + p.key + '">' + Math.round(DFS.w[p.key] / sw * 100) + "%</span></div>" +
          '<input type="range" min="0" max="50" step="1" id="sl-' + p.key + '" data-pillar="' + p.key + '" value="' + DFS.w[p.key] + '" aria-label="' + p.label + 'の重み"></div>';
      }).join("") + "</div></div>" +
      '<div class="controls"><label>選手 <input id="df-q" type="search" value="' + esc(DFS.q) + '" placeholder="名前で絞り込み" style="font:inherit;padding:5px 8px;border:1px solid var(--line-strong);border-radius:8px;background:var(--surface);color:var(--ink)"></label>' +
      '<span class="seg" role="group" aria-label="ポジション">' + ["ALL", "C", "F", "G"].map(function (p) { return '<button type="button" data-pos="' + p + '" aria-pressed="' + (DFS.pos === p) + '">' + p + "</button>"; }).join("") + "</span>" +
      '<span class="seg" role="group" aria-label="対象">' + '<button type="button" data-qual="1" aria-pressed="' + DFS.qual + '">評価対象のみ</button><button type="button" data-qual="0" aria-pressed="' + !DFS.qual + '">全選手</button></span>' +
      '<span class="muted small">' + rows.length + "人を表示</span></div>" +
      table("df", cols, rows, { sort: { k: "score", dir: -1 } }) +
      '<div class="grid two section">' +
      '<div class="card"><h3>スコアの作り方</h3><p class="small">① 各指標を評価対象内で標準化（DRtg・DFG%・DIFF% は低いほど良いので符号を反転）→ ② 6つの柱（総合インパクト／被シュート抑制／チーム失点／ボール奪取／リム保護／守備リバウンド）にまとめる → ③ 柱ごとの重みで合計し、偏差値に変換。DBPM は STL・BLK・DRB を含むため、個別の柱は軽めにしています。</p></div>' +
      '<div class="card"><h3>指標と出典</h3><p class="small">DBPM・DWS・BLK%・STL%・DRB%：Basketball-Reference（Advanced）／DRtg：Basketball-Reference（Per 100）／DFG%・DIFF%：NBA.com 公式トラッキング（被FG率と相手平均との差。試投数が少ない選手ほど誤差が大きい）。2025-26 レギュラーシーズン。空欄は元データに数値がないもので、計算では平均扱いにしています。</p></div></div>';
    return { title: "ディフェンス総合ランキング 2025-26", nav: "defense", html: html };
  }

  // ---------- 選手 ----------
  function pagePlayer(id) {
    var p = PLAYERS[id];
    if (!p) return notFound();
    var html = '<div class="eyebrow">Player</div><div class="ptitle"><h1>' + esc(p.name) + "</h1>" + (p.draft ? gradeBadge(p.draft.g) : "") + "</div>";
    if (p.draft) {
      var d = p.draft;
      var aw = honors(d, true);
      html += '<div class="card section"><h2>ドラフト評価</h2><dl class="facts">' +
        fact("指名", '<a href="#draft~' + d.y + '">' + d.y + "年</a> " + d.rd + "巡目 " + d.p + "位") +
        fact("初年度所属", d.t && d.t !== "-" ? esc(d.t) : "NBA出場なし") +
        fact("評価", gradeBadge(d.g) + " " + d.s + "点") +
        fact("期待値（" + d.p + "位）", f2(d.fit)) +
        fact("期待値との差", dv(d.df)) +
        fact("総出場分数", comma(d.min)) +
        fact("平均出場分数", f1(d.mpg)) +
        "</dl>" + (aw ? '<div style="margin-top:12px">' + aw + "</div>" : "") +
        (d.y >= RECENT_FROM ? '<div class="note">キャリアが短いため、評価は今後変わる可能性があります。</div>' : "") + "</div>";
      var same = DRAFT.filter(function (x) { return x.y === d.y && Math.abs(x.p - d.p) <= 3 && x.p !== d.p; });
      html += '<div class="section"><h3>前後の指名（' + d.y + "年）</h3>" + table("near", draftCols(false), same.concat([d]).sort(function (a, b) { return a.p - b.p; }), { mark: function (x) { return x === d; } }) + "</div>";
    } else {
      html += '<p class="muted">' + YEARS[0] + "〜" + YEARS[YEARS.length - 1] + "年のドラフト評価データには含まれていません（ドラフト外、またはそれ以前の指名）。</p>";
    }
    if (p.def) {
      var f = p.def;
      html += '<div class="card section"><h2>2025-26 ディフェンス</h2><dl class="facts">' +
        fact("チーム / POS", esc(f.team) + " / " + esc(f.pos)) +
        fact("総合スコア（バランス）", BAL[f.i].toFixed(1)) +
        fact("順位", f.qual ? BAL_RANK[f.i] + "位 / " + QUAL_N + "人" : '<span class="dim">対象外</span>') +
        fact("G / MPG", f.g + " / " + f1(f.mpg)) +
        fact("DBPM", f1(f.dbpm)) + fact("DWS", f1(f.dws)) +
        fact("DRtg", f.drtg == null ? "–" : f.drtg) + fact("DFG% / DIFF%", f1(f.dfg) + " / " + sgn(f.diff, 1)) +
        fact("BLK% / STL%", f1(f.blkpct) + " / " + f1(f.stlpct)) +
        "</dl>" + (f.honors ? '<div style="margin-top:12px"><span class="award big">' + esc(f.honors) + "</span></div>" : "") +
        (!f.qual ? '<p class="small muted" style="margin-top:8px">' + QUAL_G + "試合・" + QUAL_MP + "分に届いていないため、順位の対象外です。</p>" : "") + "</div>";
    }
    return { title: p.name, nav: "", html: html };
  }
  function fact(k, v) { return "<div><dt>" + k + "</dt><dd>" + v + "</dd></div>"; }

  function notFound() { return { title: "ページが見つかりません", nav: "", html: '<h1>ページが見つかりません</h1><p><a href="#">トップへ戻る</a></p>' }; }

  // ---------- ルーティング ----------
  function route() {
    var h = decodeURIComponent(location.hash.replace(/^#/, ""));
    var a = h.split("~");
    switch (a[0]) {
      case "": return pageHome();
      case "draft": return pageDraft(a[1]);
      case "steals": return pageSteals();
      case "curve": return pageCurve();
      case "teams": return pageTeams();
      case "defense": return pageDefense();
      case "p": return pagePlayer(a.slice(1).join("~"));
      default: return notFound();
    }
  }
  var lastHash = null;
  function render(keepScroll) {
    var page = route();
    var y = window.scrollY;
    view.innerHTML = page.html;
    document.title = page.title === "オタバス NBA データ室" ? page.title : page.title + " | オタバス";
    document.querySelectorAll("[data-nav]").forEach(function (a) { a.classList.toggle("active", a.getAttribute("data-nav") === page.nav); });
    if (page.after) page.after();
    if (keepScroll) window.scrollTo(0, y);
    else if (lastHash !== location.hash) window.scrollTo(0, 0);
    lastHash = location.hash;
  }

  // ---------- 操作 ----------
  document.addEventListener("click", function (e) {
    var t = e.target;
    var th = t.closest("th[data-k]");
    if (th) { onSort(th); return; }
    var b;
    if ((b = t.closest("[data-round]"))) { window.__round = b.getAttribute("data-round"); render(true); return; }
    if ((b = t.closest("[data-sround]"))) { window.__steals.round = b.getAttribute("data-sround"); render(true); return; }
    if ((b = t.closest("[data-preset]"))) { DFS.preset = b.getAttribute("data-preset"); DFS.w = Object.assign({}, PRESETS[DFS.preset].w); render(true); return; }
    if ((b = t.closest("[data-adj]"))) { DFS.posadj = b.getAttribute("data-adj") === "1"; render(true); return; }
    if ((b = t.closest("[data-pos]"))) { DFS.pos = b.getAttribute("data-pos"); render(true); return; }
    if ((b = t.closest("[data-qual]"))) { DFS.qual = b.getAttribute("data-qual") === "1"; render(true); return; }
    if (!t.closest(".search")) document.getElementById("results").hidden = true;
  });
  document.addEventListener("keydown", function (e) {
    var th = e.target.closest && e.target.closest("th[data-k]");
    if (th && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onSort(th); }
  });
  var sliderTimer = null;
  document.addEventListener("input", function (e) {
    var t = e.target;
    if (t.hasAttribute("data-pillar")) {
      DFS.w[t.getAttribute("data-pillar")] = +t.value; DFS.preset = "";
      clearTimeout(sliderTimer);
      sliderTimer = setTimeout(function () { refocus(t.id, function () { render(true); }); }, 60);
    } else if (t.id === "df-q") {
      DFS.q = t.value; refocus("df-q", function () { render(true); });
    }
  });
  // 再描画しても入力中のコントロールからフォーカスが外れないようにする
  function refocus(id, fn) {
    var el = document.getElementById(id), pos = el && el.selectionStart;
    fn();
    var n = document.getElementById(id);
    if (n) { n.focus(); try { if (pos != null) n.setSelectionRange(pos, pos); } catch (err) { /* range 入力は非対応 */ } }
  }
  document.addEventListener("change", function (e) {
    var t = e.target, s = window.__steals, tm = window.__teams;
    if (t.id === "s-from") { s.from = +t.value; if (s.to < s.from) s.to = s.from; render(true); }
    else if (t.id === "s-to") { s.to = +t.value; if (s.from > s.to) s.from = s.to; render(true); }
    else if (t.id === "s-recent") { s.recent = t.checked; render(true); }
    else if (t.id === "t-merge") { tm.merge = t.checked; render(true); }
    else if (t.id === "t-recent") { tm.recent = t.checked; render(true); }
  });

  // ---------- 検索 ----------
  function norm(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  var INDEX = Object.keys(PLAYERS).map(function (id) {
    var p = PLAYERS[id];
    var meta = p.draft ? p.draft.y + " #" + p.draft.p : "";
    if (p.def) meta += (meta ? " · " : "") + p.def.team;
    return { id: id, name: p.name, k: norm(p.name), meta: meta };
  });
  var q = document.getElementById("q"), results = document.getElementById("results"), sel = -1;
  function showResults() {
    var s = norm(q.value.trim()); sel = -1;
    if (!s) { results.hidden = true; results.innerHTML = ""; return; }
    var hits = INDEX.filter(function (x) { return x.k.indexOf(s) >= 0; });
    hits.sort(function (a, b) {
      var sa = (" " + a.k).indexOf(" " + s) >= 0 ? 0 : 1, sb = (" " + b.k).indexOf(" " + s) >= 0 ? 0 : 1;
      return sa - sb || a.k.localeCompare(b.k);
    });
    results.innerHTML = hits.length ? hits.slice(0, 20).map(function (x) {
      return '<li><a href="#p~' + esc(x.id) + '"><span>' + esc(x.name) + '</span><span class="meta">' + esc(x.meta) + "</span></a></li>";
    }).join("") : '<li><a><span class="meta">見つかりませんでした</span></a></li>';
    results.hidden = false;
  }
  q.addEventListener("input", showResults);
  q.addEventListener("keydown", function (e) {
    var items = results.querySelectorAll("li");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); if (!items.length) return;
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items.forEach(function (li, i) { li.classList.toggle("sel", i === sel); });
    } else if (e.key === "Enter") {
      var a = items[sel >= 0 ? sel : 0]; a = a && a.querySelector("a[href]");
      if (a) { location.hash = a.getAttribute("href"); results.hidden = true; q.value = ""; q.blur(); }
    } else if (e.key === "Escape") { results.hidden = true; }
  });
  results.addEventListener("click", function (e) { if (e.target.closest("a[href]")) { results.hidden = true; q.value = ""; } });

  document.getElementById("foot").innerHTML =
    "オタバス NBA データ室 · ドラフト評価はオタバス独自の採点（" + YEARS[0] + "〜" + YEARS[YEARS.length - 1] + "年）／DF指標は Basketball-Reference・NBA.com の 2025-26 データより · 更新 " + esc(RAW.built);

  window.addEventListener("hashchange", function () { render(false); });
  render(false);
})();
