"""ElevenLabs エンジン（クラウド・有料）。

リサーチでは品質最優先の選択肢。自声クローンには手軽な Instant（Starter〜）と
高再現の Professional（Creator〜）があり、ナレーション用途は Professional 推奨、
つまり実質 Creator（月 $22 ≒ 約 3,300 円）が下限とされている。

**他人の声のクローンは全プランで禁止** されている。本エンジンは
:mod:`jigoe.consent` の同意ゲートの対象。

連結のため、出力は MP3 ではなく ``pcm_*`` を既定にしている。
"""

from __future__ import annotations

from ..audio import Pcm
from ..errors import ConfigError
from ..http import get_json, request
from .base import Engine, Voice, register

API_ROOT = "https://api.elevenlabs.io/v1"
#: pcm_44100 は上位プラン限定。既定は全プランで使える 24kHz。
DEFAULT_OUTPUT_FORMAT = "pcm_24000"


@register
class ElevenLabsEngine(Engine):
    """ElevenLabs Text to Speech。"""

    name = "elevenlabs"
    clones_voice = True
    description = "ElevenLabs（有料・品質最優先。自声クローンは Creator 以上が実質下限）"

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self.api_key("ELEVENLABS_API_KEY")}

    def _output_rate(self) -> int:
        fmt = str(self.option("output_format", DEFAULT_OUTPUT_FORMAT))
        if not fmt.startswith("pcm_"):
            raise ConfigError(
                f"[engines.elevenlabs] output_format は pcm_* を指定してください（現在: {fmt}）。"
                "MP3 は連結できません。"
            )
        try:
            return int(fmt.split("_", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ConfigError(f"output_format を解釈できません: {fmt}") from exc

    def voices(self) -> list[Voice]:
        data = get_json(
            f"{API_ROOT}/voices", headers=self._headers(), label="音声一覧の取得", retries=1
        )
        return [
            Voice(
                id=v.get("voice_id", ""),
                name=v.get("name", ""),
                note=v.get("category", ""),
            )
            for v in data.get("voices", [])
        ]

    def health(self) -> str:
        data = get_json(
            f"{API_ROOT}/user/subscription",
            headers=self._headers(),
            label="サブスクリプション情報の取得",
            retries=1,
        )
        used = data.get("character_count", 0)
        limit = data.get("character_limit", 0)
        tier = data.get("tier", "?")
        remaining = max(0, limit - used)
        return (
            f"elevenlabs: {tier} プラン / 今期 {used:,} 文字使用 "
            f"（残り約 {remaining:,} 文字）"
        )

    def synthesize(
        self,
        text: str,
        *,
        speed: float | None = None,
        pitch: float | None = None,
        volume: float | None = None,
        style: str | None = None,
    ) -> Pcm:
        voice_id = self.option("voice_id", required=True)
        rate = self._output_rate()

        settings: dict[str, object] = {
            "stability": float(self.option("stability", 0.5)),
            "similarity_boost": float(self.option("similarity_boost", 0.75)),
            "use_speaker_boost": bool(self.option("use_speaker_boost", True)),
        }
        if self.option("style_exaggeration") is not None:
            settings["style"] = float(self.option("style_exaggeration"))
        resolved_speed = self.resolve("speed", speed, 1.0)
        if resolved_speed != 1.0:
            # ElevenLabs が受け付ける範囲に丸める
            settings["speed"] = max(0.7, min(1.2, resolved_speed))

        raw = request(
            "POST",
            f"{API_ROOT}/text-to-speech/{voice_id}",
            params={"output_format": str(self.option("output_format", DEFAULT_OUTPUT_FORMAT))},
            json={
                "text": text,
                "model_id": self.option("model_id", "eleven_multilingual_v2"),
                "voice_settings": settings,
            },
            headers={**self._headers(), "Accept": "audio/*"},
            label="音声合成",
        )
        pcm = Pcm.from_bytes(raw, sample_rate=rate, channels=1)
        resolved_volume = self.resolve("volume", volume, 1.0)
        return pcm.gain(resolved_volume) if resolved_volume != 1.0 else pcm
