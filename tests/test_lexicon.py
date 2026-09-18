import pytest

from jigoe.errors import ConfigError
from jigoe.lexicon import Entry, Lexicon, find_risky_terms


def test_tsv_roundtrip():
    lex = Lexicon.from_tsv("# コメント\nレブロン\tレブロン\tメモ\n\nNBA\tエヌビーエー\n")
    assert len(lex) == 2
    reloaded = Lexicon.from_tsv(lex.to_tsv())
    assert {e.surface for e in reloaded.entries} == {"レブロン", "NBA"}


def test_tsv_rejects_missing_reading():
    with pytest.raises(ConfigError, match="表記<TAB>読み"):
        Lexicon.from_tsv("レブロン\n")


def test_json_object_form():
    lex = Lexicon.from_json('{"NBA": "エヌビーエー"}')
    assert lex.apply("NBAの話")[0] == "エヌビーエーの話"


def test_json_array_form():
    lex = Lexicon.from_json('[{"surface": "NBA", "reading": "エヌビーエー"}]')
    assert "NBA" in lex


def test_json_rejects_missing_keys():
    with pytest.raises(ConfigError, match="surface と reading"):
        Lexicon.from_json('[{"surface": "NBA"}]')


def test_longest_surface_wins():
    lex = Lexicon([Entry("カリー", "カリー"), Entry("ステフィン・カリー", "ステフカリー")])
    assert lex.apply("ステフィン・カリー選手")[0] == "ステフカリー選手"


def test_apply_counts_hits():
    lex = Lexicon([Entry("NBA", "エヌビーエー")])
    text, hits = lex.apply("NBAとNBA")
    assert text == "エヌビーエーとエヌビーエー"
    assert hits["NBA"] == 2


def test_apply_without_entries_is_a_noop():
    text, hits = Lexicon().apply("そのまま")
    assert text == "そのまま" and not hits


def test_risky_terms_flag_unregistered_names():
    risks = find_risky_terms("ステフィン・カリーが決めた。")
    assert [r.term for r in risks] == ["ステフィン・カリー"]
    assert risks[0].kind == "katakana"


def test_registered_names_are_not_flagged():
    lex = Lexicon([Entry("ステフィン・カリー", "ステフカリー")])
    assert find_risky_terms("ステフィン・カリーが決めた。", lex) == []


def test_full_name_is_treated_as_one_term():
    risks = find_risky_terms("レブロン・ジェームズ")
    assert [r.term for r in risks] == ["レブロン・ジェームズ"]


def test_common_basketball_words_are_not_flagged():
    assert find_risky_terms("リバウンドとアシストとディフェンス。") == []


def test_score_and_decimal_are_flagged():
    kinds = {r.kind for r in find_risky_terms("118-110で勝ち、平均27.4得点。")}
    assert kinds == {"score", "decimal"}


def test_known_acronyms_are_not_flagged():
    assert find_risky_terms("NBAのMVP。") == []


def test_unknown_latin_is_flagged():
    assert [r.term for r in find_risky_terms("Warriorsの試合。")] == ["Warriors"]


def test_risks_sorted_by_frequency():
    risks = find_risky_terms("カリーとカリーとデュラント。".replace("カリー", "カリーさん"))
    assert risks[0].count >= risks[-1].count


def test_compound_containing_a_known_word_is_still_flagged():
    """「カリー」を登録しても、「カリータイム」全体の読みは未確認なので出す。"""
    lex = Lexicon([Entry("カリー", "カリー")])
    assert [r.term for r in find_risky_terms("カリータイム", lex)] == ["カリータイム"]


def test_registering_the_compound_clears_it():
    lex = Lexicon([Entry("カリータイム", "カリータイム")])
    assert find_risky_terms("カリータイム", lex) == []


def test_wider_entry_covers_a_narrower_candidate():
    """「44.2点」を登録しておけば、候補の「44.2」は出てこない。"""
    lex = Lexicon([Entry("44.2点", "よんじゅうよんテンにてん")])
    assert find_risky_terms("大学時代は平均44.2点だった。", lex) == []


def test_identity_entry_marks_a_term_as_checked():
    """読みを表記と同じにして登録＝「確認済み」として扱う。"""
    lex = Lexicon([Entry("ノールック", "ノールック")])
    assert find_risky_terms("ノールックのパス。", lex) == []


def test_substituted_readings_are_not_flagged_again():
    """辞書が入れたカタカナ読みが、新たな誤読候補として出てこないこと。"""
    lex = Lexicon([Entry("ピート・マラビッチ", "ピートマラビッチ")])
    assert find_risky_terms("ピート・マラビッチの話。", lex) == []
