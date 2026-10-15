#!/usr/bin/env python3
"""NBA 選手スタッツの静的サイトを生成する。

data/ の CSV と config.toml を読み、dist/ に HTML 一式を書き出す。
標準ライブラリのみで動作（Python 3.11 以上）。

    python build.py                 # data/ → dist/
    python build.py --data DIR --out DIR --config FILE
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import shutil
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]+")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def slug(value: str) -> str:
    """ファイル名に使える形へ変換（英数字・_ . - 以外は - に置換）。"""
    return SAFE_ID.sub("-", value.strip()).strip("-") or "_"


def to_num(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt(value: object, kind: str) -> str:
    """セルの表示文字列を返す。数値に変換できなければ元の文字列のまま。"""
    if value is None:
        return ""
    if isinstance(value, float):
        num = value
    else:
        raw = str(value).strip()
        if kind == "text" or raw == "":
            return raw
        num = to_num(raw)
        if num is None:
            return raw
    if kind == "int":
        return str(int(round(num)))
    if kind == "f1":
        return f"{num:.1f}"
    if kind == "f3":
        return f"{num:.3f}"
    if kind == "pct":
        text = f"{num:.3f}"
        return text[1:] if text.startswith("0.") else text.replace("-0.", "-.")
    return str(value)


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    # utf-8-sig: Excel で保存した BOM 付き CSV にも対応
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [
            {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(f)
        ]


@dataclass
class Column:
    key: str
    label: str
    fmt: str = "text"
    agg: str = ""


@dataclass
class Table:
    id: str
    title: str
    file: str
    columns: list[Column]
    weight: str = ""
    rows: list[dict[str, str]] = field(default_factory=list)
    career_rows: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class Site:
    config: dict
    players: dict[str, dict[str, str]]
    teams: dict[str, dict[str, str]]
    tables: list[Table]
    total_codes: set[str]

    @property
    def seasons(self) -> list[str]:
        found = {r["season"] for t in self.tables for r in t.rows}
        return sorted(found, reverse=True)

    def team_name(self, code: str) -> str:
        return self.teams.get(code, {}).get("name") or code

    def is_total(self, team: str) -> bool:
        return team.upper() in self.total_codes

    def player_name(self, pid: str) -> str:
        return self.players.get(pid, {}).get("name") or pid


def load_site(data_dir: Path, config_path: Path) -> Site:
    with config_path.open("rb") as f:
        config = tomllib.load(f)

    players: dict[str, dict[str, str]] = {}
    players_csv = data_dir / "players.csv"
    if players_csv.exists():
        for row in read_csv(players_csv):
            if row.get("player_id"):
                players[row["player_id"]] = row

    teams: dict[str, dict[str, str]] = {}
    teams_csv = data_dir / "teams.csv"
    if teams_csv.exists():
        for row in read_csv(teams_csv):
            if row.get("team"):
                teams[row["team"]] = row

    tables: list[Table] = []
    for spec in config.get("tables", []):
        path = data_dir / spec["file"]
        if not path.exists():
            print(f"[skip] {path} が見つからないため「{spec['title']}」表を省略", file=sys.stderr)
            continue
        table = Table(
            id=spec["id"],
            title=spec["title"],
            file=spec["file"],
            weight=spec.get("weight", ""),
            columns=[Column(**c) for c in spec["columns"]],
        )
        for n, row in enumerate(read_csv(path), start=2):
            missing = [k for k in ("player_id", "season", "team") if not row.get(k)]
            if missing and row.get("season", "").lower() != "career":
                print(f"[warn] {path.name}:{n} 必須列が空: {', '.join(missing)}", file=sys.stderr)
                continue
            if row["season"].lower() == "career":
                table.career_rows[row["player_id"]] = row
            else:
                table.rows.append(row)
        tables.append(table)

    # stats にだけ出てくる選手も名前なしで扱えるようにする
    for t in tables:
        for r in t.rows:
            pid = r["player_id"]
            if pid not in players:
                players[pid] = {"player_id": pid, "name": r.get("player") or pid}

    total_codes = {c.upper() for c in config.get("site", {}).get("total_team_codes", ["TOT"])}
    return Site(config, players, teams, tables, total_codes)


# ---------------------------------------------------------------------------
# 集計
# ---------------------------------------------------------------------------


def season_sort_key(site: Site, row: dict[str, str]) -> tuple:
    # 同シーズン内では合計行（TOT）を先頭、その後チーム別
    return (row["season"], 0 if site.is_total(row["team"]) else 1, row["team"])


def counted_rows(site: Site, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """二重計上を避けるため、移籍シーズンは合計行（TOT）だけを残す。"""
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        groups[(r["player_id"], r["season"])].append(r)
    out = []
    for group in groups.values():
        totals = [r for r in group if site.is_total(r["team"])]
        out.extend(totals or group)
    return out


def aggregate(table: Table, rows: list[dict[str, str]]) -> dict[str, float | None]:
    def wsum(key: str, weight_key: str = "") -> tuple[float, float]:
        """(Σ value*weight, Σ weight) を返す。値が空の行は除外。"""
        total = wt = 0.0
        for r in rows:
            v = to_num(r.get(key))
            w = to_num(r.get(weight_key)) if weight_key else 1.0
            if v is None or w is None:
                continue
            total += v * w
            wt += w
        return total, wt

    result: dict[str, float | None] = {}
    for col in table.columns:
        agg = col.agg
        value: float | None = None
        if agg == "sum":
            total, n = wsum(col.key)
            value = total if n else None
        elif agg == "max":
            nums = [x for x in (to_num(r.get(col.key)) for r in rows) if x is not None]
            value = max(nums) if nums else None
        elif agg.startswith("wavg"):
            weight_key = agg.partition(":")[2] or table.weight
            total, wt = wsum(col.key, weight_key)
            value = total / wt if wt else None
        elif agg.startswith("ratio:"):
            num_key, _, den_key = agg[6:].partition("/")
            num, _ = wsum(num_key, table.weight)
            den, _ = wsum(den_key, table.weight)
            value = num / den if den else None
        result[col.key] = value
    return result


def career_row(site: Site, table: Table, pid: str, rows: list[dict[str, str]]):
    """通算行。CSV に Career 行があればそれを優先し、なければ計算する。"""
    if pid in table.career_rows:
        return table.career_rows[pid]
    if not any(c.agg for c in table.columns):
        return None
    return aggregate(table, counted_rows(site, rows))


# ---------------------------------------------------------------------------
# HTML 部品
# ---------------------------------------------------------------------------


class Pages:
    def __init__(self, site: Site, out: Path):
        self.site = site
        self.out = out
        self.built = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.count = 0

    # パスはすべて相対リンク。サブディレクトリ配置や file:// でも動く。
    def write(self, rel: str, title: str, body: str, active: str = "") -> None:
        depth = rel.count("/")
        root = "../" * depth
        cfg = self.site.config.get("site", {})
        site_title = cfg.get("title", "NBA Stats")
        robots = '<meta name="robots" content="noindex, nofollow, noarchive">' if cfg.get("noindex", True) else ""
        nav = "".join(
            f'<a href="{root}{href}"{" class=\"active\"" if key == active else ""}>{label}</a>'
            for key, href, label in (
                ("players", "players/index.html", "Players"),
                ("seasons", "seasons/index.html", "Seasons"),
                ("teams", "teams/index.html", "Teams"),
            )
        )
        doc = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{robots}
<meta name="referrer" content="no-referrer">
<title>{esc(title)} | {esc(site_title)}</title>
<link rel="stylesheet" href="{root}assets/style.css">
</head>
<body>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{root}index.html">{esc(site_title)}</a>
    <nav class="nav">{nav}</nav>
    <div class="search">
      <input id="search" type="search" placeholder="選手名で検索…" autocomplete="off" aria-label="選手検索">
      <ul id="search-results" class="search-results" hidden></ul>
    </div>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-footer"><div class="wrap">最終更新 {esc(self.built)}</div></footer>
<script>window.SITE_ROOT = {json.dumps(root)};</script>
<script src="{root}assets/search-index.js"></script>
<script src="{root}assets/app.js"></script>
</body>
</html>
"""
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(doc, encoding="utf-8")
        self.count += 1

    # --- リンク ---------------------------------------------------------

    def player_link(self, pid: str, root: str) -> str:
        return f'<a href="{root}players/{slug(pid)}.html">{esc(self.site.player_name(pid))}</a>'

    def team_link(self, team: str, root: str, season: str = "") -> str:
        if self.site.is_total(team):
            return esc(team)
        href = f"{root}teams/{slug(team)}/{slug(season)}.html" if season else f"{root}teams/{slug(team)}.html"
        return f'<a href="{href}" title="{esc(self.site.team_name(team))}">{esc(team)}</a>'

    def season_link(self, season: str, root: str) -> str:
        return f'<a href="{root}seasons/{slug(season)}.html">{esc(season)}</a>'

    # --- 表 ---------------------------------------------------------------

    def stat_table(
        self,
        table: Table,
        rows: list[dict[str, str]],
        root: str,
        lead: list[str],
        footer: dict | None = None,
        rank: bool = False,
    ) -> str:
        """lead: 先頭に置く固定列（"season" / "player" / "team"）。"""
        labels = {"season": "Season", "player": "Player", "team": "Team"}
        cols = [c for c in table.columns if any(r.get(c.key, "") != "" for r in rows) or (footer and footer.get(c.key) not in (None, ""))]
        head = ('<th class="num" data-sort="num">Rk</th>' if rank else "") + "".join(
            f'<th class="lead{" sticky" if i == 0 else ""}" data-sort="text">{labels[k]}</th>' for i, k in enumerate(lead)
        ) + "".join(
            f'<th class="{"text" if c.fmt == "text" else "num"}" data-sort="{"text" if c.fmt == "text" else "num"}">{esc(c.label)}</th>'
            for c in cols
        )

        # 移籍シーズンのチーム別行（合計行 TOT が別にある行）に印を付ける
        def sticky(k: str) -> str:
            return " sticky" if k == lead[0] else ""

        has_total = {(r["player_id"], r["season"]) for r in rows if self.site.is_total(r["team"])}
        body_rows = []
        for i, r in enumerate(rows, start=1):
            cells = [f'<td class="num">{i}</td>'] if rank else []
            for k in lead:
                if k == "season":
                    cells.append(f'<th scope="row" class="lead{sticky(k)}">{self.season_link(r["season"], root)}</th>')
                elif k == "player":
                    cells.append(f'<td class="lead{sticky(k)}" data-v="{esc(self.site.player_name(r["player_id"]))}">{self.player_link(r["player_id"], root)}</td>')
                elif k == "team":
                    cells.append(f'<td class="lead{sticky(k)}">{self.team_link(r["team"], root, r["season"])}</td>')
            for c in cols:
                raw = r.get(c.key, "")
                num = to_num(raw)
                data_v = f' data-v="{num}"' if num is not None and c.fmt != "text" else ""
                cells.append(f'<td class="{"text" if c.fmt == "text" else "num"}"{data_v}>{esc(fmt(raw, c.fmt))}</td>')
            partial = not self.site.is_total(r["team"]) and (r["player_id"], r["season"]) in has_total
            cls = ' class="partial"' if partial else ""
            g = to_num(r.get("g"))
            data_g = f' data-g="{g}"' if g is not None else ""
            body_rows.append(f"<tr{cls}{data_g}>{''.join(cells)}</tr>")

        foot = ""
        if footer:
            span = len(lead) + (1 if rank else 0)
            seasons = len({r["season"] for r in rows})
            fcells = [f'<th class="lead sticky" colspan="{span}">Career <span class="muted">({seasons} seasons)</span></th>']
            for c in cols:
                v = footer.get(c.key)
                fcells.append(f'<td class="{"text" if c.fmt == "text" else "num"}">{esc(fmt(v, c.fmt))}</td>')
            foot = f"<tfoot><tr>{''.join(fcells)}</tr></tfoot>"

        return (
            f'<div class="table-scroll"><table class="stats sortable" id="t-{esc(table.id)}">'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody>{foot}</table></div>"
        )

    def tabs(self, sections: list[tuple[str, str, str]]) -> str:
        """sections: (id, title, html)。表が複数ならタブ切り替え。"""
        if not sections:
            return '<p class="muted">データがありません。</p>'
        buttons = "".join(
            f'<button type="button" class="tab{" active" if i == 0 else ""}" data-tab="{esc(sid)}">{esc(title)}</button>'
            for i, (sid, title, _) in enumerate(sections)
        )
        panels = "".join(
            f'<section class="panel" data-panel="{esc(sid)}"{"" if i == 0 else " hidden"}><h2>{esc(title)}</h2>{content}</section>'
            for i, (sid, title, content) in enumerate(sections)
        )
        return f'<div class="tabs" role="tablist">{buttons}</div>{panels}'


# ---------------------------------------------------------------------------
# 各ページ
# ---------------------------------------------------------------------------


def build_player_pages(p: Pages) -> None:
    site = p.site
    root = "../"
    by_player: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for t in site.tables:
        for r in t.rows:
            by_player[r["player_id"]][t.id].append(r)

    bio_spec = site.config.get("bio", [])
    for pid, info in site.players.items():
        name = info.get("name") or pid
        bio_items = "".join(
            f"<div><dt>{esc(b['label'])}</dt><dd>{esc(info[b['key']])}</dd></div>"
            for b in bio_spec
            if info.get(b["key"])
        )
        sections = []
        all_rows = []
        for t in site.tables:
            rows = sorted(by_player[pid].get(t.id, []), key=lambda r: season_sort_key(site, r))
            if not rows:
                continue
            all_rows.extend(rows)
            sections.append((t.id, t.title, p.stat_table(t, rows, root, ["season", "team"], footer=career_row(site, t, pid, rows))))

        seasons = sorted({r["season"] for r in all_rows})
        span = f"{seasons[0]} – {seasons[-1]}" if seasons else ""
        teams = []
        for r in sorted(all_rows, key=lambda r: r["season"]):
            if not site.is_total(r["team"]) and r["team"] not in teams:
                teams.append(r["team"])
        team_links = " · ".join(p.team_link(t, root) for t in teams)

        body = f"""
<div class="breadcrumbs"><a href="{root}players/index.html">Players</a> › {esc(name)}</div>
<section class="profile">
  <h1>{esc(name)}</h1>
  <p class="muted">{esc(span)}{f' · {len(seasons)} seasons' if seasons else ''}</p>
  {f'<dl class="bio">{bio_items}</dl>' if bio_items else ''}
  {f'<p class="teams">Teams: {team_links}</p>' if team_links else ''}
</section>
{p.tabs(sections)}
"""
        p.write(f"players/{slug(pid)}.html", name, body, "players")


def last_name_key(info: dict[str, str]) -> str:
    if info.get("last_name"):
        return info["last_name"]
    parts = (info.get("name") or info.get("player_id", "")).split()
    # "Jr." "III" などの接尾辞は飛ばす
    while len(parts) > 1 and parts[-1].rstrip(".").lower() in {"jr", "sr", "ii", "iii", "iv", "v"}:
        parts.pop()
    return parts[-1] if parts else ""


def build_players_index(p: Pages) -> None:
    site = p.site
    root = "../"
    span: dict[str, list[str]] = defaultdict(list)
    for t in site.tables:
        for r in t.rows:
            span[r["player_id"]].append(r["season"])

    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pid, info in site.players.items():
        key = last_name_key(info)
        letter = key[:1].upper() if key[:1].isalpha() else "#"
        groups[letter].append((key.lower() + " " + (info.get("name") or "").lower(), pid))

    letters = sorted(groups)
    jump = " ".join(f'<a href="#letter-{l}">{l}</a>' for l in letters)
    blocks = []
    for l in letters:
        items = []
        for _, pid in sorted(groups[l]):
            ss = sorted(span.get(pid, []))
            years = f' <span class="muted">{esc(ss[0])} – {esc(ss[-1])}</span>' if ss else ""
            items.append(f"<li>{p.player_link(pid, root)}{years}</li>")
        blocks.append(f'<section id="letter-{l}"><h2>{l}</h2><ul class="cols">{"".join(items)}</ul></section>')

    body = f"""
<h1>Players <span class="muted">({len(site.players)})</span></h1>
<p class="jump">{jump}</p>
{''.join(blocks)}
"""
    p.write("players/index.html", "Players", body, "players")


def build_season_pages(p: Pages) -> None:
    site = p.site
    root = "../"
    seasons = site.seasons
    for i, season in enumerate(seasons):
        sections = []
        for t in site.tables:
            rows = [r for r in t.rows if r["season"] == season]
            if not rows:
                continue
            rows.sort(key=lambda r: (site.player_name(r["player_id"]).lower(), 0 if site.is_total(r["team"]) else 1, r["team"]))
            sections.append((t.id, t.title, p.stat_table(t, rows, root, ["player", "team"], rank=True)))

        prev_link = p.season_link(seasons[i + 1], root) if i + 1 < len(seasons) else ""
        next_link = p.season_link(seasons[i - 1], root) if i > 0 else ""
        body = f"""
<div class="breadcrumbs"><a href="{root}seasons/index.html">Seasons</a> › {esc(season)}</div>
<h1>{esc(season)} Player Stats</h1>
<p class="pager">{'‹ ' + prev_link if prev_link else ''} {next_link + ' ›' if next_link else ''}</p>
<div class="filters">
  <label>最低試合数 <input type="number" class="min-games" min="0" value="0" inputmode="numeric"></label>
  <label><input type="checkbox" class="hide-partial"> 移籍選手はチーム別の行を隠す（合計行のみ）</label>
</div>
{p.tabs(sections)}
"""
        p.write(f"seasons/{slug(season)}.html", f"{season} Player Stats", body, "seasons")

    items = "".join(f"<li>{p.season_link(s, root)}</li>" for s in seasons)
    p.write("seasons/index.html", "Seasons", f'<h1>Seasons</h1><ul class="cols">{items}</ul>', "seasons")


def build_team_pages(p: Pages) -> None:
    site = p.site
    by_team: dict[str, dict[str, dict[str, list]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for t in site.tables:
        for r in t.rows:
            if not site.is_total(r["team"]):
                by_team[r["team"]][r["season"]][t.id].append(r)

    # チームシーズンページ: teams/{TEAM}/{SEASON}.html
    for team, seasons in by_team.items():
        name = site.team_name(team)
        for season, per_table in seasons.items():
            root = "../../"
            sections = []
            for t in site.tables:
                rows = per_table.get(t.id, [])
                if not rows:
                    continue
                rows = sorted(rows, key=lambda r: -(to_num(r.get("mp")) or 0))
                sections.append((t.id, t.title, p.stat_table(t, rows, root, ["player"])))
            body = f"""
<div class="breadcrumbs"><a href="{root}teams/index.html">Teams</a> › <a href="{root}teams/{slug(team)}.html">{esc(name)}</a> › {esc(season)}</div>
<h1>{esc(season)} {esc(name)}</h1>
<p class="muted">シーズン全体: {p.season_link(season, root)}</p>
{p.tabs(sections)}
"""
            p.write(f"teams/{slug(team)}/{slug(season)}.html", f"{season} {name}", body, "teams")

        # チームトップ: シーズン一覧
        root = "../"
        rows = []
        for season in sorted(seasons, reverse=True):
            players = {r["player_id"] for rs in seasons[season].values() for r in rs}
            rows.append(
                f'<tr><th scope="row" class="lead sticky"><a href="{slug(team)}/{slug(season)}.html">{esc(season)}</a></th>'
                f'<td class="num" data-v="{len(players)}">{len(players)}</td></tr>'
            )
        info = site.teams.get(team, {})
        meta = " · ".join(esc(info[k]) for k in ("conference", "division") if info.get(k))
        body = f"""
<div class="breadcrumbs"><a href="{root}teams/index.html">Teams</a> › {esc(name)}</div>
<h1>{esc(name)} <span class="muted">({esc(team)})</span></h1>
{f'<p class="muted">{meta}</p>' if meta else ''}
<div class="table-scroll"><table class="stats sortable narrow">
<thead><tr><th class="lead sticky" data-sort="text">Season</th><th class="num" data-sort="num">Players</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
"""
        p.write(f"teams/{slug(team)}.html", name, body, "teams")

    # 一覧（conference 列があればグループ化）
    root = "../"
    codes = sorted(set(by_team) | set(site.teams))
    groups: dict[str, list[str]] = defaultdict(list)
    for code in codes:
        groups[site.teams.get(code, {}).get("conference", "")].append(code)
    blocks = []
    for conf in sorted(groups):
        items = []
        for code in sorted(groups[conf], key=lambda c: site.team_name(c)):
            label = f"{esc(site.team_name(code))} <span class=\"muted\">{esc(code)}</span>"
            items.append(f'<li><a href="{slug(code)}.html">{label}</a></li>' if code in by_team else f"<li>{label}</li>")
        heading = f"<h2>{esc(conf)}</h2>" if conf else ""
        blocks.append(f'<section>{heading}<ul class="cols">{"".join(items)}</ul></section>')
    p.write("teams/index.html", "Teams", f"<h1>Teams</h1>{''.join(blocks)}", "teams")


def build_home(p: Pages) -> None:
    site = p.site
    cfg = site.config.get("home", {})
    root = ""
    seasons = site.seasons
    title = site.config.get("site", {}).get("title", "NBA Stats")
    subtitle = site.config.get("site", {}).get("subtitle", "")

    leaders_html = ""
    table = next((t for t in site.tables if t.id == cfg.get("leaders_table", "per_game")), None)
    if table and seasons:
        latest = seasons[0]
        rows = counted_rows(site, [r for r in table.rows if r["season"] == latest])
        min_g = cfg.get("leaders_min_games", 0)
        rows = [r for r in rows if (to_num(r.get("g")) or 0) >= min_g] if min_g else rows
        cols = {c.key: c for c in table.columns}
        cards = []
        for key in cfg.get("leaders", []):
            if key not in cols:
                continue
            ranked = sorted((r for r in rows if to_num(r.get(key)) is not None), key=lambda r: -to_num(r[key]))
            ranked = ranked[: cfg.get("leaders_count", 5)]
            if not ranked:
                continue
            lis = "".join(
                f'<li><span class="who">{p.player_link(r["player_id"], root)} <span class="muted">{esc(r["team"])}</span></span>'
                f'<span class="val">{esc(fmt(r[key], cols[key].fmt))}</span></li>'
                for r in ranked
            )
            cards.append(f'<div class="card"><h3>{esc(cols[key].label)}</h3><ol>{lis}</ol></div>')
        if cards:
            note = f"（{min_g}試合以上）" if min_g else ""
            leaders_html = f"""
<section>
  <h2>{esc(latest)} Leaders <span class="muted small">{esc(table.title)}{esc(note)}</span></h2>
  <div class="cards">{''.join(cards)}</div>
  <p><a href="seasons/{slug(latest)}.html">{esc(latest)} の全選手スタッツ →</a></p>
</section>"""

    season_list = "".join(f"<li>{p.season_link(s, root)}</li>" for s in seasons[:12])
    body = f"""
<section class="hero">
  <h1>{esc(title)}</h1>
  {f'<p class="muted">{esc(subtitle)}</p>' if subtitle else ''}
  <p class="stats-count">{len(site.players)} players · {len(seasons)} seasons · {len({r['team'] for t in site.tables for r in t.rows if not site.is_total(r['team'])})} teams</p>
</section>
{leaders_html}
<section>
  <h2>Seasons</h2>
  <ul class="cols">{season_list}</ul>
  <p><a href="seasons/index.html">すべてのシーズン →</a></p>
</section>
"""
    p.write("index.html", "Home", body)


def build_search_index(site: Site, out: Path) -> None:
    span: dict[str, list[str]] = defaultdict(list)
    for t in site.tables:
        for r in t.rows:
            span[r["player_id"]].append(r["season"])
    items = []
    for pid, info in site.players.items():
        ss = sorted(span.get(pid, []))
        items.append({
            "n": info.get("name") or pid,
            "u": f"players/{slug(pid)}.html",
            "y": f"{ss[0]}–{ss[-1]}" if ss else "",
        })
    items.sort(key=lambda x: x["n"].lower())
    # fetch ではなく <script> で読み込む（file:// でも検索が動くように）
    text = "window.PLAYERS = " + json.dumps(items, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (out / "assets" / "search-index.js").write_text(text, encoding="utf-8")


def build(data_dir: Path, out: Path, config_path: Path) -> Pages:
    site = load_site(data_dir, config_path)
    marker = out / ".nba-stats-build"
    if out.exists() and any(out.iterdir()):
        # このスクリプトが作ったディレクトリ以外は消さない
        if not marker.exists():
            raise SystemExit(f"{out} は空でなく、このツールの出力先ではありません。別の --out を指定してください。")
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    marker.write_text("generated by nba-stats/build.py\n", encoding="utf-8")
    for f in (HERE / "static").iterdir():
        shutil.copy2(f, out / "assets" / f.name)

    if site.config.get("site", {}).get("noindex", True):
        (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    p = Pages(site, out)
    build_search_index(site, out)
    build_home(p)
    build_players_index(p)
    build_player_pages(p)
    build_season_pages(p)
    build_team_pages(p)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NBA スタッツの静的サイトを生成")
    ap.add_argument("--data", type=Path, default=None, help="CSV のあるディレクトリ（既定: data/、無ければ sample_data/）")
    ap.add_argument("--out", type=Path, default=HERE / "dist", help="出力先")
    ap.add_argument("--config", type=Path, default=HERE / "config.toml")
    args = ap.parse_args(argv)
    if args.data is None:
        args.data = HERE / "data"
        if not args.data.exists():
            args.data = HERE / "sample_data"
            print("[info] data/ が無いので sample_data/（架空のサンプル）でビルドします", file=sys.stderr)
    p = build(args.data, args.out, args.config)
    print(f"{p.count} ページを {args.out} に出力しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
