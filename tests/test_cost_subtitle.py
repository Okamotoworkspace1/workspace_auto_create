import pytest

from jigoe.cost import CHARS_PER_10MIN, credits_for, estimate
from jigoe.subtitle import Cue, to_srt, to_vtt, to_youtube_chapters


# --- コスト試算 ---------------------------------------------------------


def test_multilingual_is_one_credit_per_character():
    assert credits_for("elevenlabs", 3300) == 3300


def test_flash_is_half_price():
    assert credits_for("elevenlabs", 3300, model="flash") == 1650


def test_local_engines_cost_nothing():
    report = estimate(3300, engine="aivisspeech", videos_per_month=30)
    assert report.service == "local"
    assert report.monthly_jpy == 0


def test_weekly_three_videos_recommends_creator():
    """リサーチの結論（週3〜7本なら Creator が本命）と一致すること。"""
    report = estimate(CHARS_PER_10MIN, engine="elevenlabs", videos_per_month=12)
    assert report.recommended.name == "Creator"
    assert report.recommended.jpy() == 3300


def test_daily_posting_outgrows_creator():
    report = estimate(CHARS_PER_10MIN, engine="elevenlabs", videos_per_month=32)
    assert report.recommended.name == "Pro"


def test_starter_is_allowed_when_instant_clone_is_enough():
    report = estimate(
        CHARS_PER_10MIN,
        engine="elevenlabs",
        videos_per_month=8,
        require_professional_clone=False,
    )
    assert report.recommended.name == "Starter"


def test_professional_clone_requirement_skips_starter():
    report = estimate(CHARS_PER_10MIN, engine="elevenlabs", videos_per_month=8)
    assert report.recommended.name == "Creator"


def test_free_plans_are_excluded_for_commercial_use():
    report = estimate(100, engine="fishaudio", videos_per_month=1)
    assert report.recommended.name == "Plus"


def test_fish_plus_is_about_1650_yen():
    report = estimate(CHARS_PER_10MIN, engine="fishaudio", videos_per_month=8)
    assert report.recommended.jpy() == 1650


def test_exchange_rate_is_configurable():
    report = estimate(CHARS_PER_10MIN, engine="elevenlabs", videos_per_month=12, usd_jpy=160)
    assert report.recommended.jpy(160) == 3520


def test_no_plan_fits_extreme_volume():
    report = estimate(CHARS_PER_10MIN, engine="elevenlabs", videos_per_month=100_000)
    assert report.recommended is None
    assert "足りません" in "\n".join(report.lines())


def test_unknown_service_raises():
    with pytest.raises(ValueError, match="料金表"):
        estimate(100, engine="unknown-service")


# --- 字幕 ---------------------------------------------------------------


def test_srt_format():
    srt = to_srt([Cue(1, 0.0, 1.5, "こんにちは。")])
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nこんにちは。\n")


def test_vtt_uses_dot_separator():
    assert "00:00:00.000 --> 00:00:01.500" in to_vtt([Cue(1, 0.0, 1.5, "テスト")])


def test_srt_handles_hours():
    srt = to_srt([Cue(1, 3661.25, 3662.0, "長い動画")])
    assert "01:01:01,250 --> 01:01:02,000" in srt


def test_chapters_always_start_at_zero():
    text = to_youtube_chapters([("オープニング", 2.5), ("本編", 65.0)])
    assert text.splitlines() == ["0:00 オープニング", "1:05 本編"]


def test_chapters_insert_intro_when_first_starts_late():
    """最初の見出しより前に本編がある場合は、冒頭にイントロを足す。"""
    text = to_youtube_chapters([("本編", 30.0)])
    assert text.splitlines() == ["0:00 イントロ", "0:30 本編"]


def test_chapters_snap_a_near_zero_start_instead_of_adding_intro():
    text = to_youtube_chapters([("オープニング", 2.5)])
    assert text.splitlines() == ["0:00 オープニング"]


def test_chapters_show_hours_when_needed():
    assert "1:00:00 後半" in to_youtube_chapters([("前半", 0.0), ("後半", 3600.0)])


def test_empty_chapters():
    assert to_youtube_chapters([]) == ""
