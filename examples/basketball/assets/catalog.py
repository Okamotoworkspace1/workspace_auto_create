#!/usr/bin/env python3
"""素材カタログ（catalog.tsv）を検索する。

    python3 catalog.py                  全件
    python3 catalog.py ロッドマン        ラベル・タグ・メモの部分一致
    python3 catalog.py --no-sa          継承なしだけ（収益化チャンネル向き）
    python3 catalog.py --kind 動画      種別で絞る
    python3 catalog.py --todo           確認がまだのものだけ
    python3 catalog.py ブルズ --no-sa --urls   URL だけ出す
"""

from __future__ import annotations

import argparse
import pathlib
import sys

COLUMNS = ["ID", "ラベル", "タグ", "年", "種別", "ライセンス", "継承", "URL", "確認", "メモ"]
CATALOG = pathlib.Path(__file__).parent / "catalog.tsv"


def width(s: str) -> int:
    """全角を 2 桁として数える。"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - width(s))


def load() -> list[dict[str, str]]:
    rows = []
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if cells[0] == "ID" or len(cells) < len(COLUMNS):
            continue
        rows.append(dict(zip(COLUMNS, cells)))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="素材カタログを検索する")
    ap.add_argument("query", nargs="*", help="ラベル・タグ・メモへの部分一致")
    ap.add_argument("--no-sa", action="store_true", help="継承なしだけ")
    ap.add_argument("--kind", help="種別で絞る（写真 / 動画 / 文書 / ロゴ / カテゴリ / 図解）")
    ap.add_argument("--todo", action="store_true", help="確認がまだのものだけ")
    ap.add_argument("--urls", action="store_true", help="URL だけ出す")
    args = ap.parse_args()

    rows = load()
    for q in args.query:
        rows = [r for r in rows
                if q in r["ラベル"] + r["タグ"] + r["ID"] + r["メモ"]]
    if args.no_sa:
        # 「要確認」は継承なしと断定できないので落とす。
        # このフィルタは収益化の判断に使うものなので、疑わしいものは通さない。
        rows = [r for r in rows if r["継承"] in ("なし", "—")]
    if args.kind:
        rows = [r for r in rows if args.kind in r["種別"]]
    if args.todo:
        rows = [r for r in rows if r["確認"] == "未"]

    if not rows:
        print("該当なし", file=sys.stderr)
        return 1

    if args.urls:
        for r in rows:
            print(r["URL"])
        return 0

    wl = max(width(r["ラベル"]) for r in rows)
    wk = max(width(r["種別"]) for r in rows)
    wc = max(width(r["ライセンス"]) for r in rows)
    for r in rows:
        mark = "!" if r["確認"] == "未" else " "
        sa = "継承" if r["継承"] == "あり" else "  "
        print(f'{mark} {pad(r["ラベル"], wl)}  {pad(r["種別"], wk)}  '
              f'{pad(r["ライセンス"], wc)} {sa}  {r["URL"]}')

    todo = sum(1 for r in rows if r["確認"] == "未")
    print(f"\n{len(rows)} 件"
          + (f"（! = ライセンス未確認 {todo} 件。使う前にファイルページを開くこと）" if todo else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
