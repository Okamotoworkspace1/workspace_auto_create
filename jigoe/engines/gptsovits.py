"""GPT-SoVITS の API サーバー（``api_v2.py``）向けエンジン。

リサーチにある通り、参照音声 5〜15 秒程度のゼロショットで声質を再現できる。
学習させずに「まず自分の声で試す」用途に向く。参照音声と、その音声で実際に
喋っている文（``prompt_text``）が一致していないと精度が落ちる点に注意。
"""

from __future__ import annotations

from pathlib import Path

from ..audio import Pcm
from ..errors import ConfigError, EngineError
from ..http import request
from .base import Engine, Voice, register


@register
class GptSoVitsEngine(Engine):
    """GPT-SoVITS api_v2（既定 http://127.0.0.1:9880）。"""

    name = "gptsovits"
    clones_voice = True
    description = "GPT-SoVITS（無料 OSS・参照音声数秒のゼロショット）"

    default_url = "http://127.0.0.1:9880"

    def _ref_audio(self) -> str:
        ref = self.option("ref_audio_path", required=True)
        path = Path(str(ref))
        if not path.exists():
            raise ConfigError(
                f"参照音声が見つかりません: {path}"
                "（GPT-SoVITS サーバーから見えるパスを指定してください）"
            )
        return str(path)

    def voices(self) -> list[Voice]:
        # api_v2 に一覧エンドポイントは無い。設定中の参照音声を返す。
        ref = self.options.get("ref_audio_path", "(未設定)")
        return [Voice(id=str(ref), name="参照音声", note="ref_audio_path で切り替える")]

    def health(self) -> str:
        try:
            request(
                "GET",
                f"{self.base_url(self.default_url)}/tts",
                params={"text": "テスト", "text_lang": "ja"},
                retries=0,
                timeout=10,
                label="疎通確認",
            )
        except EngineError as exc:
            # パラメータ不足のエラーが返るなら、サーバー自体は生きている
            if "HTTP 400" not in str(exc):
                raise EngineError(
                    f"GPT-SoVITS に接続できません（{exc}）。"
                    "`python api_v2.py` でサーバーを起動してください"
                ) from exc
        return "gptsovits: 接続できました"

    def synthesize(
        self,
        text: str,
        *,
        speed: float | None = None,
        pitch: float | None = None,
        volume: float | None = None,
        style: str | None = None,
    ) -> Pcm:
        payload = {
            "text": text,
            "text_lang": self.option("text_lang", "ja"),
            "ref_audio_path": self._ref_audio(),
            "prompt_text": self.option("prompt_text", ""),
            "prompt_lang": self.option("prompt_lang", "ja"),
            "speed_factor": self.resolve("speed", speed, 1.0),
            "text_split_method": self.option("text_split_method", "cut0"),
            "media_type": "wav",
            "streaming_mode": False,
        }
        raw = request(
            "POST",
            f"{self.base_url(self.default_url)}/tts",
            json=payload,
            headers={"Accept": "audio/wav"},
            label="音声合成",
        )
        pcm = Pcm.from_wav_bytes(raw)
        volume = self.resolve("volume", volume, 1.0)
        return pcm.gain(volume) if volume != 1.0 else pcm
