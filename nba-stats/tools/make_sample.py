#!/usr/bin/env python3
"""動作確認用のサンプル CSV を生成する（選手・数値はすべて架空）。

    python tools/make_sample.py            # → sample_data/

実データの CSV を作るときの列名・形式の見本にもなる。
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample_data"

TEAMS = [
    # team, name, conference, division
    ("ATL", "Atlanta Hawks", "Eastern", "Southeast"),
    ("BOS", "Boston Celtics", "Eastern", "Atlantic"),
    ("BRK", "Brooklyn Nets", "Eastern", "Atlantic"),
    ("CHO", "Charlotte Hornets", "Eastern", "Southeast"),
    ("CHI", "Chicago Bulls", "Eastern", "Central"),
    ("CLE", "Cleveland Cavaliers", "Eastern", "Central"),
    ("DAL", "Dallas Mavericks", "Western", "Southwest"),
    ("DEN", "Denver Nuggets", "Western", "Northwest"),
    ("DET", "Detroit Pistons", "Eastern", "Central"),
    ("GSW", "Golden State Warriors", "Western", "Pacific"),
    ("HOU", "Houston Rockets", "Western", "Southwest"),
    ("IND", "Indiana Pacers", "Eastern", "Central"),
    ("LAC", "Los Angeles Clippers", "Western", "Pacific"),
    ("LAL", "Los Angeles Lakers", "Western", "Pacific"),
    ("MEM", "Memphis Grizzlies", "Western", "Southwest"),
    ("MIA", "Miami Heat", "Eastern", "Southeast"),
    ("MIL", "Milwaukee Bucks", "Eastern", "Central"),
    ("MIN", "Minnesota Timberwolves", "Western", "Northwest"),
    ("NOP", "New Orleans Pelicans", "Western", "Southwest"),
    ("NYK", "New York Knicks", "Eastern", "Atlantic"),
    ("OKC", "Oklahoma City Thunder", "Western", "Northwest"),
    ("ORL", "Orlando Magic", "Eastern", "Southeast"),
    ("PHI", "Philadelphia 76ers", "Eastern", "Atlantic"),
    ("PHO", "Phoenix Suns", "Western", "Pacific"),
    ("POR", "Portland Trail Blazers", "Western", "Northwest"),
    ("SAC", "Sacramento Kings", "Western", "Pacific"),
    ("SAS", "San Antonio Spurs", "Western", "Southwest"),
    ("TOR", "Toronto Raptors", "Eastern", "Atlantic"),
    ("UTA", "Utah Jazz", "Western", "Northwest"),
    ("WAS", "Washington Wizards", "Eastern", "Southeast"),
]

FIRST = ["Marcus", "Devin", "Tyrese", "Jalen", "Luka", "Andre", "Kevin", "Darius", "Isaiah", "Malik",
         "Jordan", "Cameron", "Trey", "Aaron", "Miles", "Noah", "Elijah", "Xavier", "Caleb", "Damian",
         "Ryo", "Kenta", "Théo", "Nikola", "Mateo"]
LAST = ["Sample", "Placeholder", "Example", "Dummy", "Testwell", "Mockley", "Fakeman", "Demo",
        "Prototype", "Specimen", "Template", "Fixture", "Stubbs", "Draftson", "Sketch", "Outline"]
POS = ["PG", "SG", "SF", "PF", "C"]
SEASONS = [f"{y}-{str(y + 1)[2:]}" for y in range(2018, 2026)]

STAT_KEYS = ["g", "gs", "mp", "fg", "fga", "fg3", "fg3a", "ft", "fta", "orb", "drb", "ast", "stl", "blk", "tov", "pf"]


def stint_totals(rng: random.Random, g: int, skill: float, pos: str) -> dict[str, float]:
    """1 チーム分のトータルを生成。各値は整合性が取れるように作る。"""
    big = pos in ("PF", "C")
    mpg = min(38.0, max(8.0, rng.gauss(18 + 16 * skill, 3)))
    fga_pg = mpg * rng.uniform(0.32, 0.48) * (0.7 + 0.6 * skill)
    fg3a_pg = fga_pg * (rng.uniform(0.05, 0.25) if big else rng.uniform(0.3, 0.55))
    fta_pg = fga_pg * rng.uniform(0.15, 0.4)
    t = {
        "g": g,
        "gs": round(g * min(1.0, max(0.0, skill * 1.3 - 0.1 + rng.uniform(-0.1, 0.1)))),
        "mp": round(mpg * g),
        "fga": round(fga_pg * g),
        "fg3a": round(fg3a_pg * g),
        "fta": round(fta_pg * g),
        "orb": round(mpg * g * (0.08 if big else 0.025) * rng.uniform(0.7, 1.3)),
        "drb": round(mpg * g * (0.22 if big else 0.12) * rng.uniform(0.7, 1.3)),
        "ast": round(mpg * g * (0.06 if big else 0.16) * rng.uniform(0.6, 1.4) * (0.8 + 0.5 * skill)),
        "stl": round(mpg * g * 0.03 * rng.uniform(0.6, 1.4)),
        "blk": round(mpg * g * (0.04 if big else 0.012) * rng.uniform(0.6, 1.4)),
        "tov": round(mpg * g * 0.05 * rng.uniform(0.7, 1.3)),
        "pf": round(mpg * g * 0.065 * rng.uniform(0.7, 1.3)),
    }
    t["fg3"] = round(t["fg3a"] * rng.uniform(0.30, 0.41))
    fg2a = t["fga"] - t["fg3a"]
    t["fg"] = t["fg3"] + round(fg2a * rng.uniform(0.47, 0.60 if big else 0.55))
    t["ft"] = round(t["fta"] * rng.uniform(0.62 if big else 0.75, 0.80 if big else 0.92))
    return t


def derived(t: dict[str, float]) -> dict[str, float | str]:
    """トータルから派生列（2P, TRB, PTS, 各種%）を計算。"""
    d = dict(t)
    d["fg2"] = t["fg"] - t["fg3"]
    d["fg2a"] = t["fga"] - t["fg3a"]
    d["trb"] = t["orb"] + t["drb"]
    d["pts"] = 2 * d["fg2"] + 3 * t["fg3"] + t["ft"]

    def pct(a, b):
        return f"{a / b:.3f}" if b else ""

    d["fg_pct"] = pct(t["fg"], t["fga"])
    d["fg3_pct"] = pct(t["fg3"], t["fg3a"])
    d["fg2_pct"] = pct(d["fg2"], d["fg2a"])
    d["ft_pct"] = pct(t["ft"], t["fta"])
    d["efg_pct"] = pct(t["fg"] + 0.5 * t["fg3"], t["fga"])
    return d


def per_game(d: dict) -> dict:
    g = d["g"]
    out = {}
    for k, v in d.items():
        if k in ("g", "gs") or k.endswith("_pct"):
            out[k] = v
        else:
            out[k] = f"{v / g:.1f}"
    return out


def advanced(rng: random.Random, d: dict, skill: float) -> dict:
    tsa = d["fga"] + 0.44 * d["fta"]
    ws = max(-1.0, d["mp"] / 48 * (0.03 + 0.17 * skill) * rng.uniform(0.7, 1.3))
    ows = ws * rng.uniform(0.5, 0.75)
    bpm = rng.gauss(-3 + 10 * skill, 1.2)
    obpm = bpm * rng.uniform(0.5, 0.8) + rng.uniform(-0.5, 0.5)
    return {
        "g": d["g"],
        "mp": d["mp"],
        "per": f"{rng.gauss(9 + 16 * skill, 1.5):.1f}",
        "ts_pct": f"{d['pts'] / (2 * tsa):.3f}" if tsa else "",
        "fg3a_rate": f"{d['fg3a'] / d['fga']:.3f}" if d["fga"] else "",
        "fta_rate": f"{d['fta'] / d['fga']:.3f}" if d["fga"] else "",
        "usg_pct": f"{rng.gauss(14 + 16 * skill, 1.5):.1f}",
        "ows": f"{ows:.1f}",
        "dws": f"{ws - ows:.1f}",
        "ws": f"{ws:.1f}",
        "ws_48": f"{ws / d['mp'] * 48:.3f}" if d["mp"] else "",
        "obpm": f"{obpm:.1f}",
        "dbpm": f"{bpm - obpm:.1f}",
        "bpm": f"{bpm:.1f}",
        "vorp": f"{(bpm + 2) * d['mp'] / (48 * 82) * 1.0:.1f}",
    }


def main() -> None:
    rng = random.Random(20251015)
    OUT.mkdir(exist_ok=True)
    codes = [t[0] for t in TEAMS]

    players, pg_rows, tot_rows, adv_rows = [], [], [], []
    used = set()
    for i in range(48):
        while True:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        if i % 11 == 3:
            name += " Jr."
        pid = f"{name.split()[1][:5].lower()}{name.split()[0][:2].lower()}{i:02d}"
        pos = rng.choice(POS)
        start = rng.randint(0, len(SEASONS) - 2)
        # 7 割は最新シーズンまで現役
        length = len(SEASONS) - start if rng.random() < 0.7 else rng.randint(2, len(SEASONS) - start)
        birth_year = int(SEASONS[start][:4]) + 1 - rng.randint(19, 27)
        players.append({
            "player_id": pid,
            "name": name,
            "pos": pos,
            "shoots": rng.choice(["Right", "Right", "Right", "Left"]),
            "height": f"{rng.randint(6, 7)}-{rng.randint(0, 11)}",
            "weight": f"{rng.randint(180, 260)}lb",
            "birth_date": f"{birth_year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "birth_place": rng.choice(["USA", "USA", "USA", "Canada", "France", "Serbia", "Japan", "Australia"]),
            "college": rng.choice(["Sample State", "Example University", "", "Placeholder Tech"]),
            "draft": rng.choice(["1st round", "2nd round", "Undrafted"]),
        })

        skill = rng.uniform(0.05, 1.0)
        team = rng.choice(codes)
        for s_idx in range(start, start + length):
            season = SEASONS[s_idx]
            age = int(season[:4]) + 1 - birth_year
            skill = min(1.0, max(0.02, skill + rng.uniform(-0.08, 0.1)))
            g_total = rng.randint(20, 82)
            # 12% の確率でシーズン途中に移籍
            if rng.random() < 0.12:
                other = rng.choice([c for c in codes if c != team])
                split = rng.randint(5, g_total - 5)
                stints = [(team, split), (other, g_total - split)]
                team = other
            else:
                stints = [(team, g_total)]
                if rng.random() < 0.15:
                    team = rng.choice(codes)  # オフに移籍

            totals = [(tm, stint_totals(rng, g, skill, pos)) for tm, g in stints]
            if len(totals) > 1:
                summed = {k: sum(t[k] for _, t in totals) for k in STAT_KEYS}
                totals.insert(0, (f"{len(stints)}TM", summed))

            for tm, t in totals:
                d = derived(t)
                base = {"player_id": pid, "season": season, "team": tm, "age": age, "pos": pos}
                tot_rows.append({**base, **d})
                pg_rows.append({**base, **per_game(d)})
                adv_rows.append({**base, **advanced(rng, d, skill)})

    def write(name: str, rows: list[dict]) -> None:
        keys = list(rows[0].keys())
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with (OUT / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)

    write("players.csv", players)
    write("teams.csv", [dict(zip(("team", "name", "conference", "division"), t)) for t in TEAMS])
    write("per_game.csv", pg_rows)
    write("totals.csv", tot_rows)
    write("advanced.csv", adv_rows)
    print(f"{OUT} に {len(players)} 選手 / {len(tot_rows)} 行を出力しました")


if __name__ == "__main__":
    main()
