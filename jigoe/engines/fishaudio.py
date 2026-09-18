"""Fish Audio エンジン（クラウド・有料）。

リサーチではコスパ重視の選択肢。Plus（$11 ≒ 約 1,650 円／月）で商用可、
15 秒程度の音声からクローンできる。無料枠は商用利用不可。

ElevenLabs 同様、他人の声のクローンは規約違反。同意ゲートの対象。
"""

from __future__ import annotations

from ..audio import Pcm
from ..http import get_json, request
from .base import Engine, Voice, register

API_ROOT = "https://api.fish.audio"


@register
class FishAudioEngine(Engine):
    """Fish Audio Text to Speech。"""

    name = "fishaudio"
    clones_voice = True
    description = "Fish Audio（有料・低価格。Plus 約 1,650 円/月で商用可）"

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key('FISH_AUDIO_API_KEY')}"}
        model = self.option("model")
        if model:
            headers["model"] = str(model)
        return headers

    def voices(self) -> list[Voice]:
        data = get_json(
            f"{API_ROOT}/model",
            params={"self": "true", "page_size": 100},
            headers=self._headers(),
            label="モデル一覧の取得",
            retries=1,
        )
        items = data.get("items", data if isinstance(data, list) else [])
        return [
            Voice(
                id=item.get("_id", item.get("id", "")),
                name=item.get("title", ""),
                note=item.get("languages", [""])[0] if item.get("languages") else "",
            )
            for item in items
        ]

    def health(self) -> str:
        voices = self.voices()
        return f"fishaudio: 接続できました（自分のモデル {len(voices)} 件）"

    def synthesize(
        self,
        text: str,
        *,
        speed: float | None = None,
        pitch: float | None = None,
        volume: float | None = None,
        style: str | None = None,
    ) -> Pcm:
        payload: dict[str, object] = {
            "text": text,
            "format": "wav",
            "latency": self.option("latency", "normal"),
            "normalize": bool(self.option("normalize", True)),
        }
        reference_id = self.option("reference_id", required=True)
        payload["reference_id"] = str(reference_id)

        raw = request(
            "POST",
            f"{API_ROOT}/v1/tts",
            json=payload,
            headers={**self._headers(), "Accept": "audio/wav"},
            label="音声合成",
        )
        pcm = Pcm.from_bytes(raw, sample_rate=int(self.option("sample_rate", 44100)))
        # Fish Audio 側に話速パラメータが無いため、必要なら編集ソフトで調整する
        resolved_volume = self.resolve("volume", volume, 1.0)
        return pcm.gain(resolved_volume) if resolved_volume != 1.0 else pcm
