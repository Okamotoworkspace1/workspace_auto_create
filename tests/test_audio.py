import math

import pytest

from jigoe.audio import Pcm, concat
from jigoe.errors import AudioError


def tone(seconds=0.2, rate=16000, amplitude=8000, channels=1):
    from array import array

    frames = int(seconds * rate)
    samples = array("h", bytes(2 * frames * channels))
    for i in range(frames):
        value = int(amplitude * math.sin(2 * math.pi * 440 * i / rate))
        for c in range(channels):
            samples[i * channels + c] = value
    return Pcm(samples.tobytes(), rate, channels)


def test_silence_duration():
    assert Pcm.silence(1.5, 24000).duration == pytest.approx(1.5)


def test_wav_roundtrip_preserves_audio():
    original = tone()
    restored = Pcm.from_wav_bytes(original.to_wav_bytes())
    assert restored.sample_rate == original.sample_rate
    assert restored.data == original.data


def test_from_bytes_detects_headerless_pcm():
    raw = tone().data
    pcm = Pcm.from_bytes(raw, sample_rate=24000)
    assert pcm.sample_rate == 24000
    assert pcm.data == raw


def test_from_bytes_detects_wav_header():
    pcm = Pcm.from_bytes(tone(rate=16000).to_wav_bytes(), sample_rate=99999)
    assert pcm.sample_rate == 16000  # ヘッダの値が優先される


def test_from_bytes_rejects_mp3_with_a_useful_message():
    with pytest.raises(AudioError, match="output_format"):
        Pcm.from_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100, sample_rate=44100)


def test_concat_sums_durations():
    parts = [tone(0.2), Pcm.silence(0.5, 16000), tone(0.3)]
    joined = concat(parts, 16000)
    assert joined.duration == pytest.approx(1.0, abs=0.01)


def test_concat_conforms_mixed_rates():
    joined = concat([tone(0.5, rate=16000), tone(0.5, rate=24000)], 44100)
    assert joined.sample_rate == 44100
    assert joined.duration == pytest.approx(1.0, abs=0.02)


def test_resample_keeps_duration():
    resampled = tone(0.5, rate=16000).resample(44100)
    assert resampled.sample_rate == 44100
    assert resampled.duration == pytest.approx(0.5, abs=0.01)


def test_to_mono_halves_stereo_frames():
    stereo = tone(0.2, channels=2)
    mono = stereo.to_mono()
    assert mono.channels == 1
    assert mono.duration == pytest.approx(stereo.duration, abs=0.001)


def test_normalize_hits_target_peak():
    normalized = tone(amplitude=3000).normalize(-1.5)
    assert normalized.peak_dbfs() == pytest.approx(-1.5, abs=0.15)


def test_normalize_leaves_silence_alone():
    silence = Pcm.silence(0.3, 16000)
    assert silence.normalize(-1.5).data == silence.data


def test_normalize_none_is_a_noop():
    original = tone(amplitude=3000)
    assert original.normalize(None).data == original.data


def test_gain_scales_peak():
    assert tone(amplitude=1000).gain(2.0).peak == pytest.approx(2000, abs=5)


def test_odd_trailing_bytes_are_dropped():
    pcm = Pcm(b"\x00" * 7, 16000, 1)
    assert len(pcm.data) == 6


def test_save_and_load(tmp_path):
    path = tone().save(tmp_path / "nested" / "a.wav")
    assert path.is_file()
    assert Pcm.load(path).duration == pytest.approx(0.2)


# --- audioop が無い環境（Python 3.13 以降）の純 Python 実装 -----------------


@pytest.fixture
def without_audioop(monkeypatch):
    import jigoe.audio as audio_mod

    monkeypatch.setattr(audio_mod, "audioop", None)


def test_fallback_resample_matches_duration(without_audioop):
    resampled = tone(0.5, rate=16000).resample(44100)
    assert resampled.sample_rate == 44100
    assert resampled.duration == pytest.approx(0.5, abs=0.01)


def test_fallback_to_mono(without_audioop):
    mono = tone(0.1, channels=2).to_mono()
    assert mono.channels == 1
    assert mono.duration == pytest.approx(0.1, abs=0.005)


def test_fallback_gain_and_peak(without_audioop):
    assert tone(0.05, amplitude=1000).gain(2.0).peak == pytest.approx(2000, abs=5)


def test_fallback_normalize(without_audioop):
    assert tone(0.05, amplitude=3000).normalize(-1.5).peak_dbfs() == pytest.approx(-1.5, abs=0.15)


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_bit_depth_conversion(width, without_audioop, tmp_path):
    import wave

    path = tmp_path / f"{width}.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(width)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * (width * 1600))
    pcm = Pcm.load(path)
    assert pcm.duration == pytest.approx(0.1, abs=0.001)
