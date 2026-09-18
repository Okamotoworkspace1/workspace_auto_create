#!/usr/bin/env python3
"""収録原稿.txt と同じ内容を、読み上げやすい PDF に組む。

紙に印刷したりタブレットに入れたりして、声に出して読むための版面にしている。
文字を大きめに、行間を広く、1 文ごとに薄い帯を敷いて目線が迷わないようにした。

使い方:
    pip install reportlab
    python examples/recording/make_pdf.py

日本語フォントは環境にあるものを自動で探す。見つからない場合は
FONT_CANDIDATES にパスを足すこと。
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    LongTable,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
)

CORPUS_URL = "https://raw.githubusercontent.com/mmorise/ita-corpus/main/{}"
CORPUS_FILES = ["emotion_transcript_utf8.txt", "recitation_transcript_utf8.txt"]

#: 日本語フォントの探索先（先に見つかったものを使う）
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
]

FONT_NAME = "JP"
ACCENT = colors.HexColor("#b4522d")
MUTED = colors.HexColor("#8a8580")
BAND = colors.HexColor("#f4f1ec")
RULE = colors.HexColor("#e2ded8")

#: 到達目安（文番号 -> 見出し, 補足）
MILESTONES = {
    150: ("ここまでで約 12 分", "学習に必要な最低ライン。疲れていたらここで終えて構いません。"),
    300: ("ここまでで約 25 分", "品質が安定する量です。"),
}


def register_font() -> None:
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            pdfmetrics.registerFont(TTFont(FONT_NAME, path))
            return
    sys.exit(
        "日本語フォントが見つかりません。FONT_CANDIDATES にフォントのパスを追加してください。"
    )


def load_sentences(cache_dir: Path) -> list[str]:
    """ITAコーパスの文を取得する（ダウンロード済みならそれを使う）。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    sentences: list[str] = []
    for name in CORPUS_FILES:
        path = cache_dir / name
        if not path.is_file():
            urllib.request.urlretrieve(CORPUS_URL.format(name), path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            # 「ID:表記,カタカナ読み」から表記だけを取る
            surface = line.split(":", 1)[1].split(",")[0].strip()
            if surface:
                sentences.append(surface)
    return sentences


def build_styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName=FONT_NAME, fontSize=19, leading=26, spaceAfter=2
        ),
        "lead": ParagraphStyle(
            "lead", fontName=FONT_NAME, fontSize=9.5, leading=15, textColor=MUTED
        ),
        "section": ParagraphStyle(
            "section",
            fontName=FONT_NAME,
            fontSize=11,
            leading=16,
            textColor=ACCENT,
            spaceBefore=12,
            spaceAfter=4,
        ),
        # wordWrap="CJK" で日本語の行分割と禁則処理（句読点を行頭に置かない）が働く
        "note": ParagraphStyle(
            "note", fontName=FONT_NAME, fontSize=10, leading=17, wordWrap="CJK"
        ),
        "num": ParagraphStyle(
            "num", fontName=FONT_NAME, fontSize=9, leading=20, textColor=MUTED
        ),
        "line": ParagraphStyle(
            "line",
            fontName=FONT_NAME,
            fontSize=13,
            leading=21,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "milestone": ParagraphStyle(
            "milestone",
            fontName=FONT_NAME,
            fontSize=11.5,
            leading=18,
            textColor=ACCENT,
            spaceBefore=10,
            spaceAfter=10,
        ),
    }


def cover(styles: dict[str, ParagraphStyle]) -> list:
    story = [
        Paragraph("収録原稿", styles["title"]),
        Paragraph(
            "自分の声のモデルを作るための読み上げ原稿 ／ ITAコーパス 424 文"
            "（パブリックドメイン・github.com/mmorise/ita-corpus）",
            styles["lead"],
        ),
        Paragraph("録音をはじめる前に", styles["section"]),
        Paragraph(
            "□ エアコン・PCのファン・冷蔵庫など、鳴っているものを止める<br/>"
            "□ マイクと口の距離を決める<br/>"
            "□ スマホの通知を切る",
            styles["note"],
        ),
        Paragraph("読むときのルール", styles["section"]),
        Paragraph(
            "・録音は止めずに、最後まで通しで録る（1 本のファイルにする）<br/>"
            "・番号は読まない。文だけを読む<br/>"
            "・1 文読んだら 1〜2 秒あけて次へ<br/>"
            "・噛んだら、少し間をあけて同じ文をもう一度読む"
            "（録音は止めなくてよい。あとで自動的に整理される）<br/>"
            "・<b>声の大きさ・話す速さ・マイクとの距離を最後まで一定に保つ</b>"
            "。ここが品質を決めます<br/>"
            "・抑揚をつけすぎず、ナレーションで実際に使うトーンで読む",
            styles["note"],
        ),
        Paragraph("どこまで読むか", styles["section"]),
        Paragraph(
            "150 番まで … 約 12 分。ここまでで学習できます（まずはここを目標に）<br/>"
            "300 番まで … 約 25 分。品質が安定します<br/>"
            "424 番まで … 全部。いちばん良い結果になります<br/><br/>"
            "途中で疲れたら、キリのいい番号でやめて構いません。"
            "あとから追加で録音して足すこともできます。",
            styles["note"],
        ),
        Spacer(1, 14),
    ]
    return story


def sentence_table(rows: list[tuple[int, str]], styles: dict[str, ParagraphStyle]) -> LongTable:
    data = [
        [Paragraph(f"{n}", styles["num"]), Paragraph(text, styles["line"])]
        for n, text in rows
    ]
    table = LongTable(data, colWidths=[13 * mm, 157 * mm], hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
    ]
    # 1 行おきに薄い帯を敷く。読み上げ中に目線が迷いにくくなる。
    for i, (n, _) in enumerate(rows):
        if n % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    table.setStyle(TableStyle(style))
    return table


def milestone(number: int, styles: dict[str, ParagraphStyle]) -> Paragraph:
    heading, note = MILESTONES[number]
    return Paragraph(f"── {heading} ──　{note}", styles["milestone"])


def on_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))
    canvas.drawString(20 * mm, 12 * mm, "収録原稿 — jigoe")
    canvas.restoreState()


def main() -> None:
    register_font()
    here = Path(__file__).resolve().parent
    sentences = load_sentences(here / ".corpus")
    styles = build_styles()

    doc = BaseDocTemplate(
        str(here / "収録原稿.pdf"),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="収録原稿 — 自分の声のモデルを作るための読み上げ原稿",
        author="jigoe",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])

    story = cover(styles)
    chunk: list[tuple[int, str]] = []
    for n, text in enumerate(sentences, start=1):
        chunk.append((n, text))
        if n in MILESTONES:
            story.append(sentence_table(chunk, styles))
            story.append(milestone(n, styles))
            chunk = []
    if chunk:
        story.append(sentence_table(chunk, styles))

    doc.build(story)
    print(f"作成しました: {here / '収録原稿.pdf'}（{len(sentences)} 文）")


if __name__ == "__main__":
    main()
