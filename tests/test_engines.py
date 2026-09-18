"""エンジンの組み立てとリクエスト内容の検証。

実際の API やローカルサーバーには接続せず、HTTP 層を差し替えて
「何を、どんなパラメータで呼ぶか」だけを確かめる。
"""

import math
from array import array

import pytest

from jigoe.audio import Pcm
from jigoe.config import VoiceConfig
from jigoe.engines.base import available_engines, get_engine
from jigoe.errors import ConfigError, EngineError


def wav_bytes(seconds=0.2, rate=24000):
    frames = int(seconds * rate)
    samples = array("h", bytes(2 * frames))
    for i in range(frames):
        samples[i] = int(6000 * math.sin(2 * math.pi * 300 * i / rate))
    return Pcm(samples.tobytes(), rate, 1).to_wav_bytes()


@pytest.fixture
def spy(monkeypatch):
    """jigoe.http の呼び出しを記録し、固定のレスポンスを返す。"""
    calls: list[dict] = []
    responses: dict[str, object] = {"request": wav_bytes(), "json": {}}

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return responses["request"]

    def fake_get_json(url, **kwargs):
        calls.append({"method": "GET", "url": url, **kwargs})
        return responses["json"]

    def fake_post_json(url, **kwargs):
        calls.append({"method": "POST", "url": url, **kwargs})
        return responses["json"]

    for module in ("voicevox_like", "sbv2", "gptsovits", "elevenlabs", "fishaudio"):
        mod = __import__(f"jigoe.engines.{module}", fromlist=["x"])
        for name, fake in (
            ("request", fake_request),
            ("get_json", fake_get_json),
            ("post_json", fake_post_json),
        ):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, fake)

    return calls, responses


# --- レジストリ ---------------------------------------------------------


def test_all_engines_are_registered():
    assert set(available_engines()) == {
        "mock", "voicevox", "aivisspeech", "sbv2", "gptsovits", "elevenlabs", "fishaudio",
    }


def test_unknown_engine_is_reported():
    with pytest.raises(EngineError, match="未知のエンジン"):
        get_engine("nope")


def test_cloud_engines_are_marked_as_cloning():
    registry = available_engines()
    assert registry["elevenlabs"].clones_voice
    assert registry["fishaudio"].clones_voice
    assert not registry["voicevox"].clones_voice  # 配布キャラ音声のみ


# --- mock ---------------------------------------------------------------


def test_mock_duration_scales_with_text_length():
    engine = get_engine("mock")
    short = engine.synthesize("あいうえお")
    long = engine.synthesize("あいうえお" * 4)
    assert long.duration > short.duration * 3


def test_mock_speed_shortens_audio():
    engine = get_engine("mock")
    assert engine.synthesize("同じ文です", speed=2.0).duration < engine.synthesize(
        "同じ文です", speed=1.0
    ).duration


# --- VOICEVOX 互換 ------------------------------------------------------


def test_aivisspeech_posts_query_then_synthesis(spy):
    calls, responses = spy
    responses["json"] = {"speedScale": 1.0, "prePhonemeLength": 0.1, "postPhonemeLength": 0.1}
    engine = get_engine("aivisspeech", {"speaker": 42}, VoiceConfig(speed=1.2))
    pcm = engine.synthesize("テスト")

    assert pcm.duration > 0
    query, synth = calls
    assert query["url"].endswith("/audio_query")
    assert query["params"] == {"text": "テスト", "speaker": 42}
    assert synth["url"].endswith("/synthesis")
    assert synth["json"]["speedScale"] == 1.2
    # 前後の余白はパイプライン側で管理するのでエンジンには持たせない
    assert synth["json"]["prePhonemeLength"] == 0.0
    assert synth["json"]["postPhonemeLength"] == 0.0


def test_aivisspeech_uses_its_own_default_port(spy):
    calls, responses = spy
    responses["json"] = {}
    get_engine("aivisspeech").synthesize("テスト")
    assert "127.0.0.1:10101" in calls[0]["url"]


def test_voicevox_uses_its_own_default_port(spy):
    calls, responses = spy
    responses["json"] = {}
    get_engine("voicevox").synthesize("テスト")
    assert "127.0.0.1:50021" in calls[0]["url"]


def test_base_url_override(spy):
    calls, responses = spy
    responses["json"] = {}
    get_engine("voicevox", {"base_url": "http://localhost:9999/"}).synthesize("テスト")
    assert calls[0]["url"].startswith("http://localhost:9999/audio_query")


def test_voices_flattens_styles(spy):
    _, responses = spy
    responses["json"] = [
        {"name": "話者A", "speaker_uuid": "uuid-a", "styles": [{"id": 1, "name": "ノーマル"}]}
    ]
    voices = get_engine("voicevox").voices()
    assert voices[0].id == "1"
    assert voices[0].name == "話者A / ノーマル"


def test_connection_failure_explains_how_to_start_the_engine(monkeypatch):
    import jigoe.engines.voicevox_like as mod

    def boom(*args, **kwargs):
        raise EngineError("Connection refused")

    monkeypatch.setattr(mod, "get_json", boom)
    with pytest.raises(EngineError, match="AivisSpeech を起動"):
        get_engine("aivisspeech").voices()


# --- Style-Bert-VITS2 ---------------------------------------------------


def test_sbv2_converts_speed_to_length(spy):
    calls, _ = spy
    get_engine("sbv2", {"model_id": 3}, VoiceConfig(speed=2.0)).synthesize("テスト")
    params = calls[0]["params"]
    assert params["length"] == 0.5  # length は話速の逆数
    assert params["model_id"] == 3
    assert params["auto_split"] is False  # 分割はこちらで済ませている


def test_sbv2_style_argument_wins_over_config(spy):
    calls, _ = spy
    get_engine("sbv2", {"style": "Neutral"}).synthesize("テスト", style="Happy")
    assert calls[0]["params"]["style"] == "Happy"


# --- GPT-SoVITS ---------------------------------------------------------


def test_gptsovits_requires_a_reference_audio():
    with pytest.raises(ConfigError, match="ref_audio_path"):
        get_engine("gptsovits").synthesize("テスト")


def test_gptsovits_rejects_a_missing_reference_file(tmp_path):
    engine = get_engine("gptsovits", {"ref_audio_path": str(tmp_path / "nope.wav")})
    with pytest.raises(ConfigError, match="参照音声が見つかりません"):
        engine.synthesize("テスト")


def test_gptsovits_sends_the_reference_and_prompt(spy, tmp_path):
    calls, _ = spy
    ref = tmp_path / "ref.wav"
    ref.write_bytes(wav_bytes())
    engine = get_engine(
        "gptsovits", {"ref_audio_path": str(ref), "prompt_text": "参照音声の内容"}
    )
    engine.synthesize("テスト")
    payload = calls[0]["json"]
    assert payload["ref_audio_path"] == str(ref)
    assert payload["prompt_text"] == "参照音声の内容"
    assert payload["media_type"] == "wav"
    assert payload["streaming_mode"] is False


# --- ElevenLabs ---------------------------------------------------------


def test_elevenlabs_needs_an_api_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="ELEVENLABS_API_KEY"):
        get_engine("elevenlabs", {"voice_id": "v1"}).synthesize("テスト")


def test_elevenlabs_needs_a_voice_id(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    with pytest.raises(ConfigError, match="voice_id"):
        get_engine("elevenlabs").synthesize("テスト")


def test_elevenlabs_rejects_mp3_output(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    engine = get_engine("elevenlabs", {"voice_id": "v1", "output_format": "mp3_44100_128"})
    with pytest.raises(ConfigError, match="pcm_"):
        engine.synthesize("テスト")


def test_elevenlabs_sends_settings_and_parses_headerless_pcm(spy, monkeypatch):
    calls, responses = spy
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    responses["request"] = b"\x00\x01" * 12000  # ヘッダ無し PCM
    engine = get_engine(
        "elevenlabs", {"voice_id": "v1", "stability": 0.4}, VoiceConfig(speed=1.1)
    )
    pcm = engine.synthesize("テスト")

    assert pcm.sample_rate == 24000
    assert pcm.duration == pytest.approx(0.5, abs=0.01)
    call = calls[0]
    assert call["url"].endswith("/text-to-speech/v1")
    assert call["headers"]["xi-api-key"] == "k"
    assert call["json"]["voice_settings"]["stability"] == 0.4
    assert call["json"]["voice_settings"]["speed"] == 1.1


def test_elevenlabs_clamps_speed_to_the_supported_range(spy, monkeypatch):
    calls, _ = spy
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    get_engine("elevenlabs", {"voice_id": "v1"}, VoiceConfig(speed=3.0)).synthesize("テスト")
    assert calls[0]["json"]["voice_settings"]["speed"] == 1.2


def test_elevenlabs_custom_api_key_env(monkeypatch, spy):
    monkeypatch.setenv("MY_KEY", "secret")
    calls, _ = spy
    get_engine("elevenlabs", {"voice_id": "v1", "api_key_env": "MY_KEY"}).synthesize("テスト")
    assert calls[0]["headers"]["xi-api-key"] == "secret"


# --- Fish Audio ---------------------------------------------------------


def test_fishaudio_requires_a_reference_id(monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "k")
    with pytest.raises(ConfigError, match="reference_id"):
        get_engine("fishaudio").synthesize("テスト")


def test_fishaudio_requests_wav(spy, monkeypatch):
    calls, _ = spy
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "k")
    get_engine("fishaudio", {"reference_id": "model-1"}).synthesize("テスト")
    call = calls[0]
    assert call["json"]["format"] == "wav"
    assert call["json"]["reference_id"] == "model-1"
    assert call["headers"]["Authorization"] == "Bearer k"
