import json

import pytest

from jigoe.audio import Pcm
from jigoe.config import AudioConfig, Config, VoiceConfig
from jigoe.engines.base import Engine
from jigoe.engines.mock import MockEngine
from jigoe.lexicon import Entry, Lexicon
from jigoe.pipeline import Cache, synthesize, write_outputs
from jigoe.script import parse_script

SCRIPT = """\
# オープニング

最初の文です。[[0.8]]続きの文です。

# 本編

本編の一文。
"""


class CountingEngine(Engine):
    """呼び出し回数と渡されたテキストを記録するだけのエンジン。"""

    name = "counting"
    clones_voice = False

    def __init__(self, options=None, voice=None):
        super().__init__(options, voice)
        self.calls: list[tuple[str, float]] = []

    def synthesize(self, text, *, speed=None, pitch=None, volume=None, style=None):
        self.calls.append((text, self.resolve("speed", speed, 1.0)))
        return Pcm.silence(0.4, 24000)


@pytest.fixture
def config(tmp_path):
    return Config(
        out_dir=tmp_path / "out",
        voice=VoiceConfig(engine="mock"),
        audio=AudioConfig(sample_rate=24000, lead_silence=0.2, tail_silence=0.3),
    )


def test_end_to_end_produces_expected_files(config):
    script = parse_script(SCRIPT, config.audio)
    result = synthesize(script, config, MockEngine())
    files = write_outputs(result, config.out_dir, basename="demo")

    assert set(files) >= {"wav", "srt", "vtt", "chapters", "report"}
    assert files["wav"].is_file()
    assert Pcm.load(files["wav"]).duration == pytest.approx(result.duration, abs=0.01)
    assert files["srt"].read_text(encoding="utf-8").startswith("1\n00:00:00,200")
    assert files["chapters"].read_text(encoding="utf-8").startswith("0:00 オープニング")


def test_report_json_records_timeline(config):
    result = synthesize(parse_script(SCRIPT, config.audio), config, MockEngine())
    files = write_outputs(result, config.out_dir)
    report = json.loads(files["report"].read_text(encoding="utf-8"))
    assert report["char_count"] == result.char_count
    assert len(report["timeline"]) == len(result.rendered)
    # 冒頭の無音はタイムラインに含めず、最初のセグメントはその直後から始まる
    assert report["timeline"][0]["start"] == config.audio.lead_silence


def test_timeline_is_monotonic_and_gapless(config):
    result = synthesize(parse_script(SCRIPT, config.audio), config, MockEngine())
    previous_end = config.audio.lead_silence
    for item in result.rendered:
        assert item.start == pytest.approx(previous_end, abs=0.01)
        previous_end = item.end


def test_lead_and_tail_silence_are_applied(config):
    script = parse_script("一文だけ。", config.audio)
    engine = CountingEngine()
    result = synthesize(script, config, engine)
    # 0.2（冒頭） + 0.4（合成） + 0.3（末尾）
    assert result.duration == pytest.approx(0.9, abs=0.01)


def test_lexicon_is_applied_before_synthesis(config):
    engine = CountingEngine()
    lexicon = Lexicon([Entry("NBA", "エヌビーエー")])
    synthesize(parse_script("NBAの話。", config.audio), config, engine, lexicon)
    assert engine.calls[0][0] == "エヌビーエーの話。"


def test_cue_text_keeps_the_original_wording(config):
    lexicon = Lexicon([Entry("NBA", "エヌビーエー")])
    result = synthesize(parse_script("NBAの話。", config.audio), config, CountingEngine(), lexicon)
    # 字幕は台本どおり、読み上げだけ辞書を通す
    assert result.cues()[0].text == "NBAの話。"


def test_cache_prevents_a_second_synthesis(config, tmp_path):
    cache = Cache(tmp_path / "cache")
    script = parse_script(SCRIPT, config.audio)

    first = CountingEngine()
    result = synthesize(script, config, first, cache=cache)
    assert result.synthesized_count == len(first.calls) > 0

    second = CountingEngine()
    again = synthesize(script, config, second, cache=cache)
    assert second.calls == []
    assert again.cached_count == result.synthesized_count
    assert again.duration == pytest.approx(result.duration, abs=0.001)


def test_cache_is_invalidated_by_changed_text(config, tmp_path):
    cache = Cache(tmp_path / "cache")
    engine = CountingEngine()
    synthesize(parse_script("最初の文。", config.audio), config, engine, cache=cache)
    synthesize(parse_script("違う文。", config.audio), config, engine, cache=cache)
    assert len(engine.calls) == 2


def test_cache_can_be_disabled(config, tmp_path):
    cache = Cache(tmp_path / "cache", enabled=False)
    engine = CountingEngine()
    script = parse_script("同じ文。", config.audio)
    synthesize(script, config, engine, cache=cache)
    synthesize(script, config, engine, cache=cache)
    assert len(engine.calls) == 2


def test_cache_clear(config, tmp_path):
    cache = Cache(tmp_path / "cache")
    synthesize(parse_script("文です。", config.audio), config, CountingEngine(), cache=cache)
    assert cache.clear() == 1
    assert not cache.root.exists()


def test_chapters_point_at_the_first_spoken_word(config):
    result = synthesize(parse_script(SCRIPT, config.audio), config, MockEngine())
    titles = [t for t, _ in result.chapters]
    starts = [s for _, s in result.chapters]
    assert titles == ["オープニング", "本編"]
    assert starts[0] < starts[1]
    assert starts[0] == pytest.approx(config.audio.lead_silence, abs=0.01)


def test_segment_audio_is_written_when_requested(config):
    result = synthesize(
        parse_script(SCRIPT, config.audio), config, MockEngine(), keep_segment_audio=True
    )
    files = write_outputs(result, config.out_dir, write_segments=True)
    assert len(list(files["segments"].glob("*.wav"))) == len(result.cues())


def test_peak_is_normalized(config):
    config.audio.peak_dbfs = -3.0
    result = synthesize(parse_script("音量の確認です。", config.audio), config, MockEngine())
    assert result.pcm.peak_dbfs() == pytest.approx(-3.0, abs=0.2)


def test_per_line_speed_directive_reaches_the_engine(config):
    engine = CountingEngine()
    synthesize(parse_script("@speed 1.3\n速い行。", config.audio), config, engine)
    assert engine.calls[0][1] == 1.3


def test_config_speed_is_used_when_no_directive(tmp_path):
    cfg = Config(
        out_dir=tmp_path / "out",
        voice=VoiceConfig(engine="counting", speed=1.4),
        audio=AudioConfig(sample_rate=24000),
    )
    engine = CountingEngine(voice=cfg.voice)
    synthesize(parse_script("ディレクティブ無しの行。", cfg.audio), cfg, engine)
    assert engine.calls[0][1] == 1.4


def test_directive_overrides_config_speed(tmp_path):
    cfg = Config(
        out_dir=tmp_path / "out",
        voice=VoiceConfig(engine="counting", speed=1.4),
        audio=AudioConfig(sample_rate=24000),
    )
    engine = CountingEngine(voice=cfg.voice)
    synthesize(parse_script("@speed 0.9\n遅い行。", cfg.audio), cfg, engine)
    assert engine.calls[0][1] == 0.9


def test_cache_is_invalidated_when_config_speed_changes(tmp_path):
    """設定の話速を変えたら再合成されること（古い音声が再利用されない）。"""
    cache = Cache(tmp_path / "cache")
    script_text = "同じ台本です。"

    def run(speed):
        cfg = Config(
            out_dir=tmp_path / "out",
            voice=VoiceConfig(engine="counting", speed=speed),
            audio=AudioConfig(sample_rate=24000),
        )
        engine = CountingEngine(voice=cfg.voice)
        synthesize(parse_script(script_text, cfg.audio), cfg, engine, cache=cache)
        return engine.calls

    assert len(run(1.0)) == 1
    assert len(run(1.3)) == 1  # 速度が変わったので合成し直す
    assert len(run(1.0)) == 0  # 元の速度はキャッシュから
