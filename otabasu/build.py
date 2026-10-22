#!/usr/bin/env python3
"""オタバス NBA データ室を 1 枚の HTML にまとめて出力する（Python 3.11 以上・標準ライブラリのみ）。

    python build.py --pages pages        # Cloudflare Pages 用フォルダ（index.html ほか）
    python build.py --single site.html   # claude.ai Artifact 用（<html> 骨組みなし）

入力（data/ 以下。公開リポジトリには含めない）:
    draft.csv              ドラフト評価（スプレッドシート「全選手一覧」を CSV で書き出したもの）
    defense_2025_26.json   DF 指標（選手ごとの dict の配列）
    logo_mark.webp         ヘッダー用のロゴ（ボール部分）
    logo_full.webp         トップページ用のロゴ（文字入り）
    favicon.png            ブラウザのタブ用アイコン
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECENT_FROM = 2023  # この年以降の指名はキャリアが短く、評価途中として扱う

DRAFT_HEADER = [
    "ドラフト年", "ラウンド", "指名順位", "選手名", "", "初年度所属チーム", "AS選出回数",
    "ALL NBA 3rd", "ALL NBA 2nd", "ALL NBA 1st", "ALL DF 2nd", "ALL DF 1st", "DPOY", "MVP", "FMVP",
    "総出場分数", "平均出場分数", "得点", "平均値", "フィッティング", "スコア-平均値", "スコア-フィッティング",
]
GRADES = {"SSS": 6, "SS": 5, "S": 4, "A": 3, "B": 2, "C": 1, "D": 0}
DEF_FIELDS = [
    "player", "team", "pos", "g", "gs", "mp", "mpg", "dbpm", "dws", "drtg",
    "blkpct", "stlpct", "drbpct", "dfg", "diff", "dfga", "honors",
]


def name_key(name: str) -> str:
    """表記ゆれを吸収した照合用キー（アクセント・記号・Jr. などを除く）。"""
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    words = [w for w in s.split() if w not in {"jr", "sr", "ii", "iii", "iv"}]
    return " ".join(words)


def slug(name: str) -> str:
    return name_key(name).replace(" ", "-") or "player"


def num(text: str, kind=float):
    """'19,862' → 19862、'-' や空欄 → None。"""
    t = (text or "").strip().replace(",", "")
    if t in ("", "-"):
        return None
    return kind(float(t)) if kind is int else float(t)


def load_draft(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = [h.strip() for h in rows[0]]
    if header[: len(DRAFT_HEADER)] != DRAFT_HEADER:
        raise SystemExit(f"{path.name} の列がスプレッドシートの想定と違います:\n  {header}")
    out = []
    for n, r in enumerate(rows[1:], start=2):
        if not r or not r[0].strip():
            continue
        grade = r[4].strip()
        if grade not in GRADES:
            raise SystemExit(f"{path.name}:{n} 評価 '{grade}' が SSS〜D のどれでもありません")
        out.append({
            "year": int(r[0]), "round": int(r[1]), "pick": int(r[2]), "name": r[3].strip(), "grade": grade,
            "team": r[5].strip(),
            "as": num(r[6], int) or 0, "nba3": num(r[7], int) or 0, "nba2": num(r[8], int) or 0, "nba1": num(r[9], int) or 0,
            "def2": num(r[10], int) or 0, "def1": num(r[11], int) or 0,
            "dpoy": num(r[12], int) or 0, "mvp": num(r[13], int) or 0, "fmvp": num(r[14], int) or 0,
            "min": num(r[15], int), "mpg": num(r[16]),
            "score": int(r[17]), "avg": num(r[18]), "fit": num(r[19]), "dfit": num(r[21]),
        })
    return out


def build_data(data_dir: Path) -> dict:
    draft = load_draft(data_dir / "draft.csv")
    defense = json.loads((data_dir / "defense_2025_26.json").read_text(encoding="utf-8"))

    # 選手 ID: 同名の別人がいれば年を付けて区別する
    by_key = defaultdict(list)
    for i, d in enumerate(draft):
        by_key[name_key(d["name"])].append(i)
    for key, idx in by_key.items():
        for i in idx:
            draft[i]["id"] = slug(draft[i]["name"]) + (f"-{draft[i]['year']}" if len(idx) > 1 else "")
            draft[i]["def"] = None

    used_ids = {d["id"] for d in draft}
    defense_out = []
    for j, d in enumerate(defense):
        row = {k: d.get(k) for k in DEF_FIELDS}
        idx = by_key.get(name_key(d["player"]), [])
        if len(idx) == 1:  # 同名が複数いるときは誤リンクを避けてつながない
            row["id"] = draft[idx[0]]["id"]
            row["di"] = idx[0]
            draft[idx[0]]["def"] = j
        else:
            pid = slug(d["player"])
            row["id"] = pid if pid not in used_ids else pid + "-df"
            row["di"] = None
        defense_out.append(row)

    rows = [[
        d["year"], d["round"], d["pick"], d["name"], d["grade"], d["team"], d["as"], d["nba3"], d["nba2"], d["nba1"],
        d["def2"], d["def1"], d["dpoy"], d["mvp"], d["fmvp"], d["min"], d["mpg"], d["score"], d["avg"], d["fit"], d["dfit"],
        d["id"], d["def"],
    ] for d in draft]
    return {
        "built": dt.datetime.now().strftime("%Y-%m-%d"),
        "recentFrom": RECENT_FROM,
        "draft": rows,
        "defense": defense_out,
    }


def data_uri(path: Path) -> str:
    mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg"}[path.suffix.lower()]
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def render(data_dir: Path, full_document: bool) -> str:
    data = build_data(data_dir)
    # </script> を含む文字列でスクリプトが途切れないようにする
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = (HERE / "web" / "template.html").read_text(encoding="utf-8")
    page = (page.replace("{{DATA}}", payload)
                .replace("{{APP_JS}}", (HERE / "web" / "app.js").read_text(encoding="utf-8"))
                .replace("{{LOGO_MARK}}", data_uri(data_dir / "logo_mark.webp"))
                .replace("{{LOGO_FULL}}", data_uri(data_dir / "logo_full.webp")))
    if not full_document:
        return page
    # 普通の Web サーバー用: 完全な HTML 文書にする
    head, sep, body = page.partition("<header")
    head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    return (
        '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="referrer" content="no-referrer">\n<link rel="icon" href="favicon.png">\n'
        f"{head}</head>\n<body>\n{sep}{body}</body>\n</html>\n"
    )


def build_pages(data_dir: Path, out: Path) -> Path:
    marker = out / ".otabasu-build"
    if out.exists() and any(out.iterdir()) and not marker.exists():
        raise SystemExit(f"{out} は空でなく、このツールの出力先ではありません。別の出力先を指定してください。")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    marker.write_text("generated by otabasu/build.py\n", encoding="utf-8")
    (out / "index.html").write_text(render(data_dir, True), encoding="utf-8")
    shutil.copy2(data_dir / "favicon.png", out / "favicon.png")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    # Cloudflare Pages はこのファイルを読んで HTTP ヘッダーを付ける
    (out / "_headers").write_text(
        "/*\n  X-Robots-Tag: noindex, nofollow, noarchive\n  Referrer-Policy: no-referrer\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="オタバス NBA データ室をビルド")
    ap.add_argument("--data", type=Path, default=HERE / "data")
    ap.add_argument("--pages", type=Path, metavar="DIR", help="Cloudflare Pages 用フォルダを出力")
    ap.add_argument("--single", type=Path, metavar="FILE", help="Artifact 用の 1 ファイルを出力")
    args = ap.parse_args(argv)
    if not args.pages and not args.single:
        ap.error("--pages か --single を指定してください")
    if args.pages:
        out = build_pages(args.data, args.pages)
        print(f"{out} を出力しました（index.html {(out / 'index.html').stat().st_size / 1024:.0f} KB）")
    if args.single:
        args.single.parent.mkdir(parents=True, exist_ok=True)
        args.single.write_text(render(args.data, False), encoding="utf-8")
        print(f"{args.single} を出力しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
