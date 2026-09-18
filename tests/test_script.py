import pytest

from jigoe.config import AudioConfig
from jigoe.errors import ScriptError
from jigoe.script import parse_script, soft_wrap, split_sentences


def test_split_sentences_keeps_closing_brackets():
    assert split_sentences("これは文です。「そうですね。」と彼は言った。") == [
        "これは文です。",
        "「そうですね。」と彼は言った。",
    ]


def test_split_sentences_handles_multiple_endings():
    assert split_sentences("本当に？ はい！ そうです。") == ["本当に？", "はい！", "そうです。"]


def test_soft_wrap_prefers_reading_points():
    text = "あ" * 30 + "、" + "い" * 30
    parts = soft_wrap(text, 40)
    assert len(parts) == 2
    assert parts[0].endswith("、")


def test_soft_wrap_forces_split_without_candidates():
    parts = soft_wrap("あ" * 100, 30)
    assert all(len(p) <= 30 for p in parts)
    assert "".join(parts) == "あ" * 100


def test_soft_wrap_noop_when_short():
    assert soft_wrap("短い文。", 100) == ["短い文。"]


def test_headings_become_chapters_and_are_not_spoken():
    script = parse_script("# オープニング\n\n本文です。\n")
    assert [c.title for c in script.chapters] == ["オープニング"]
    assert script.text() == "本文です。"


def test_speak_headings_option():
    script = parse_script("# タイトル\n\n本文です。\n", speak_headings=True)
    assert "タイトル" in script.text()


def test_inline_pause_creates_pause_segment():
    audio = AudioConfig(sentence_pause=0.3)
    script = parse_script("前半です。[[0.9]]後半です。", audio)
    pauses = [s.seconds for s in script.segments if not s.is_speech]
    assert 0.9 in pauses


def test_inline_pause_overrides_default_sentence_pause():
    audio = AudioConfig(sentence_pause=0.5)
    script = parse_script("前半。[[0.2]]後半。", audio)
    # 書き手が明示した「間」は、既定値より短くても尊重する
    between = [s for s in script.segments if not s.is_speech][0]
    assert between.seconds == 0.2


def test_explicit_pause_at_line_end_is_not_widened():
    audio = AudioConfig(sentence_pause=0.9, paragraph_pause=1.5)
    script = parse_script("最初。[[0.2]]\n\n次の段落。", audio)
    assert [s.seconds for s in script.segments if not s.is_speech] == [0.2]


def test_implicit_pauses_take_the_longer_value():
    audio = AudioConfig(sentence_pause=0.3, chapter_pause=1.2)
    script = parse_script("最初。\n\n# 章\n\n次。", audio)
    assert max(s.seconds for s in script.segments if not s.is_speech) == 1.2


def test_comments_are_ignored():
    script = parse_script("// メモ\n本文です。\n")
    assert script.text() == "本文です。"


def test_directives_apply_to_following_lines():
    script = parse_script("@speed 1.2\n速い行です。\n@speed reset\n普通の行です。\n")
    speech = script.speech_segments
    assert speech[0].speed == 1.2
    assert speech[1].speed is None


def test_pause_directive():
    script = parse_script("最初。\n@pause 2.5\n次。\n")
    assert max(s.seconds for s in script.segments if not s.is_speech) == 2.5


def test_paragraph_break_uses_paragraph_pause():
    audio = AudioConfig(sentence_pause=0.1, paragraph_pause=1.5)
    script = parse_script("一段落目。\n\n二段落目。", audio)
    assert max(s.seconds for s in script.segments if not s.is_speech) == 1.5


def test_no_leading_pause():
    script = parse_script("\n\n本文です。")
    assert script.segments[0].is_speech


def test_char_count_excludes_pauses_and_comments():
    script = parse_script("// コメント\n@pause 1.0\nあいうえお。")
    assert script.char_count() == 6  # 句点を含む


def test_unknown_directive_raises():
    with pytest.raises(ScriptError, match="未知のディレクティブ"):
        parse_script("@unknown 1\n本文。")


def test_directive_without_value_raises():
    with pytest.raises(ScriptError, match="値が必要"):
        parse_script("@speed\n本文。")


def test_empty_script_raises():
    with pytest.raises(ScriptError, match="読み上げる本文"):
        parse_script("// コメントだけ\n")


def test_long_line_is_split_for_the_engine():
    script = parse_script("あ" * 400 + "。", max_chars=100)
    assert len(script.speech_segments) >= 4
    assert all(len(s.text) <= 100 for s in script.speech_segments)
