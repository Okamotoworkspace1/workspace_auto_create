"""WAV / PCM の最小限の処理。外部ライブラリなしで動く。

numpy も ffmpeg も前提にしない。``audioop``（Python 3.12 まで標準）が使えれば
それを、無ければ純 Python の実装を使う。扱うのは 16bit 整数 PCM に統一する。
"""

from __future__ import annotations

import io
import math
import warnings
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

from .errors import AudioError

with warnings.catch_warnings():
    # 3.12 で DeprecationWarning が出るが、無ければ下の純 Python 実装に落ちるだけ
    warnings.simplefilter("ignore", DeprecationWarning)
    try:
        import audioop  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - Python 3.13 以降
        audioop = None  # type: ignore[assignment]

SAMPWIDTH = 2  # 16bit に統一
_MAX = 32767


def _clamp(value: float) -> int:
    if value > _MAX:
        return _MAX
    if value < -_MAX - 1:
        return -_MAX - 1
    return int(value)


@dataclass
class Pcm:
    """16bit 整数 PCM のかたまり。"""

    data: bytes
    sample_rate: int
    channels: int = 1

    def __post_init__(self) -> None:
        frame = SAMPWIDTH * self.channels
        if len(self.data) % frame:
            # 端数フレームは切り捨てる（エンジンが途中で切れた場合の保険）
            self.data = self.data[: len(self.data) // frame * frame]

    # --- 基本情報 -------------------------------------------------------

    @property
    def frame_count(self) -> int:
        return len(self.data) // (SAMPWIDTH * self.channels)

    @property
    def duration(self) -> float:
        """秒。"""
        return self.frame_count / self.sample_rate if self.sample_rate else 0.0

    @property
    def peak(self) -> int:
        """最大振幅（0〜32767）。"""
        if not self.data:
            return 0
        if audioop is not None:
            return audioop.max(self.data, SAMPWIDTH)
        samples = array("h")
        samples.frombytes(self.data)
        return max((abs(s) for s in samples), default=0)

    def peak_dbfs(self) -> float:
        peak = self.peak
        if peak <= 0:
            return -math.inf
        return 20 * math.log10(peak / _MAX)

    # --- 生成 -----------------------------------------------------------

    @classmethod
    def silence(cls, seconds: float, sample_rate: int, channels: int = 1) -> "Pcm":
        frames = max(0, int(round(seconds * sample_rate)))
        return cls(b"\x00" * (frames * SAMPWIDTH * channels), sample_rate, channels)

    @classmethod
    def from_wav_bytes(cls, raw: bytes) -> "Pcm":
        """WAV バイト列を読む。ビット深度は 16bit に正規化する。"""
        try:
            with wave.open(io.BytesIO(raw), "rb") as wf:
                channels = wf.getnchannels()
                width = wf.getsampwidth()
                rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
        except (wave.Error, EOFError) as exc:
            raise AudioError(f"WAV として読めません: {exc}") from exc
        return cls(_to_16bit(frames, width), rate, channels)

    @classmethod
    def from_bytes(cls, raw: bytes, *, sample_rate: int, channels: int = 1) -> "Pcm":
        """WAV でもヘッダ無し PCM でも受け取る。

        ElevenLabs の ``pcm_*`` のようにヘッダ無しで返るエンジンがあるため、
        RIFF ヘッダの有無で判定する。
        """
        if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
            return cls.from_wav_bytes(raw)
        if raw[:4] in (b"ID3\x03", b"ID3\x04") or raw[:2] in (b"\xff\xfb", b"\xff\xf3"):
            raise AudioError(
                "MP3 が返りました。jigoe は連結のため PCM/WAV を必要とします。"
                "エンジン設定の output_format を pcm_24000 などに変更してください。"
            )
        return cls(raw, sample_rate, channels)

    @classmethod
    def load(cls, path: str | Path) -> "Pcm":
        return cls.from_wav_bytes(Path(path).read_bytes())

    # --- 変換 -----------------------------------------------------------

    def to_mono(self) -> "Pcm":
        if self.channels == 1:
            return self
        if audioop is not None and self.channels == 2:
            return Pcm(audioop.tomono(self.data, SAMPWIDTH, 0.5, 0.5), self.sample_rate, 1)
        src = array("h")
        src.frombytes(self.data)
        n = self.channels
        out = array("h", bytes(2 * (len(src) // n)))
        for i in range(len(src) // n):
            out[i] = _clamp(sum(src[i * n : i * n + n]) / n)
        return Pcm(out.tobytes(), self.sample_rate, 1)

    def resample(self, sample_rate: int) -> "Pcm":
        """線形補間でサンプリングレートを変換する。"""
        if sample_rate == self.sample_rate or not self.data:
            return Pcm(self.data, sample_rate, self.channels) if not self.data else self
        if audioop is not None:
            converted, _ = audioop.ratecv(
                self.data, SAMPWIDTH, self.channels, self.sample_rate, sample_rate, None
            )
            return Pcm(converted, sample_rate, self.channels)
        src = array("h")
        src.frombytes(self.data)
        ch = self.channels
        in_frames = len(src) // ch
        out_frames = max(1, int(in_frames * sample_rate / self.sample_rate))
        out = array("h", bytes(2 * out_frames * ch))
        ratio = (in_frames - 1) / (out_frames - 1) if out_frames > 1 else 0.0
        for i in range(out_frames):
            pos = i * ratio
            left = int(pos)
            right = min(left + 1, in_frames - 1)
            frac = pos - left
            for c in range(ch):
                a = src[left * ch + c]
                b = src[right * ch + c]
                out[i * ch + c] = _clamp(a + (b - a) * frac)
        return Pcm(out.tobytes(), sample_rate, ch)

    def gain(self, factor: float) -> "Pcm":
        """振幅を倍率で変える。"""
        if factor == 1.0 or not self.data:
            return self
        if audioop is not None:
            return Pcm(audioop.mul(self.data, SAMPWIDTH, factor), self.sample_rate, self.channels)
        samples = array("h")
        samples.frombytes(self.data)
        for i, value in enumerate(samples):
            samples[i] = _clamp(value * factor)
        return Pcm(samples.tobytes(), self.sample_rate, self.channels)

    def normalize(self, target_dbfs: float | None) -> "Pcm":
        """ピークが target_dbfs になるようゲインを合わせる。"""
        if target_dbfs is None:
            return self
        peak = self.peak
        if peak <= 0:
            return self
        target = _MAX * (10 ** (target_dbfs / 20))
        return self.gain(target / peak)

    def conform(self, sample_rate: int, channels: int = 1) -> "Pcm":
        """レートとチャンネル数を揃える。連結前に必ず通す。"""
        pcm = self.to_mono() if channels == 1 else self
        return pcm.resample(sample_rate)

    # --- 出力 -----------------------------------------------------------

    def to_wav_bytes(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(SAMPWIDTH)
            wf.setframerate(self.sample_rate)
            wf.writeframes(self.data)
        return buf.getvalue()

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.to_wav_bytes())
        return p


def concat(parts: list[Pcm], sample_rate: int, channels: int = 1) -> Pcm:
    """複数の Pcm を 1 本に連結する。レート・チャンネルは揃えてから繋ぐ。"""
    chunks = [p.conform(sample_rate, channels).data for p in parts if p.frame_count]
    return Pcm(b"".join(chunks), sample_rate, channels)


def _to_16bit(frames: bytes, width: int) -> bytes:
    """任意ビット深度の整数 PCM を 16bit にする。"""
    if width == SAMPWIDTH:
        return frames
    if audioop is not None:
        return audioop.lin2lin(frames, width, SAMPWIDTH)
    if width == 1:  # 8bit WAV は符号なし
        return array("h", [(b - 128) << 8 for b in frames]).tobytes()
    if width == 3:
        out = array("h", bytes(2 * (len(frames) // 3)))
        for i in range(len(frames) // 3):
            value = int.from_bytes(frames[i * 3 : i * 3 + 3], "little", signed=True)
            out[i] = _clamp(value >> 8)
        return out.tobytes()
    if width == 4:
        src = array("i")
        src.frombytes(frames)
        out = array("h", bytes(2 * len(src)))
        for i, value in enumerate(src):
            out[i] = _clamp(value >> 16)
        return out.tobytes()
    raise AudioError(f"未対応のビット深度です: {width * 8}bit")
