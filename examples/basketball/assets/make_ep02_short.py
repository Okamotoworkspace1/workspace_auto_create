#!/usr/bin/env python3
"""ep02_short.txt（縦型ショート）用の素材を SVG で生成する。

写真や試合映像は著作権・パブリシティ権・商標が重なるので使わない。
数字とタイポグラフィだけで 83 秒を持たせる構成にしてある。

    python3 make_ep02_short.py              # SVG を書き出す
    python3 make_ep02_short.py --png        # Chromium があれば PNG も書き出す

フォントは環境変数 JIGOE_FONT で差し替えられる。
    JIGOE_FONT="Noto Sans JP" python3 make_ep02_short.py
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# --- キャンバス ---------------------------------------------------------
W, H = 1080, 1920                     # YouTube ショート（9:16）

# セーフエリア。右はアクションボタン列、下はタイトル・チャンネル名が乗る。
SAFE_X0, SAFE_X1 = 80, 880
SAFE_Y0, SAFE_Y1 = 200, 1480
SAFE_W = SAFE_X1 - SAFE_X0

# --- 配色（dataviz スキルの検証済みパレットより）------------------------
# validate_palette.js "#e66767,#3987e5" --mode dark → 全チェック PASS
BG        = "#12120f"   # 背景（ダーク面）
INK       = "#ffffff"   # 主テキスト
INK_2     = "#c3c2b7"   # 副テキスト
INK_3     = "#85847c"   # 補助テキスト
BULLS     = "#e66767"   # カテゴリカル slot 8（赤）
WARRIORS  = "#3987e5"   # カテゴリカル slot 1（青）
LOSS      = "#4a4944"   # 敗戦セグメント（無彩色。必ず直接ラベルを添える）
LOSS_HI   = "#eda100"   # 敗戦を強調する状態（slot 4 黄）
RULE      = "#2b2b27"   # 罫線

FONT = os.environ.get("JIGOE_FONT", "IPAGothic")
FAMILY = f"'{FONT}', 'Noto Sans JP', 'Hiragino Sans', sans-serif"

OUT = pathlib.Path(__file__).parent / "ep02_short"


# --- SVG ヘルパ ---------------------------------------------------------
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size, *, fill=INK, weight=700, anchor="start", spacing=0, opacity=1.0):
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    op = f' opacity="{opacity}"' if opacity != 1.0 else ""
    return (
        f'<text x="{x}" y="{y}" font-family="{FAMILY}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}{op}>'
        f"{esc(s)}</text>"
    )


def rect(x, y, w, h, fill, *, r=0, opacity=1.0):
    if w <= 0:
        return ""
    op = f' opacity="{opacity}"' if opacity != 1.0 else ""
    rr = f' rx="{r}" ry="{r}"' if r else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{rr}{op}/>'


def card(body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">'
        f'{rect(0, 0, W, H, BG)}{body}</svg>'
    )


def kicker(y: int, s: str) -> str:
    """画面上部の小見出し。全カード共通の位置に置く。"""
    return (
        rect(SAFE_X0, y - 34, 8, 44, BULLS)
        + text(SAFE_X0 + 30, y, s, 34, fill=INK_2, weight=700, spacing=4)
    )


# --- 個別の素材 ---------------------------------------------------------
def a01_hook() -> str:
    """0:00-0:08 フック。結論を数字で置く。"""
    return card(
        kicker(300, "NBA 歴代最強のチーム")
        + text(SAFE_X0, 680, "72", 280, weight=900)
        + text(SAFE_X0 + 350, 680, "勝", 110, fill=INK_2)
        + text(SAFE_X0, 980, "10", 280, fill=INK_3, weight=900)
        + text(SAFE_X0 + 350, 980, "敗", 110, fill=INK_3)
        + rect(SAFE_X0, 1080, SAFE_W, 3, RULE)
        + text(SAFE_X0, 1200, "シカゴ・ブルズ", 76)
        + text(SAFE_X0, 1290, "1995-96 シーズン", 48, fill=INK_2, weight=400)
    )


def bar_chart(title: str, note: str, rows, *, maxval: int, unit: str) -> str:
    """縦置きの横棒グラフ。ゼロ基点・直接ラベル・凡例なし（1 指標のため）。

    チーム名が長いので、シーズンは右端に別ラベルとして逃がす。
    """
    body = kicker(300, title)
    y = 560
    for team, season, value, color, emph in rows:
        bw = int(SAFE_W * value / maxval)
        body += text(SAFE_X0, y, team, 46, fill=INK if emph else INK_2)
        body += text(SAFE_X1, y, season, 36, fill=INK_3, weight=400, anchor="end")
        # 4px 角丸をキャンバス比率に合わせて拡大（16px）
        body += rect(SAFE_X0, y + 34, bw, 96, color, r=16, opacity=1.0 if emph else 0.55)
        body += text(SAFE_X0 + bw - 28, y + 104, f"{value}", 76, fill="#12120f",
                     weight=900, anchor="end")
        y += 280
    body += rect(SAFE_X0, y - 60, SAFE_W, 3, RULE)
    body += text(SAFE_X0, y + 30, unit, 36, fill=INK_3, weight=400)
    for i, line in enumerate(note.split("\n")):
        body += text(SAFE_X0, y + 130 + i * 62, line, 46, fill=INK_2, weight=400)
    return card(body)


def a02_regular_season() -> str:
    """0:08-0:18 レギュラーシーズン勝利数。ウォリアーズが 1 つ上。"""
    return bar_chart(
        "レギュラーシーズン 勝利数",
        "記録はすでに破られている。",
        [
            ("シカゴ・ブルズ", "1995-96", 72, BULLS, False),
            ("ウォリアーズ", "2015-16", 73, WARRIORS, True),
        ],
        maxval=82,
        unit="0 〜 82 試合",
    )




def stacked_season(highlight: str) -> str:
    """通年成績の積み上げ。highlight は 'win' か 'loss'。

    同じ座標で 2 状態を書き出すので、編集側はクロスディゾルブするだけで
    「負けた数」への寄りになる。
    """
    rows = [
        ("シカゴ・ブルズ", 87, 13, BULLS),
        ("ウォリアーズ", 88, 18, WARRIORS),
    ]
    # 右端に「18敗」のラベルが載るので、その分（180px）を引いてから割る。
    # 引かないとセーフエリアをはみ出し、ショートの UI に隠れる。
    scale = (SAFE_W - 180) / 106.0    # 最長（88+18）を基準にそろえる
    win_hi = highlight == "win"
    body = kicker(300, "レギュラーシーズン ＋ プレーオフ")
    y = 580
    for label, win, loss, color in rows:
        ww, lw = int(win * scale), int(loss * scale)
        body += text(SAFE_X0, y, label, 46, fill=INK_2)
        # 積み上げの境目に 6px の背景色ギャップを入れる（2px 相当の拡大）
        body += rect(SAFE_X0, y + 34, ww, 110, color, r=16,
                     opacity=1.0 if win_hi else 0.3)
        body += rect(SAFE_X0 + ww + 6, y + 34, lw, 110,
                     LOSS if win_hi else LOSS_HI, r=16,
                     opacity=0.9 if win_hi else 1.0)
        body += text(SAFE_X0 + 24, y + 116, f"{win}勝", 64,
                     fill="#12120f" if win_hi else INK_3, weight=900)
        body += text(SAFE_X0 + ww + 6 + lw + 24, y + 116, f"{loss}敗", 64,
                     fill=INK_3 if win_hi else LOSS_HI, weight=900)
        y += 300
    body += rect(SAFE_X0, y - 40, SAFE_W, 3, RULE)
    if win_hi:
        body += text(SAFE_X0, y + 70, "勝った数だけなら", 50, fill=INK_2, weight=400)
        body += text(SAFE_X0, y + 155, "ウォリアーズが上。", 68, fill=INK)
    else:
        body += text(SAFE_X0, y + 70, "違うのは", 50, fill=INK_2, weight=400)
        body += text(SAFE_X0, y + 155, "負けた数だった。", 68, fill=LOSS_HI)
    return card(body)





def a00_safe_area() -> str:
    """編集時の確認用。セーフエリアのガイド。書き出しには乗せない。"""
    return card(
        rect(SAFE_X0, SAFE_Y0, SAFE_W, SAFE_Y1 - SAFE_Y0, "#ffffff", opacity=0.06)
        + f'<rect x="{SAFE_X0}" y="{SAFE_Y0}" width="{SAFE_W}" '
        f'height="{SAFE_Y1 - SAFE_Y0}" fill="none" stroke="{BULLS}" '
        f'stroke-width="3" stroke-dasharray="18 14"/>'
        + rect(880, 0, 200, H, LOSS_HI, opacity=0.10)
        + rect(0, 1480, W, H - 1480, LOSS_HI, opacity=0.10)
        + text(SAFE_X0, SAFE_Y0 - 30, "SAFE AREA 1080x1920", 34, fill=INK_2, spacing=3)
        + text(920, 1000, "UI", 44, fill=INK_3, anchor="middle")
        + text(SAFE_X0, 1560, "タイトル・チャンネル名が乗る領域", 40, fill=INK_3, weight=400)
    )


# ここにあるのは「探してこられない絵」だけ。
# 人物・会場・試合の画は Commons などから持ってくる（README.md の素材表）。
# 数字の図解は一次情報から自分で起こすしかなく、workflow.md が求める
# 「動画ごと最低 1 点の独自図解」も兼ねる。
CARDS = [
    ("00_safe-area",        a00_safe_area,                    "（ガイド）"),
    ("01_hook",             a01_hook,                         "0:00-0:08"),
    ("02_regular-season",   a02_regular_season,               "0:08-0:18"),
    ("05a_season-wins",     lambda: stacked_season("win"),    "0:30-0:43"),
    ("05b_season-losses",   lambda: stacked_season("loss"),   "0:43-0:48"),
]


def find_chromium() -> str | None:
    for c in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        if (p := shutil.which(c)):
            return p
    for p in pathlib.Path("/opt/pw-browsers").glob("chromium*/chrome-linux/*"):
        if p.name in ("chrome", "headless_shell") and os.access(p, os.X_OK):
            return str(p)
    return None


def to_png(svg_path: pathlib.Path, png_path: pathlib.Path, browser: str) -> bool:
    html = (
        f"<!doctype html><meta charset='utf-8'>"
        f"<style>html,body{{margin:0;padding:0;background:{BG}}}</style>"
        f"{svg_path.read_text(encoding='utf-8')}"
    )
    with tempfile.TemporaryDirectory() as td:
        page = pathlib.Path(td) / "page.html"
        page.write_text(html, encoding="utf-8")
        r = subprocess.run(
            [browser, "--headless", "--no-sandbox", "--disable-gpu",
             "--hide-scrollbars", f"--window-size={W},{H}",
             f"--screenshot={png_path}", f"--virtual-time-budget=1500",
             page.as_uri()],
            capture_output=True, cwd=td,
        )
        return r.returncode == 0 and png_path.exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", action="store_true", help="PNG も書き出す")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    browser = find_chromium() if args.png else None
    if args.png and not browser:
        print("Chromium が見つからないので SVG だけ書き出します。", file=sys.stderr)

    for name, fn, cue in CARDS:
        svg = OUT / f"{name}.svg"
        svg.write_text(fn(), encoding="utf-8")
        line = f"  {cue:<12} {svg.name}"
        if browser:
            png = OUT / f"{name}.png"
            line += "  →  " + (png.name if to_png(svg, png, browser) else "PNG 失敗")
        print(line)

    print(f"\n{len(CARDS)} 点を {OUT} に書き出しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
