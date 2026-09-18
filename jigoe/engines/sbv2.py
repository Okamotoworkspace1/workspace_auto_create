"""Style-Bert-VITS2 の API サーバー（``server_fastapi.py``）向けエンジン。

リサーチで「日本語の自然な抑揚に強い／AivisSpeech の中身」とされた OSS。
ITA コーパスを数分〜20 分ほど自分の声で収録して学習させれば、完全無料で
自声モデルが手に入る。GUI で完結させたいなら AivisSpeech、学習や
スタイル指定まで細かく触りたいならこちら。
"""

from __future__ import annotations

from ..audio import Pcm
from ..errors import EngineError
from ..http import get_json, request
from .base import Engine, Voice, register


@register
class StyleBertVits2Engine(Engine):
    """Style-Bert-VITS2 API サーバー（既定 http://127.0.0.1:5000）。"""

    name = "sbv2"
    clones_voice = True
    description = "Style-Bert-VITS2（無料 OSS・自声モデルを学習して使う）"

    default_url = "http://127.0.0.1:5000"

    def voices(self) -> list[Voice]:
        url = f"{self.base_url(self.default_url)}/models/info"
        try:
            data = get_json(url, label="モデル一覧の取得", retries=1)
        except EngineError as exc:
            raise EngineError(
                f"Style-Bert-VITS2 に接続できません（{exc}）。"
                "`python server_fastapi.py` でサーバーを起動してください"
            ) from exc
        voices: list[Voice] = []
        for model_id, info in (data or {}).items():
            name = info.get("config_path", "") or info.get("model_path", "")
            for speaker in (info.get("spk2id") or {"": 0}):
                voices.append(
                    Voice(
                        id=str(model_id),
                        name=f"{info.get('model_name', name)} / {speaker or 'default'}",
                        note="styles: " + ", ".join((info.get("style2id") or {}).keys()),
                    )
                )
        return voices

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
        params: dict[str, object] = {
            "text": text,
            "encoding": "utf-8",
            "model_id": int(self.option("model_id", 0)),
            "language": self.option("language", "JP"),
            # Style-Bert-VITS2 の `length` は話速の逆数
            "length": round(1.0 / speed, 4),
            "sdp_ratio": float(self.option("sdp_ratio", 0.2)),
            "noise": float(self.option("noise", 0.6)),
            "noisew": float(self.option("noisew", 0.8)),
            "style": style or self.voice.style or self.option("style", "Neutral"),
            "style_weight": float(self.option("style_weight", 1.0)),
            # 分割はこちら側で済ませているのでエンジンには任せない
            "auto_split": bool(self.option("auto_split", False)),
        }
        speaker_name = self.option("speaker_name")
        if speaker_name:
            params["speaker_name"] = speaker_name
        else:
            params["speaker_id"] = int(self.option("speaker_id", 0))

        raw = request(
            "GET",
            f"{self.base_url(self.default_url)}/voice",
            params={k: v for k, v in params.items() if v is not None},
            headers={"Accept": "audio/wav"},
            label="音声合成",
        )
        pcm = Pcm.from_wav_bytes(raw)
        volume = self.resolve("volume", volume, 1.0)
        return pcm.gain(volume) if volume != 1.0 else pcm
