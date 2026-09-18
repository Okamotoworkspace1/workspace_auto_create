"""読み辞書と誤読チェック。

リサーチでは音声工程の AI 代替度は 95%、人間が残すべき 5% は
「固有名詞（選手名）とスコアの誤読チェック」とされている。ここはその 5% を
機械的に検出して人間に差し出すためのモジュール。

* :class:`Lexicon` — ``表記<TAB>読み`` の対応表。合成前に置換する。
* :func:`find_risky_terms` — 辞書に未登録のカタカナ語・英字・スコア表記・
  小数を「誤読しやすい箇所」として列挙する。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

# 中黒（・）を含めて「レブロン・ジェームズ」を 1 語として拾う
KATAKANA = re.compile(r"[ァ-ヺーヽヾ]+(?:・[ァ-ヺーヽヾ]+)*")
LATIN = re.compile(r"[A-Za-z][A-Za-z'’.\-]*[A-Za-z]")
SCORE = re.compile(r"\d+\s*[-−–—ー]\s*\d+")
DECIMAL = re.compile(r"\d+[.．]\d+")

#: カタカナだが一般語で、辞書登録を促す必要がないもの
COMMON_KATAKANA = frozenset(
    {
        "バスケ", "バスケット", "バスケットボール", "シュート", "パス", "ドリブル",
        "リバウンド", "アシスト", "スティール", "ブロック", "ファウル", "コート",
        "ゴール", "リーグ", "シーズン", "チーム", "プレー", "プレイ", "プレイヤー",
        "スタッツ", "ランキング", "ドラフト", "トレード", "ルーキー", "ベテラン",
        "オフェンス", "ディフェンス", "スリーポイント", "フリースロー", "ダンク",
        "レギュラー", "ファイナル", "チャンピオン", "タイトル", "スター", "ファン",
        "コーチ", "スタジアム", "アリーナ", "ポイント", "ゲーム", "キャリア",
    }
)

#: 英字だが読み替え不要なもの（頭字語として自然に読まれる）
COMMON_LATIN = frozenset({"NBA", "WNBA", "MVP", "NCAA", "FIBA", "AI", "TV", "US", "USA"})


@dataclass(frozen=True)
class Entry:
    """辞書 1 件。"""

    surface: str
    reading: str
    note: str = ""


@dataclass(frozen=True)
class Risk:
    """誤読しやすいと判定された語。"""

    term: str
    kind: str  # katakana | latin | score | decimal
    count: int

    @property
    def advice(self) -> str:
        return {
            "katakana": "固有名詞なら読み辞書に登録して読みを固定する",
            "latin": "英字はエンジンごとに読みが揺れる。カタカナ読みを登録する",
            "score": "「118-110」は「118対110」など読み方を明示する",
            "decimal": "小数は「27.4」→「27てん4」など読みを確認する",
        }.get(self.kind, "読みを確認する")


class Lexicon:
    """表記 → 読み の置換テーブル。長い表記から順に適用する。"""

    def __init__(self, entries: list[Entry] | None = None) -> None:
        self._entries: dict[str, Entry] = {}
        for entry in entries or []:
            self.add(entry)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, surface: object) -> bool:
        return isinstance(surface, str) and surface in self._entries

    @property
    def entries(self) -> list[Entry]:
        return sorted(self._entries.values(), key=lambda e: e.surface)

    def add(self, entry: Entry) -> None:
        if not entry.surface:
            raise ConfigError("読み辞書の表記が空です")
        self._entries[entry.surface] = entry

    def covers(self, term: str) -> bool:
        """その語が辞書で（部分的にでも）カバーされているか。

        台本全体を踏まえた正確な判定は :func:`find_risky_terms` が行う。
        こちらは文脈を持たない単体チェック用。
        """
        if term in self._entries:
            return True
        return any(surface in term for surface in self._entries)

    def apply(self, text: str) -> tuple[str, Counter]:
        """辞書を適用したテキストと、適用回数を返す。"""
        used: Counter = Counter()
        if not self._entries:
            return text, used
        for surface in sorted(self._entries, key=len, reverse=True):
            if surface in text:
                used[surface] += text.count(surface)
                text = text.replace(surface, self._entries[surface].reading)
        return text, used

    def merge(self, other: "Lexicon") -> None:
        for entry in other.entries:
            self.add(entry)

    # --- 入出力 ---------------------------------------------------------

    @classmethod
    def from_tsv(cls, text: str, *, origin: str = "<tsv>") -> "Lexicon":
        lex = cls()
        for line_no, raw in enumerate(text.splitlines(), start=1):
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
                raise ConfigError(
                    f"{origin}:{line_no}: 読み辞書は「表記<TAB>読み[<TAB>メモ]」の形式です"
                )
            lex.add(
                Entry(
                    surface=parts[0].strip(),
                    reading=parts[1].strip(),
                    note=parts[2].strip() if len(parts) > 2 else "",
                )
            )
        return lex

    @classmethod
    def from_json(cls, text: str, *, origin: str = "<json>") -> "Lexicon":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{origin}: JSON を解析できません: {exc}") from exc
        lex = cls()
        if isinstance(data, dict):
            items = [{"surface": k, "reading": v} for k, v in data.items()]
        elif isinstance(data, list):
            items = data
        else:
            raise ConfigError(f"{origin}: オブジェクトか配列で書いてください")
        for item in items:
            if not isinstance(item, dict) or "surface" not in item or "reading" not in item:
                raise ConfigError(f"{origin}: 各項目に surface と reading が必要です")
            lex.add(
                Entry(
                    surface=str(item["surface"]),
                    reading=str(item["reading"]),
                    note=str(item.get("note", "")),
                )
            )
        return lex

    @classmethod
    def load(cls, path: str | Path) -> "Lexicon":
        p = Path(path)
        if not p.is_file():
            raise ConfigError(f"読み辞書が見つかりません: {p}")
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            return cls.from_json(text, origin=str(p))
        return cls.from_tsv(text, origin=str(p))

    @classmethod
    def load_all(cls, paths: list[Path]) -> "Lexicon":
        lex = cls()
        for path in paths:
            lex.merge(cls.load(path))
        return lex

    def to_tsv(self) -> str:
        lines = ["# 表記\t読み\tメモ"]
        for entry in self.entries:
            lines.append(f"{entry.surface}\t{entry.reading}\t{entry.note}".rstrip("\t"))
        return "\n".join(lines) + "\n"


def find_risky_terms(text: str, lexicon: Lexicon | None = None) -> list[Risk]:
    """誤読しやすい語を列挙する。辞書で処理済みのものは除く。

    「処理済み」の判定は、辞書を適用した後のテキストにその語が残っているかで
    行う。``44.2点`` のように候補（``44.2``）より広い範囲を登録した場合も、
    ``ノールック`` のように読みを表記と同じにして「確認済み」を表明した場合も、
    どちらも正しく除外される。

    返り値は出現回数の多い順。台本の最終チェックで人間が目を通す用。
    """
    lexicon = lexicon or Lexicon()
    converted, _ = lexicon.apply(text)

    def handled(term: str) -> bool:
        # 辞書にそのまま載っている（読み＝表記の「確認済み」登録を含む）
        if term in lexicon:
            return True
        # 辞書適用で書き換えられて消えた
        return term not in converted

    counts: dict[tuple[str, str], int] = {}

    def collect(
        pattern: re.Pattern[str],
        kind: str,
        skip: frozenset[str] = frozenset(),
        min_length: int = 1,
    ) -> None:
        for match in pattern.finditer(text):
            term = match.group(0)
            if len(term) < min_length or term in skip or handled(term):
                continue
            counts[(term, kind)] = counts.get((term, kind), 0) + 1

    collect(KATAKANA, "katakana", COMMON_KATAKANA, min_length=3)
    collect(LATIN, "latin", COMMON_LATIN)
    collect(SCORE, "score")
    collect(DECIMAL, "decimal")

    risks = [Risk(term=t, kind=k, count=c) for (t, k), c in counts.items()]
    risks.sort(key=lambda r: (-r.count, r.kind, r.term))
    return risks
