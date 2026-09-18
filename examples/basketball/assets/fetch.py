#!/usr/bin/env python3
"""カタログの画像をまとめてダウンロードする。

    python3 fetch.py              # Commons の画像・動画を downloads/ に落とす
    python3 fetch.py --width 1080 # 横幅を指定して縮小版を取る（既定 1600）
    python3 fetch.py ブルズ        # 部分一致で絞る

Commons のファイルページ URL を Special:FilePath に変換して直接取得する。
カテゴリ・素材サイト・ローカルの自作図解は対象外。

**この開発環境では commons.wikimedia.org への通信が遮断されているため失敗します。**
手元のマシンで実行してください。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).parent
OUT = HERE / "downloads"
COLUMNS = ["ID", "ラベル", "タグ", "年", "種別", "ライセンス", "継承", "URL", "確認", "メモ"]
UA = "jigoe-asset-fetcher/1.0 (basketball trivia channel; contact via repo)"

# Wikimedia が事前生成しているサムネ幅。ここに無い幅を頼むとサーバ側で
# 毎回レンダリングが走り、429（Too many requests）で弾かれる。
THUMB_WIDTHS = (320, 640, 800, 1024, 1280, 2560)
PAUSE_SECONDS = 1.0          # 1 件ごとに待つ
RETRY_WAITS = (5, 15, 45)    # 429 が返ったときの待ち時間


def load() -> list[dict[str, str]]:
    rows = []
    for line in (HERE / "catalog.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if cells[0] == "ID" or len(cells) < len(COLUMNS):
            continue
        rows.append(dict(zip(COLUMNS, cells)))
    return rows


def direct_url(page_url: str, width: int | None) -> str | None:
    """Commons のファイルページ URL を、ファイル本体の URL に変換する。

    .../wiki/File:Foo_Bar.jpg  ->  .../wiki/Special:FilePath/Foo_Bar.jpg
    Special:FilePath は本体へリダイレクトするので、これで直接落とせる。
    """
    marker = "/wiki/File:"
    if marker not in page_url:
        return None
    name = page_url.split(marker, 1)[1]
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{name}"
    # width はラスタ画像にだけ効く。PDF や webm に付けても無視されるか失敗するので付けない。
    if width and name.lower().endswith((".jpg", ".jpeg", ".png")):
        url += f"?width={width}"
    return url


def main() -> int:
    ap = argparse.ArgumentParser(description="カタログの画像を一括ダウンロード")
    ap.add_argument("query", nargs="*", help="ラベル・タグ・IDへの部分一致で絞る")
    ap.add_argument("--width", type=int, default=2560,
                    help=f"横幅（既定 2560）。Wikimedia が用意している幅は "
                         f"{THUMB_WIDTHS}。ここに無い値は 429 で弾かれやすい")
    ap.add_argument("--full", action="store_true", help="縮小せず原寸で取る")
    args = ap.parse_args()

    rows = load()
    for q in args.query:
        rows = [r for r in rows if q in r["ラベル"] + r["タグ"] + r["ID"] + r["メモ"]]

    targets = []
    for r in rows:
        url = direct_url(r["URL"], None if args.full else args.width)
        if url:
            targets.append((r, url))

    if not targets:
        print("対象がありません（カテゴリ・素材サイト・自作図解は対象外）", file=sys.stderr)
        return 1

    OUT.mkdir(exist_ok=True)
    if not args.full and args.width not in THUMB_WIDTHS:
        print(f"注意: 幅 {args.width} は Wikimedia の標準サムネイル幅 "
              f"{THUMB_WIDTHS} にありません。429 で弾かれやすくなります。",
              file=sys.stderr)
    ok = fail = 0
    for r, url in targets:
        ext = pathlib.PurePosixPath(urllib.parse.urlparse(url).path).suffix or ".bin"
        dest = OUT / f'{r["ID"]}{ext}'
        if dest.exists():
            print(f'  = {dest.name}  （取得済み）')
            ok += 1
            continue
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        for attempt, wait in enumerate((0, *RETRY_WAITS)):
            if wait:
                print(f'    429 のため {wait} 秒待って再試行 '
                      f'({attempt}/{len(RETRY_WAITS)})', file=sys.stderr)
                time.sleep(wait)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    dest.write_bytes(resp.read())
                print(f'  + {dest.name}  {r["ラベル"]}  [{r["ライセンス"]}]')
                ok += 1
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < len(RETRY_WAITS):
                    continue
                print(f'  ! {r["ID"]}  取得できず: {e}', file=sys.stderr)
                fail += 1
                break
            except (urllib.error.URLError, OSError) as e:
                print(f'  ! {r["ID"]}  取得できず: {e}', file=sys.stderr)
                fail += 1
                break
        time.sleep(PAUSE_SECONDS)   # 連続で叩かない

    print(f"\n{ok} 件取得 / {fail} 件失敗  →  {OUT}")
    if ok:
        print("クレジットは catalog.tsv の ライセンス 欄を見ること。"
              "著作者名はファイルページから写す（このスクリプトは取得しない）。")
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
