#!/usr/bin/env python3
"""台本から絵コンテ（素材の割り当て表）を自動生成する。

    jigoe speak scripts/ep02_short.txt            # 先に report.json を作る
    python3 assets/storyboard.py out/ep02_short.report.json

`keywords.tsv` の語が台詞に出たら、対応する素材を当てる。
どれにも当たらなかった区間は受け皿（`*` の行）で埋める。

**まず全カットを埋めることを優先する。** 年代が合うか、権利が通るかは後工程。
合わないと分かったら keywords.tsv の素材ID を差し替えるだけでよい。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
FALLBACK = "*"


def load_catalog() -> dict[str, dict[str, str]]:
    cols = ["ID", "ラベル", "タグ", "年", "種別", "ライセンス", "継承", "URL", "確認", "メモ"]
    out = {}
    for line in (HERE / "catalog.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if cells[0] == "ID" or len(cells) < len(cols):
            continue
        out[cells[0]] = dict(zip(cols, cells))
    return out


# 1 カットの上限。これを超えたら同じ素材でも切り直す。
# 受け皿が続くと 30 秒 1 枚のような絵コンテになってしまうため。
MAX_SHOT_SECONDS = 8.0


def keyword_files(name: str) -> list[pathlib.Path]:
    """共通の keywords.tsv と、回ごとの keywords.<回>.tsv を集める。

    回ごとのファイルを先に置く。同じ長さのキーワードがぶつかったとき、
    安定ソートで回ごとの割り当てが勝つ。
    """
    files = []
    for cand in (f"keywords.{name}.tsv", f"keywords.{name.split('_')[0]}.tsv"):
        if (p := HERE / cand).exists() and p not in files:
            files.append(p)
    files.append(HERE / "keywords.tsv")
    return files


def load_keywords(name: str) -> list[tuple[str, str]]:
    """(キーワード, 素材ID) を長い順に返す。長いほうが優先される。"""
    pairs = []
    for path in keyword_files(name):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cells = line.split("\t")
            if len(cells) >= 2 and cells[0] and cells[1]:
                pairs.append((cells[0], cells[1]))
    return sorted(pairs, key=lambda p: -len(p[0]))


def pick(text: str, keywords: list[tuple[str, str]]) -> tuple[str, str]:
    """台詞に当たる素材IDと、当たったキーワードを返す。"""
    for kw, asset in keywords:
        if kw != FALLBACK and kw in text:
            return asset, kw
    for kw, asset in keywords:
        if kw == FALLBACK:
            return asset, ""
    return "", ""


def mmss(t: float) -> str:
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="台本から絵コンテを作る")
    ap.add_argument("report", help="jigoe speak が出す *.report.json")
    ap.add_argument("-o", "--out", help="書き出し先 (.md)。省略すると標準出力")
    args = ap.parse_args()

    report = json.loads(pathlib.Path(args.report).read_text(encoding="utf-8"))
    name = pathlib.Path(args.report).name.replace(".report.json", "")
    catalog, keywords = load_catalog(), load_keywords(name)

    # 台詞ごとに素材を決め、同じ素材が続く区間はひとつのカットにまとめる
    shots: list[dict] = []
    for seg in report["timeline"]:
        if seg["kind"] != "speech":
            continue
        asset, kw = pick(seg["text"], keywords)
        long_enough = shots and seg["end"] - shots[-1]["start"] > MAX_SHOT_SECONDS
        if shots and shots[-1]["asset"] == asset and not long_enough:
            shots[-1]["end"] = seg["end"]
            shots[-1]["lines"].append(seg["text"])
        else:
            shots.append({"start": seg["start"], "end": seg["end"], "asset": asset,
                          "kw": kw, "lines": [seg["text"]]})

    rows = [
        f"# {name} 絵コンテ",
        "",
        f"`storyboard.py` が自動生成。全 {report['duration_display']}・{len(shots)} カット。",
        "",
        "素材を変えたいときは `assets/keywords.tsv` の素材ID を差し替えて再実行する。",
        "",
        "| 時間 | 台詞 | 素材 | 入手先 |",
        "|---|---|---|---|",
    ]
    filled = 0
    for s in shots:
        c = catalog.get(s["asset"], {})
        label = c.get("ラベル", s["asset"] or "—")
        url = c.get("URL", "")
        link = f"[開く]({url})" if url.startswith("http") else f"`{url}`"
        hit = f"`{s['kw']}`" if s["kw"] else "（受け皿）"
        if s["kw"]:
            filled += 1
        text = "<br>".join(s["lines"])
        rows.append(f"| {mmss(s['start'])}-{mmss(s['end'])} | {text} | {label} {hit} | {link} |")

    rows += [
        "",
        f"キーワードが当たったカット: {filled} / {len(shots)}"
        f"（残りは受け皿の b-roll。keywords.tsv に語を足せば埋まる）",
        "",
        "## 使った素材",
        "",
        "| 素材 | ライセンス | 継承 | 確認 | 入手先 |",
        "|---|---|---|---|---|",
    ]
    for aid in dict.fromkeys(s["asset"] for s in shots):
        c = catalog.get(aid)
        if not c:
            rows.append(f"| `{aid}` | **カタログに無い** | | | |")
            continue
        url = c["URL"]
        link = f"[開く]({url})" if url.startswith("http") else f"`{url}`"
        rows.append(f'| {c["ラベル"]} | {c["ライセンス"]} | {c["継承"]} | {c["確認"]} | {link} |')

    out = "\n".join(rows) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(out, encoding="utf-8")
        print(f"{args.out} に {len(shots)} カットを書き出しました "
              f"（キーワード一致 {filled}/{len(shots)}）")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
