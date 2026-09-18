"""オフライン用のダミーエンジン。

API キーも GPU もローカルサーバーも無い状態で、台本解析・ポーズ・字幕・
連結までのパイプライン全体を通して確かめるためのもの。音声としては
「文字数に比例した長さの、抑揚のついたブザー音」を返す。

テストと動作確認のための土台であって、納品用の音声ではない。
"""

from __future__ import annotations

import math
from array import array

from ..audio import Pcm
from ..config import VoiceConfig
from ..cost import CHARS_PER_SECOND
from .base import Engine, Voice, register


@register
class MockEngine(Engine):
    """合成しているように見えるだけのエンジン。"""

    name = "mock"
    clones_voice = False
    description = "オフライン確認用のダミー音声（API 不要）"

    def __init__(self, options=None, voice: VoiceConfig | None = None):
        super().__init__(options, voice)
        self.sample_rate = int(self.option("sample_rate", 24000))
        self.base_freq = float(self.option("base_freq", 130.0))

    def voices(self) -> list[Voice]:
        return [Voice(id="mock", name="mock voice", note="ダミー")]

    def health(self) -> str:
        return "mock: API 不要。常に利用できます"

    def synthesize(
        self,
        text: str,
        *,
        speed: float | None = None,
        pitch: float | None = None,
        volume: float | None = None,
        style: str | None = None,
    ) -> Pcm:
        speed = self.resolve("speed", speed, 1.0) or 1.0
        pitch = self.resolve("pitch", pitch, 0.0)
        volume = self.resolve("volume", volume, 1.0)

        seconds = max(0.12, len(text) / (CHARS_PER_SECOND * max(0.1, speed)))
        frames = int(seconds * self.sample_rate)
        freq = self.base_freq * (2 ** (pitch / 12))
        samples = array("h", bytes(2 * frames))

        for i in range(frames):
            t = i / self.sample_rate
            # 3 Hz 程度のゆらぎで抑揚らしさを出し、両端をフェードして繋ぎ目を消す
            wobble = 1 + 0.06 * math.sin(2 * math.pi * 3.1 * t)
            wave_value = (
                math.sin(2 * math.pi * freq * wobble * t)
                + 0.35 * math.sin(4 * math.pi * freq * wobble * t)
                + 0.15 * math.sin(6 * math.pi * freq * wobble * t)
            )
            envelope = min(1.0, i / (0.02 * self.sample_rate + 1), (frames - i) / (0.02 * self.sample_rate + 1))
            samples[i] = int(max(-32767, min(32767, wave_value * envelope * volume * 7000)))

        return Pcm(samples.tobytes(), self.sample_rate, 1)
